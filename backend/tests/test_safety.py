import pytest

from app.schemas.runs import CommandClassification
from app.services.safety import classify_command, ensure_command_allowed


def test_read_only_diagnostics_still_require_confirmation():
    result = classify_command("systemctl status nginx")

    assert result.classification == CommandClassification.READ_ONLY
    assert result.requires_confirmation is True
    assert result.requires_typed_confirmation is False


def test_mutating_targeted_command_requires_confirmation():
    result = classify_command("chown www-data:www-data /srv/app/uploads")

    assert result.classification == CommandClassification.MUTATING
    assert result.requires_confirmation is True
    assert result.blocked is False


def test_sudo_is_risky_and_requires_typed_confirmation():
    result = classify_command("sudo systemctl restart nginx")

    assert result.classification == CommandClassification.RISKY_MUTATING
    assert result.requires_typed_confirmation is True


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /etc",
        "chmod -R 777 /var",
        "systemctl disable ufw",
        "history -c",
        "cat /home/azureuser/.ssh/id_rsa",
    ],
)
def test_hard_fail_patterns_are_blocked(command):
    result = classify_command(command)

    assert result.classification == CommandClassification.BLOCKED
    assert result.blocked is True
    with pytest.raises(ValueError):
        ensure_command_allowed(command)


def test_edited_compound_command_is_risky_not_auto_allowed():
    result = classify_command("cat /etc/nginx/nginx.conf && systemctl restart nginx")

    assert result.classification == CommandClassification.RISKY_MUTATING
    assert result.requires_typed_confirmation is True
