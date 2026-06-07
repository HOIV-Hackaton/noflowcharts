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
        "rm -rf /",
        "rm -rf /home/customer",
        "rm -rf /srv/app",
        "rm -rf /var/lib/postgresql/15/main",
        "chmod -R 777 /var",
        "chmod -R 777 /",
        "chmod -R 777 /srv/app",
        "systemctl disable ufw",
        "sudo systemctl --now disable firewalld",
        "systemctl mask auditd",
        "ufw disable",
        "ufw --force reset",
        "iptables -F",
        "iptables --flush",
        "nft flush ruleset",
        "history -c",
        "rm -rf /var/log/nginx",
        "find /var/log -type f -delete",
        "shred -u /var/log/syslog",
        "truncate -s 0 /var/log/syslog",
        "cat /home/azureuser/.ssh/id_rsa",
        "cat /srv/app/.env",
        "grep SECRET /etc/app/config.pem",
        "dropdb customer_prod",
        "psql -c 'drop database customer_prod'",
        "rm -rf /var/lib/mysql",
        "rm -r -f /etc",
        "sudo rm --recursive --force -- /home/customer",
        "rm -rf --no-preserve-root /",
        "chmod --recursive 777 /etc",
        "chmod 777 -R /srv",
        "sudo chmod -Rf a+rwx /var",
        "sudo -u postgres psql -c 'alter user app superuser'",
        "journalctl -u nginx -f",
        "tail -f /var/log/syslog",
        "watch systemctl status nginx",
        "systemctl edit nginx",
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


@pytest.mark.parametrize(
    "command",
    [
        "psql -c 'select 1'",
        "psql --command '\\l'",
        "psql -Atc 'select count(*) from users'",
    ],
)
def test_bounded_psql_command_is_not_blocked_as_interactive(command):
    result = classify_command(command)

    assert result.classification == CommandClassification.RISKY_MUTATING
    assert result.requires_typed_confirmation is True
    assert result.blocked is False


def test_bare_psql_remains_blocked_as_interactive():
    result = classify_command("psql")

    assert result.classification == CommandClassification.BLOCKED
    assert result.blocked is True


@pytest.mark.parametrize(
    "command",
    [
        "chown www-data:www-data /srv/app/uploads",
        "chmod 750 /srv/app/uploads",
        "systemctl status nginx",
        "curl -fsS http://localhost/health",
    ],
)
def test_targeted_safeish_commands_remain_unblocked(command):
    result = classify_command(command)

    assert result.blocked is False
