from pathlib import Path

from app.core.config import Settings
from app.core.errors import ConfigurationError


def candidate_private_key_paths(settings: Settings) -> list[Path]:
    try:
        settings.require_ssh_key()
    except RuntimeError as exc:
        raise ConfigurationError(str(exc)) from exc

    assert settings.ssh_private_key_path is not None
    configured_path = Path(settings.ssh_private_key_path).expanduser()
    if not configured_path.exists():
        raise ConfigurationError("Configured SSH private key path does not exist")

    candidates = [configured_path]
    for sibling in sorted(configured_path.parent.glob("*.pem")):
        if sibling.is_file() and sibling != configured_path:
            candidates.append(sibling)

    return candidates
