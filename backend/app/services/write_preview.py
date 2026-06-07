import difflib
import re
import shlex
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.redaction import redact_payload, redact_text
from app.schemas.phoenix import SystemInfo
from app.services.ssh_runner import SshCommandResult


MAX_PREVIEW_FILE_CHARS = 64 * 1024
MAX_PREVIEW_DIFF_CHARS = 24 * 1024

SECRET_TARGET_PATTERNS = [
    re.compile(r"(^|/)\.ssh(/|$)"),
    re.compile(r"(^|/)\.env($|[.\s])"),
    re.compile(r"(^|/)id_rsa($|[.\s])"),
    re.compile(r"(^|/)id_ed25519($|[.\s])"),
    re.compile(r"(^|/)[^\s]+\.(pem|key)$"),
]


class PreviewSshRunner(Protocol):
    def run(self, system: SystemInfo, command: str) -> SshCommandResult: ...


@dataclass(frozen=True)
class ParsedWriteCommand:
    kind: str
    target_path: str | None
    append: bool = False
    content: str | None = None
    sed_expression: str | None = None
    needs_sudo: bool = False


class WritePreviewer:
    def __init__(self, ssh_runner: PreviewSshRunner, secrets: list[str] | None = None):
        self.ssh_runner = ssh_runner
        self.secrets = secrets if secrets is not None else get_settings().configured_secrets()

    def preview(self, system: SystemInfo, command: str) -> dict[str, Any]:
        parsed = parse_write_command(command)
        if parsed is None:
            return self._redacted({"status": "not_applicable", "redacted": True})
        if not parsed.target_path:
            return self._unavailable(parsed, "Could not safely parse target file path")
        if _is_secret_target(parsed.target_path):
            return self._unavailable(parsed, "Target path may contain secrets, so diff preview was not generated")
        if not _can_simulate(parsed):
            return self._unavailable(parsed, "Could not safely simulate this shell write command")

        try:
            before = self._read_target(system, parsed)
            after = _simulate(parsed, before)
            diff = _unified_diff(before, after, parsed.target_path)
            payload = {
                "status": "available",
                "command_kind": parsed.kind,
                "target_path": parsed.target_path,
                "diff": _truncate_diff(diff),
                "truncated": len(diff) > MAX_PREVIEW_DIFF_CHARS,
                "redacted": True,
            }
            return self._redacted(payload)
        except Exception as exc:
            return self._unavailable(parsed, redact_text(str(exc), self.secrets))

    def _read_target(self, system: SystemInfo, parsed: ParsedWriteCommand) -> str:
        command = _read_command(parsed.target_path or "", parsed.needs_sudo)
        result = self.ssh_runner.run(system, command)
        if result.timed_out:
            raise ValueError("Could not read target file before timeout")
        if result.exit_code != 0:
            raise ValueError("Could not read target file for preview")
        content = result.stdout
        if len(content) > MAX_PREVIEW_FILE_CHARS:
            raise ValueError("Target file is too large for a safe diff preview")
        return content

    def _unavailable(self, parsed: ParsedWriteCommand, reason: str) -> dict[str, Any]:
        return self._redacted(
            {
                "status": "unavailable",
                "command_kind": parsed.kind,
                "target_path": parsed.target_path,
                "reason": reason,
                "redacted": True,
            }
        )

    def _redacted(self, payload: dict[str, Any]) -> dict[str, Any]:
        return redact_payload(payload, self.secrets)


def parse_write_command(command: str) -> ParsedWriteCommand | None:
    if _has_unsupported_shell_construct(command):
        if _looks_like_write_command(command):
            return ParsedWriteCommand(kind="unsupported_write", target_path=None)
        return None

    tokens = _shell_tokens(command)
    if not tokens:
        return None

    if "|" in tokens:
        return _parse_tee_pipeline(tokens)

    command_tokens, needs_sudo = _without_sudo(tokens)
    if not command_tokens:
        return None
    base = _base(command_tokens)
    if base == "sed":
        return _parse_sed(command_tokens, needs_sudo)
    if base in {"echo", "printf"}:
        return _parse_redirect(command_tokens, needs_sudo)
    if base == "tee":
        return _parse_tee(command_tokens, needs_sudo, content=None)
    return None


def _parse_sed(tokens: list[str], needs_sudo: bool) -> ParsedWriteCommand | None:
    expression: str | None = None
    paths: list[str] = []
    in_place = False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            paths.extend(tokens[index + 1 :])
            break
        if token == "-i":
            in_place = True
            index += 1
            continue
        if token.startswith("-i") and len(token) > 2:
            in_place = True
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if expression is None:
            expression = token
        else:
            paths.append(token)
        index += 1
    if not in_place:
        return None
    if expression is None or len(paths) != 1:
        return ParsedWriteCommand("sed_i", paths[0] if paths else None, needs_sudo=needs_sudo)
    return ParsedWriteCommand("sed_i", paths[0], sed_expression=expression, needs_sudo=needs_sudo)


