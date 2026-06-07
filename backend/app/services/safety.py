import re
import shlex
from dataclasses import dataclass

from app.schemas.runs import CommandClassification


@dataclass(frozen=True)
class SafetyResult:
    classification: CommandClassification
    reason: str
    requires_confirmation: bool = True
    requires_typed_confirmation: bool = False
    blocked: bool = False


READ_ONLY_COMMANDS = {
    "cat",
    "curl",
    "df",
    "dig",
    "du",
    "free",
    "grep",
    "head",
    "ip",
    "journalctl",
    "less",
    "ls",
    "netstat",
    "pgrep",
    "ping",
    "ps",
    "ss",
    "stat",
    "systemctl",
    "tail",
    "test",
    "top",
    "uptime",
}

INTERACTIVE_COMMANDS = {
    "ftp",
    "htop",
    "less",
    "man",
    "more",
    "mysql",
    "nano",
    "psql",
    "scp",
    "sftp",
    "ssh",
    "top",
    "vi",
    "vim",
    "watch",
}

NESTED_SHELL_COMMANDS = {
    "ash",
    "bash",
    "dash",
    "fish",
    "irb",
    "node",
    "perl",
    "php",
    "python",
    "python3",
    "ruby",
    "sh",
    "zsh",
}

MUTATING_COMMANDS = {
    "apt",
    "apt-get",
    "chgrp",
    "chmod",
    "chown",
    "cp",
    "install",
    "mkdir",
    "mv",
    "rm",
    "service",
    "systemctl",
    "tee",
    "touch",
}

SHELL_TOKENS = {"&&", "||", ";", "|"}

CRITICAL_PATHS = ("/", "/etc", "/home", "/var", "/srv", "/var/lib/postgresql")
DATABASE_PATHS = ("/var/lib/postgresql", "/var/lib/mysql")
SECURITY_SERVICES = {"ufw", "firewalld", "auditd", "apparmor", "selinux"}

SECRET_PATH_PATTERNS = [
    re.compile(r"(^|/)\.ssh(/|$)"),
    re.compile(r"(^|/)\.env($|[.\s])"),
    re.compile(r"(^|/)id_rsa($|[.\s])"),
    re.compile(r"(^|/)id_ed25519($|[.\s])"),
    re.compile(r"(^|/)[^\s]+\.(pem|key)$"),
]

BLOCK_PATTERNS = [
    (re.compile(r"\brm\s+(-[A-Za-z]*r[A-Za-z]*f|-rf|-fr)\s+(/|/etc|/home|/var|/srv|/var/lib/postgresql)(/|\s|$)"), "Broad recursive deletion is blocked"),
    (re.compile(r"\bchmod\s+-R\s+777\s+(/|/etc|/home|/var|/srv|/var/lib/postgresql)(/|\s|$)"), "Blanket world-writable permissions are blocked"),
    (re.compile(r"\b(dropdb|createdb\s+.*--template|mysql\s+.*drop\s+database|psql\s+.*drop\s+database|rm\s+.*(/var/lib/(postgresql|mysql)|\.sqlite|\.db))\b", re.I), "Database deletion or reinitialization is blocked"),
    (re.compile(r"\b(systemctl|service)\s+(stop|disable)\s+(ufw|firewalld|auditd|apparmor|selinux)\b", re.I), "Disabling firewall, audit, or security controls is blocked"),
    (re.compile(r"\b(ufw\s+disable|setenforce\s+0|aa-teardown|iptables\s+-F)\b", re.I), "Disabling firewall, audit, or security controls is blocked"),
    (re.compile(r"\b(history\s+-c|rm\s+.*(\.bash_history|/var/log|/var/log/[^\s]+)|truncate\s+.*(/var/log|\.bash_history))\b", re.I), "Deleting logs or shell history is blocked"),
    (re.compile(r"\b(sudo\s+-u\s+(postgres|mysql|root)|su\s+-\s+(postgres|mysql|root)).*(chmod|chown|psql|mysql|service|systemctl)?", re.I), "Superuser workaround patterns are blocked"),
]


