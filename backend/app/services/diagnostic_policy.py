import re
import shlex
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.core.errors import SafetyError, ValidationError


MAX_AUTO_DIAGNOSTIC_STEPS = 12
MAX_FILE_LINES = 200
MAX_GREP_MATCHES = 80
MAX_JOURNAL_LINES = 200
MAX_DIRECTORY_GREP_MATCHES = 120


@dataclass(frozen=True)
class DiagnosticCommand:
    command: str
    rule_id: str
    reason: str


SAFE_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@:+-]+(?:\.service)?$")
SAFE_PROPERTY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]+$")
SHELL_META_RE = re.compile(r"[;&|<>`\n\r]|\$\(")
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|client[_-]?secret|connection[_-]?string|dsn|jwt|bearer|credential|\bkey\b)"
)

SAFE_READ_PREFIXES = (
    "/etc",
    "/opt",
    "/srv",
    "/var/www",
    "/var/log",
    "/usr/local/etc",
)
SAFE_HOME_RE = re.compile(r"^/home/[^/]+/[^.][^/]*(?:/.*)?$")
SAFE_DIRECTORY_GREP_PREFIXES = (
    "/etc",
    "/opt",
    "/srv",
    "/var/www",
    "/usr/local/etc",
)

BLOCKED_PATH_PATTERNS = [
    re.compile(r"^/root(?:/|$)"),
    re.compile(r"^/home/[^/]+/\.ssh(?:/|$)"),
    re.compile(r"^/etc/ssh(?:/|$)"),
    re.compile(r"^/etc/(shadow|gshadow)$"),
    re.compile(r"^/proc/\d+/(environ|cmdline)$"),
    re.compile(r"^/run/secrets(?:/|$)"),
    re.compile(r"^/var/lib/(mysql|postgresql)(?:/|$)"),
    re.compile(r"(^|/)(id_rsa|id_ed25519|authorized_keys|known_hosts)$"),
    re.compile(r"\.(pem|key)$", re.I),
]


def build_diagnostic_command(tool: str, arguments: dict[str, Any] | None = None) -> DiagnosticCommand:
    args = arguments or {}
    if SHELL_META_RE.search(tool):
        raise SafetyError("Diagnostic tool name contains shell metacharacters")

    if tool == "get_uptime":
        return DiagnosticCommand("uptime", "diag.uptime", "Read system uptime")
    if tool == "get_memory":
        return DiagnosticCommand("free -m", "diag.memory", "Read memory usage")
    if tool == "get_disk_usage":
        return DiagnosticCommand("df -h", "diag.disk", "Read filesystem usage")
    if tool == "list_listening_tcp_ports":
        return DiagnosticCommand("ss -ltnp", "diag.ss", "Read listening TCP ports")
    if tool == "list_processes":
        return DiagnosticCommand("ps aux", "diag.ps", "Read process list")
    if tool == "get_service_status":
        service = _service(args.get("service"))
        return DiagnosticCommand(f"systemctl --no-pager status {shlex.quote(service)}", "diag.systemctl.status", "Read service status")
    if tool == "get_service_active_state":
        service = _service(args.get("service"))
        return DiagnosticCommand(f"systemctl is-active {shlex.quote(service)}", "diag.systemctl.is-active", "Read service active state")
    if tool == "get_service_enabled_state":
        service = _service(args.get("service"))
        return DiagnosticCommand(f"systemctl is-enabled {shlex.quote(service)}", "diag.systemctl.is-enabled", "Read service enabled state")
    if tool == "get_service_unit":
        service = _service(args.get("service"))
        return DiagnosticCommand(f"systemctl cat {shlex.quote(service)}", "diag.systemctl.cat", "Read service unit")
    if tool == "get_service_properties":
        service = _service(args.get("service"))
        properties = _properties(args.get("properties"))
        return DiagnosticCommand(f"systemctl show {shlex.quote(service)} --property={shlex.quote(','.join(properties))}", "diag.systemctl.show", "Read selected service properties")
    if tool == "get_recent_journal":
        service = _service(args.get("service"))
        lines = _bounded_int(args.get("lines"), 1, MAX_JOURNAL_LINES, 80, "journal line count")
        return DiagnosticCommand(f"journalctl -u {shlex.quote(service)} -n {lines} --no-pager", "diag.journal", "Read recent service journal")
    if tool == "curl_local":
        url = _localhost_url(args)
        return DiagnosticCommand(f"curl --max-time 5 -fsS {shlex.quote(url)}", "diag.curl.local", "Read local HTTP endpoint")
    if tool == "list_directory":
        path = _safe_path(args.get("path"))
        return DiagnosticCommand(f"ls -la {shlex.quote(path)}", "diag.ls", "List directory")
    if tool == "stat_path":
        path = _safe_path(args.get("path"))
        return DiagnosticCommand(f"stat {shlex.quote(path)}", "diag.stat", "Read path metadata")
    if tool == "read_text_file":
        path = _safe_path(args.get("path"))
        lines = _bounded_int(args.get("max_lines"), 1, MAX_FILE_LINES, 120, "file line count")
        return DiagnosticCommand(f"head -n {lines} {shlex.quote(path)}", "diag.read_text", "Read bounded text file content")
    if tool == "head_file":
        path = _safe_path(args.get("path"))
        lines = _bounded_int(args.get("lines"), 1, MAX_FILE_LINES, 80, "head line count")
        return DiagnosticCommand(f"head -n {lines} {shlex.quote(path)}", "diag.head", "Read start of file")
    if tool == "tail_file":
        path = _safe_path(args.get("path"))
        lines = _bounded_int(args.get("lines"), 1, MAX_FILE_LINES, 80, "tail line count")
        return DiagnosticCommand(f"tail -n {lines} {shlex.quote(path)}", "diag.tail", "Read end of file")
    if tool == "grep_file":
        path = _safe_path(args.get("path"))
        pattern = _grep_pattern(args.get("pattern"))
        max_matches = _bounded_int(args.get("max_matches"), 1, MAX_GREP_MATCHES, 30, "grep match count")
        return DiagnosticCommand(f"grep -n -E -m {max_matches} {shlex.quote(pattern)} {shlex.quote(path)}", "diag.grep_file", "Search one file")
    if tool == "grep_directory":
        path = _safe_directory_grep_path(args.get("path"))
        pattern = _grep_pattern(args.get("pattern"))
        max_matches = _bounded_int(args.get("max_matches"), 1, MAX_DIRECTORY_GREP_MATCHES, 50, "directory grep match count")
        return DiagnosticCommand(f"grep -R -n -E -m {max_matches} {shlex.quote(pattern)} {shlex.quote(path)}", "diag.grep_directory", "Search a narrow safe directory")

    raise SafetyError(f"Unknown auto-diagnostic tool is blocked: {tool}")