def _parse_redirect(tokens: list[str], needs_sudo: bool) -> ParsedWriteCommand | None:
    redirects = [index for index, token in enumerate(tokens) if token in {">", ">>"} or token.startswith(">")]
    if len(redirects) != 1:
        return ParsedWriteCommand(f"{_base(tokens)}_redirect", None, needs_sudo=needs_sudo) if _base(tokens) in {"echo", "printf"} else None

    redirect_index = redirects[0]
    redirect = tokens[redirect_index]
    if redirect in {">", ">>"}:
        if redirect_index + 1 >= len(tokens):
            return ParsedWriteCommand(f"{_base(tokens)}_redirect", None, needs_sudo=needs_sudo)
        target = tokens[redirect_index + 1]
        if redirect_index + 2 != len(tokens):
            return ParsedWriteCommand(f"{_base(tokens)}_redirect", target, append=redirect == ">>", needs_sudo=needs_sudo)
    else:
        target = redirect[2:] if redirect.startswith(">>") else redirect[1:]
    base = _base(tokens)
    content_tokens = tokens[1:redirect_index]
    content = _echo_content(content_tokens) if base == "echo" else _printf_content(content_tokens)
    return ParsedWriteCommand(f"{base}_redirect", target, append=redirect.startswith(">>"), content=content, needs_sudo=needs_sudo)


def _parse_tee_pipeline(tokens: list[str]) -> ParsedWriteCommand | None:
    if tokens.count("|") != 1:
        return ParsedWriteCommand("tee", None)
    pipe_index = tokens.index("|")
    left = tokens[:pipe_index]
    right, needs_sudo = _without_sudo(tokens[pipe_index + 1 :])
    if not left or not right or _base(right) != "tee":
        return ParsedWriteCommand("unsupported_write", None) if _looks_like_write_command(" ".join(tokens)) else None
    left_base = _base(left)
    if left_base == "echo":
        content = _echo_content(left[1:])
    elif left_base == "printf":
        content = _printf_content(left[1:])
    else:
        return ParsedWriteCommand("tee", None, needs_sudo=needs_sudo)
    return _parse_tee(right, needs_sudo, content)


def _parse_tee(tokens: list[str], needs_sudo: bool, content: str | None) -> ParsedWriteCommand | None:
    append = False
    paths: list[str] = []
    for token in tokens[1:]:
        if token in {"-a", "--append"}:
            append = True
            continue
        if token.startswith("-"):
            continue
        paths.append(token)
    return ParsedWriteCommand("tee", paths[0] if len(paths) == 1 else None, append=append, content=content, needs_sudo=needs_sudo)


def _simulate(parsed: ParsedWriteCommand, before: str) -> str:
    if parsed.kind == "sed_i":
        if not parsed.sed_expression:
            raise ValueError("Could not safely parse sed expression")
        return _apply_sed_substitute(before, parsed.sed_expression)
    if parsed.kind in {"echo_redirect", "printf_redirect", "tee"}:
        if parsed.content is None:
            raise ValueError("Could not safely determine write content")
        return before + parsed.content if parsed.append else parsed.content
    raise ValueError("Unsupported write command for preview")


def _can_simulate(parsed: ParsedWriteCommand) -> bool:
    if parsed.kind == "sed_i":
        return bool(parsed.sed_expression)
    if parsed.kind in {"echo_redirect", "printf_redirect", "tee"}:
        return parsed.content is not None
    return False


def _apply_sed_substitute(before: str, expression: str) -> str:
    if not expression.startswith("s") or len(expression) < 4:
        raise ValueError("Only sed substitute expressions can be previewed")
    delimiter = expression[1]
    parts: list[str] = []
    current = []
    escaped = False
    for char in expression[2:]:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            current.append(char)
            continue
        if char == delimiter and len(parts) < 2:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    if len(parts) != 3:
        raise ValueError("Could not safely parse sed substitute expression")
    pattern, replacement, flags = parts
    count = 0 if "g" in flags else 1
    try:
        return re.sub(pattern, replacement, before, count=count, flags=re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"Could not simulate sed expression: {exc}") from exc


def _unified_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a{path}",
            tofile=f"b{path}",
            lineterm="",
        )
    )


def _truncate_diff(diff: str) -> str:
    if len(diff) <= MAX_PREVIEW_DIFF_CHARS:
        return diff
    return diff[:MAX_PREVIEW_DIFF_CHARS] + "\n[truncated]"


def _read_command(path: str, needs_sudo: bool) -> str:
    prefix = "sudo -n " if needs_sudo else ""
    return f"{prefix}cat -- {shlex.quote(path)}"


def _shell_tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|><")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return []


def _without_sudo(tokens: list[str]) -> tuple[list[str], bool]:
    if _base(tokens) != "sudo":
        return tokens, False
    index = 1
    sudo_options_with_value = {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in sudo_options_with_value:
            index += 2
            continue
        if token.startswith(("--user=", "--group=", "--host=", "--prompt=")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return (tokens[index:], True) if index < len(tokens) else ([], True)


def _echo_content(tokens: list[str]) -> str:
    newline = True
    values = tokens
    if values and values[0] == "-n":
        newline = False
        values = values[1:]
    return " ".join(values) + ("\n" if newline else "")


def _printf_content(tokens: list[str]) -> str:
    if not tokens:
        return ""
    format_text = _decode_escapes(tokens[0])
    values = tuple(tokens[1:])
    if not values:
        return format_text
    try:
        return format_text % values
    except (TypeError, ValueError):
        return format_text + "".join(values)


def _decode_escapes(value: str) -> str:
    return bytes(value, "utf-8").decode("unicode_escape")


def _base(tokens: list[str]) -> str:
    return tokens[0].split("/")[-1] if tokens else ""


def _has_unsupported_shell_construct(command: str) -> bool:
    return any(token in command for token in ("&&", "||", ";", "`", "$(", "\n", "<<"))


def _looks_like_write_command(command: str) -> bool:
    return bool(re.search(r"\b(sed|echo|printf|tee)\b", command)) and any(token in command for token in ("-i", ">", "|", "tee"))


def _is_secret_target(path: str) -> bool:
    return any(pattern.search(path) for pattern in SECRET_TARGET_PATTERNS)
