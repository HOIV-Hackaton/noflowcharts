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
    try:
        configured_path_exists = configured_path.exists()
    except PermissionError:
        configured_path_exists = True

    if not configured_path_exists:
        raise ConfigurationError("Configured SSH private key path does not exist")

    candidates = [configured_path]
    try:
        siblings = sorted(configured_path.parent.glob("*.pem"))
    except PermissionError:
        siblings = []
    for sibling in siblings:
        try:
            is_file = sibling.is_file()
        except PermissionError:
            is_file = True
        if is_file and sibling != configured_path:
            candidates.append(sibling)

    return candidates