def redact_diagnostic_output(value: str) -> str:
    value = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED]", value, flags=re.DOTALL)
    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-=:]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(basic\s+)[A-Za-z0-9._\-=:]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(postgres|mysql|redis)://([^:\s/@]+):([^@\s]+)@", r"\1://\2:[REDACTED]@", value)

    redacted_lines: list[str] = []
    for line in value.splitlines():
        match = re.match(r"^(\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*[=:]\s*)(.*)$", line)
        if match and SENSITIVE_KEY_RE.search(match.group(2)):
            redacted_lines.append(f"{match.group(1)}[REDACTED]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def _service(value: Any) -> str:
    service = str(value or "").strip()
    if not service:
        raise ValidationError("Diagnostic service name is required")
    if not SAFE_SERVICE_RE.fullmatch(service) or SHELL_META_RE.search(service):
        raise SafetyError("Unsafe service name is blocked")
    return service


def _properties(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    properties = [str(item).strip() for item in raw if str(item or "").strip()]
    if not properties:
        raise ValidationError("At least one systemd property is required")
    if len(properties) > 8:
        raise SafetyError("Too many service properties requested")
    for prop in properties:
        if not SAFE_PROPERTY_RE.fullmatch(prop):
            raise SafetyError("Unsafe service property name is blocked")
    return properties


def _safe_path(value: Any) -> str:
    path = str(value or "").strip()
    if not path.startswith("/"):
        raise SafetyError("Auto-diagnostic file paths must be absolute")
    if SHELL_META_RE.search(path) or ".." in path.split("/"):
        raise SafetyError("Unsafe path syntax is blocked")
    if any(pattern.search(path) for pattern in BLOCKED_PATH_PATTERNS):
        raise SafetyError("Private, secret-bearing, or high-risk path is blocked")
    if path.startswith(SAFE_READ_PREFIXES) or SAFE_HOME_RE.match(path):
        return path
    raise SafetyError("Path is outside the auto-diagnostic read allowlist")


def _safe_directory_grep_path(value: Any) -> str:
    path = _safe_path(value)
    if path in {"/", "/etc", "/opt", "/srv"}:
        raise SafetyError("Directory grep must target a narrow application or config directory")
    if path.startswith(SAFE_DIRECTORY_GREP_PREFIXES) or SAFE_HOME_RE.match(path):
        return path
    raise SafetyError("Directory grep path is outside the narrow allowlist")


def _grep_pattern(value: Any) -> str:
    pattern = str(value or "").strip()
    if not pattern:
        raise ValidationError("Grep pattern is required")
    if len(pattern) > 120:
        raise SafetyError("Grep pattern is too long for auto-diagnostics")
    if SHELL_META_RE.search(pattern):
        raise SafetyError("Grep pattern contains blocked shell syntax")
    return pattern


def _localhost_url(args: dict[str, Any]) -> str:
    if args.get("url"):
        url = str(args["url"]).strip()
    else:
        port = _bounded_int(args.get("port"), 1, 65535, 80, "curl port")
        path = str(args.get("path") or "/").strip() or "/"
        if not path.startswith("/"):
            path = "/" + path
        url = f"http://localhost:{port}{path}"
    if SHELL_META_RE.search(url):
        raise SafetyError("URL contains blocked shell syntax")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise SafetyError("Auto-diagnostic curl is limited to local HTTP URLs")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise SafetyError("URL port is outside the valid range")
    if parsed.username or parsed.password or parsed.query:
        raise SafetyError("URLs with credentials or query strings are blocked")
    return url


def _bounded_int(value: Any, minimum: int, maximum: int, fallback: int, label: str) -> int:
    if value is None or value == "":
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid {label}") from exc
    if parsed < minimum or parsed > maximum:
        raise SafetyError(f"{label} must be between {minimum} and {maximum}")
    return parsed
