import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password|passwd|pwd)\s*[=:]\s*)[^\s'\"&]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password|passwd|pwd)\s*:\s*)[^\n,}]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?im)^(\s*[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PWD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*=\s*).+$"),
    re.compile(r"(?is)-----BEGIN [^-]*-----.*?-----END [^-]*-----"),
]


def redact_text(value: str, secrets: Sequence[str] | None = None) -> str:
    redacted = value
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}{REDACTED}" if match.lastindex else REDACTED, redacted)
    return redacted


def redact_payload(value: Any, secrets: Sequence[str] | None = None) -> Any:
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, Mapping):
        return {key: redact_payload(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(item, secrets) for item in value)
    return value