def classify_command(command: str) -> SafetyResult:
    stripped = command.strip()
    if not stripped:
        return SafetyResult(CommandClassification.BLOCKED, "Empty command is blocked", blocked=True)

    blocked_reason = _blocked_reason(stripped)
    if blocked_reason:
        return SafetyResult(CommandClassification.BLOCKED, blocked_reason, blocked=True)

    tokens = _tokens(stripped)
    if not tokens:
        return SafetyResult(CommandClassification.BLOCKED, "Command could not be parsed safely", blocked=True)

    if _reads_secret_path(stripped):
        return SafetyResult(CommandClassification.BLOCKED, "Commands that read likely secret material are blocked", blocked=True)

    base = _base_command(tokens)
    if base in INTERACTIVE_COMMANDS and not _is_bounded_non_interactive_invocation(tokens):
        return SafetyResult(CommandClassification.BLOCKED, f"Interactive command '{base}' is blocked in the logged terminal", blocked=True)

    if _is_follow_mode(tokens):
        return SafetyResult(CommandClassification.BLOCKED, "Follow/watch commands do not terminate in the logged terminal", blocked=True)

    if base == "systemctl" and _systemctl_subcommand(tokens) in {"edit", "rescue", "emergency"}:
        return SafetyResult(CommandClassification.BLOCKED, "Interactive systemctl subcommands are blocked in the logged terminal", blocked=True)

    if base in NESTED_SHELL_COMMANDS:
        return SafetyResult(CommandClassification.BLOCKED, f"Nested shell or interpreter '{base}' is blocked in the logged terminal", blocked=True)

    if base == "sudo":
        sudo_target = _sudo_target(tokens)
        sudo_command_tokens = _without_sudo(tokens)
        if sudo_target in INTERACTIVE_COMMANDS and not _is_bounded_non_interactive_invocation(sudo_command_tokens):
            return SafetyResult(CommandClassification.BLOCKED, f"Interactive command '{sudo_target}' is blocked in the logged terminal", blocked=True)
        if sudo_target in NESTED_SHELL_COMMANDS:
            return SafetyResult(CommandClassification.BLOCKED, f"Nested shell or interpreter '{sudo_target}' is blocked in the logged terminal", blocked=True)
        if _is_follow_mode(tokens):
            return SafetyResult(CommandClassification.BLOCKED, "Follow/watch commands do not terminate in the logged terminal", blocked=True)
        if sudo_target == "systemctl" and _systemctl_subcommand(tokens) in {"edit", "rescue", "emergency"}:
            return SafetyResult(CommandClassification.BLOCKED, "Interactive systemctl subcommands are blocked in the logged terminal", blocked=True)
        return SafetyResult(
            CommandClassification.RISKY_MUTATING,
            "sudo requires typed technician confirmation",
            requires_typed_confirmation=True,
        )

    if _contains_shell_control(tokens):
        return SafetyResult(
            CommandClassification.RISKY_MUTATING,
            "Compound shell commands require typed technician confirmation",
            requires_typed_confirmation=True,
        )

    if _is_read_only(tokens):
        return SafetyResult(CommandClassification.READ_ONLY, "Read-only diagnostic command; technician approval still required")

    if base in MUTATING_COMMANDS or _looks_mutating(tokens):
        return SafetyResult(CommandClassification.MUTATING, "Mutating system command; technician approval required")

    return SafetyResult(CommandClassification.RISKY_MUTATING, "Unrecognized command requires typed technician confirmation", requires_typed_confirmation=True)


def ensure_command_allowed(command: str) -> SafetyResult:
    result = classify_command(command)
    if result.blocked:
        raise ValueError(result.reason)
    return result


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _base_command(tokens: list[str]) -> str:
    return tokens[0].split("/")[-1] if tokens else ""


def _sudo_target(tokens: list[str]) -> str:
    for token in tokens[1:]:
        if token == "--":
            continue
        if token.startswith("-"):
            continue
        return token.split("/")[-1]
    return ""


def _contains_shell_control(tokens: list[str]) -> bool:
    return any(token in SHELL_TOKENS for token in tokens)


def _is_read_only(tokens: list[str]) -> bool:
    base = _base_command(tokens)
    if base == "systemctl":
        return _systemctl_subcommand(tokens) in {"status", "is-active", "is-enabled", "list-units", "cat", "show"}
    if base == "journalctl":
        return True
    return base in READ_ONLY_COMMANDS and not _looks_mutating(tokens)


def _looks_mutating(tokens: list[str]) -> bool:
    mutating_flags = {"-w", "--write", "--delete", "--remove", "--force"}
    return any(token in mutating_flags for token in tokens)


def _is_bounded_non_interactive_invocation(tokens: list[str]) -> bool:
    base = _base_command(tokens)
    if base == "psql":
        return _has_psql_command_option(tokens[1:])
    return False


def _has_psql_command_option(tokens: list[str]) -> bool:
    for token in tokens:
        if token in {"-c", "--command"} or token.startswith("--command="):
            return True
        if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
            return True
    return False


def _is_follow_mode(tokens: list[str]) -> bool:
    base = _base_command(tokens)
    command_tokens = tokens
    if base == "sudo":
        target = _sudo_target(tokens)
        command_tokens = tokens[tokens.index(target) :] if target in tokens else tokens
        base = target
    if base in {"journalctl", "tail"}:
        return any(token in {"-f", "--follow"} or (token.startswith("-") and "f" in token and not token.startswith("--")) for token in command_tokens[1:])
    return False


def _systemctl_subcommand(tokens: list[str]) -> str | None:
    command_tokens = tokens
    base = _base_command(tokens)
    if base == "sudo":
        target = _sudo_target(tokens)
        command_tokens = tokens[tokens.index(target) :] if target in tokens else []
    if not command_tokens or _base_command(command_tokens) != "systemctl":
        return None
    for token in command_tokens[1:]:
        if token == "--":
            continue
        if token.startswith("-"):
            continue
        return token
    return None


