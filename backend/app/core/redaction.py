import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"

SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?:^|[_\-.])(?:"
    r"authorization|cookie|set-cookie|api[_-]?key|token|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"secret|client[_-]?secret|password|passwd|pwd|passphrase|private[_-]?key|credentials?|"
    r"connection[_-]?string|database[_-]?url|dsn"
    r")(?:$|[_\-.])"
)

SECRET_PATTERNS = [
    re.compile(r"(?is)-----BEGIN [^-]*(?:PRIVATE KEY|SECRET|TOKEN|CREDENTIAL)[^-]*-----.*?-----END [^-]*-----"),
    re.compile(r"(?i)(?P<prefix>authorization\s*:\s*(?:bearer|basic)\s+)(?P<secret>[^\s,;]+)"),
    re.compile(r"(?i)(?P<prefix>\b(?:bearer|basic)\s+)(?P<secret>[A-Za-z0-9._~+/=\-]+)"),
    re.compile(
        r"(?i)(?P<prefix>[\"']?\b(?:api[_-]?key|access[_-]?key|secret[_-]?key|token|access[_-]?token|"
        r"refresh[_-]?token|id[_-]?token|client[_-]?secret|secret|password|passwd|pwd|passphrase|"
        r"private[_-]?key|connection[_-]?string|database[_-]?url|dsn)\b[\"']?\s*[=:]\s*[\"'])"
        r"(?P<secret>.*?)(?P<suffix>[\"'])"
    ),
    re.compile(
        r"(?i)(?P<prefix>[\"']?\b(?:api[_-]?key|access[_-]?key|secret[_-]?key|token|access[_-]?token|"
        r"refresh[_-]?token|id[_-]?token|client[_-]?secret|secret|password|passwd|pwd|passphrase|"
        r"private[_-]?key|connection[_-]?string|database[_-]?url|dsn)\b[\"']?\s*[=:]\s*)"
        r"(?P<secret>[^\s'\"&;,}]+)"
    ),
    re.compile(
        r"(?im)^(?P<prefix>\s*[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PWD|API_KEY|PRIVATE_KEY|ACCESS_KEY|"
        r"DATABASE_URL|DSN|COOKIE)[A-Z0-9_]*\s*=\s*)(?P<secret>.+)$"
    ),
    re.compile(
        r"(?i)(?P<prefix>(?:^|\s)--?(?:api-key|access-key|secret-key|token|access-token|refresh-token|"
        r"client-secret|secret|password|passwd|pwd|passphrase|private-key)(?:=|\s+))(?P<secret>[^\s'\"&;]+)"
    ),
    re.compile(r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)(?P<secret>[^@\s/]+)(?P<suffix>@)", re.IGNORECASE),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9_]{36}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22}_[A-Za-z0-9_]{59}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
]


def redact_text(value: str, secrets: Sequence[str] | None = None) -> str:
    redacted = value
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


def redact_payload(value: Any, secrets: Sequence[str] | None = None) -> Any:
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, Mapping):
        return {
            key: _redact_sensitive_value(item) if _is_sensitive_key(key) and item not in (None, "") else redact_payload(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(item, secrets) for item in value)
    return value


def _redact_match(match: re.Match[str]) -> str:
    groups = match.groupdict()
    prefix = groups.get("prefix")
    if prefix is None:
        return REDACTED
    return f"{prefix}{REDACTED}{groups.get('suffix') or ''}"


def _is_sensitive_key(key: Any) -> bool:
    return bool(SENSITIVE_KEY_PATTERN.search(str(key)))


def _redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _redact_sensitive_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_value(item) for item in value)
    return REDACTED