def _blocked_reason(command: str) -> str | None:
    for pattern, reason in BLOCK_PATTERNS:
        if pattern.search(command):
            return reason
    tokens = _tokens(command)
    if not tokens:
        return None
    token_reason = _blocked_token_reason(tokens)
    if token_reason:
        return token_reason
    return None


def _blocked_token_reason(tokens: list[str]) -> str | None:
    command_tokens = _without_sudo(tokens)
    if not command_tokens:
        return None
    base = _base_command(command_tokens)
    if base == "rm" and _rm_deletes_critical_path(command_tokens):
        return "Broad recursive deletion is blocked"
    if base == "chmod" and _chmod_grants_blanket_permissions(command_tokens):
        return "Blanket world-writable permissions are blocked"
    if base in {"systemctl", "service"} and _disables_security_control(command_tokens):
        return "Disabling firewall, audit, or security controls is blocked"
    if base == "ufw" and _contains_any(command_tokens[1:], {"disable", "reset"}):
        return "Disabling firewall, audit, or security controls is blocked"
    if base == "iptables" and _contains_any(command_tokens[1:], {"-F", "--flush"}):
        return "Disabling firewall, audit, or security controls is blocked"
    if base == "nft" and _contains_ordered(command_tokens[1:], ["flush", "ruleset"]):
        return "Disabling firewall, audit, or security controls is blocked"
    if base == "find" and _find_deletes_logs(command_tokens):
        return "Deleting logs or shell history is blocked"
    if base in {"shred", "wipe"} and _targets_log_or_history(command_tokens[1:]):
        return "Deleting logs or shell history is blocked"
    return None


def _without_sudo(tokens: list[str]) -> list[str]:
    if _base_command(tokens) != "sudo":
        return tokens
    target = _sudo_target(tokens)
    if not target:
        return []
    for index, token in enumerate(tokens):
        if token.split("/")[-1] == target:
            return tokens[index:]
    return []


def _rm_deletes_critical_path(tokens: list[str]) -> bool:
    if not _has_recursive_flag(tokens) or not _has_force_flag(tokens):
        return False
    return any(_is_path_at_or_under(token, CRITICAL_PATHS) or _is_path_at_or_under(token, DATABASE_PATHS) for token in _path_like_tokens(tokens[1:]))


def _chmod_grants_blanket_permissions(tokens: list[str]) -> bool:
    if not _has_recursive_flag(tokens):
        return False
    grants_world_write = any(token == "777" or token.lower() in {"a+rwx", "ugo+rwx", "o+w", "a+w"} for token in tokens[1:])
    if not grants_world_write:
        return False
    return any(_is_path_at_or_under(token, CRITICAL_PATHS) for token in _path_like_tokens(tokens[1:]))


def _disables_security_control(tokens: list[str]) -> bool:
    operations = {"stop", "disable", "mask"}
    return _contains_any(tokens[1:], operations) and _contains_any(tokens[1:], SECURITY_SERVICES)


def _find_deletes_logs(tokens: list[str]) -> bool:
    return any(_is_path_at_or_under(token, ("/var/log",)) for token in _path_like_tokens(tokens[1:])) and _contains_any(tokens[1:], {"-delete"})


def _targets_log_or_history(tokens: list[str]) -> bool:
    return any(_is_path_at_or_under(token, ("/var/log",)) or token.endswith(".bash_history") or token.endswith(".zsh_history") for token in _path_like_tokens(tokens))


def _has_recursive_flag(tokens: list[str]) -> bool:
    return any(token in {"-r", "-R", "--recursive"} or (token.startswith("-") and not token.startswith("--") and any(flag in token for flag in "rR")) for token in tokens[1:])


def _has_force_flag(tokens: list[str]) -> bool:
    return any(token in {"-f", "--force"} or (token.startswith("-") and not token.startswith("--") and "f" in token) for token in tokens[1:])


def _path_like_tokens(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token.startswith("/") or token.startswith("~/") or token.startswith("./") or token.startswith("../")]


def _is_path_at_or_under(path: str, roots: tuple[str, ...]) -> bool:
    normalized = path.rstrip("/") or "/"
    for root in roots:
        root_normalized = root.rstrip("/") or "/"
        if normalized == root_normalized or normalized.startswith(root_normalized + "/"):
            return True
    return False


def _contains_any(tokens: list[str], values: set[str]) -> bool:
    lowered_values = {value.lower() for value in values}
    return any(token.lower() in lowered_values for token in tokens)


def _contains_ordered(tokens: list[str], values: list[str]) -> bool:
    position = 0
    for token in tokens:
        if token.lower() == values[position]:
            position += 1
            if position == len(values):
                return True
    return False


def _reads_secret_path(command: str) -> bool:
    tokens = _tokens(command)
    if not tokens:
        return False
    base_commands = {token.split("/")[-1] for token in tokens if not token.startswith("-")}
    if not (base_commands & {"cat", "head", "tail", "less", "grep"}):
        return False
    return any(pattern.search(token) for token in tokens[1:] for pattern in SECRET_PATH_PATTERNS)
