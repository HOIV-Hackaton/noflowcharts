import pytest

from app.core.errors import SafetyError
from app.services.diagnostic_policy import build_diagnostic_command, redact_diagnostic_output


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        ("get_uptime", {}, "uptime"),
        ("get_service_status", {"service": "nginx.service"}, "systemctl --no-pager status nginx.service"),
        ("get_recent_journal", {"service": "nginx", "lines": 50}, "journalctl -u nginx -n 50 --no-pager"),
        ("curl_local", {"port": 8080, "path": "/health"}, "curl --max-time 5 -fsS http://localhost:8080/health"),
        ("read_text_file", {"path": "/srv/app/.env", "max_lines": 40}, "head -n 40 /srv/app/.env"),
        ("grep_file", {"path": "/etc/nginx/nginx.conf", "pattern": "listen", "max_matches": 5}, "grep -n -E -m 5 listen /etc/nginx/nginx.conf"),
        ("grep_directory", {"path": "/srv/app/config", "pattern": "PORT", "max_matches": 10}, "grep -R -n -E -m 10 PORT /srv/app/config"),
    ],
)
def test_safe_diagnostic_tools_build_bounded_commands(tool, arguments, expected):
    result = build_diagnostic_command(tool, arguments)

    assert result.command == expected


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_service_status", {"service": "nginx; restart"}),
        ("get_recent_journal", {"service": "nginx", "lines": 1000}),
        ("curl_local", {"url": "http://example.com/health"}),
        ("curl_local", {"url": "http://localhost:8080/admin?token=abc"}),
        ("read_text_file", {"path": "/home/azureuser/.ssh/id_rsa"}),
        ("read_text_file", {"path": "/etc/shadow"}),
        ("read_text_file", {"path": "/proc/123/environ"}),
        ("read_text_file", {"path": "/run/secrets/api"}),
        ("read_text_file", {"path": "/srv/app/private.pem"}),
        ("grep_file", {"path": "/etc/nginx/nginx.conf", "pattern": "foo; rm -rf /"}),
        ("grep_directory", {"path": "/etc", "pattern": "PORT"}),
        ("systemctl_restart", {"service": "nginx"}),
    ],
)
def test_unsafe_diagnostic_requests_are_blocked(tool, arguments):
    with pytest.raises(SafetyError):
        build_diagnostic_command(tool, arguments)


def test_diagnostic_output_redacts_sensitive_env_values_but_keeps_safe_values():
    output = """PORT=8080
HOST=127.0.0.1
DB_PASSWORD=hunter2
API_TOKEN=abc123
PRIVATE_KEY=secret
DATABASE_URL=postgres://app:supersecret@localhost/app
-----BEGIN OPENSSH PRIVATE KEY-----
abc
-----END OPENSSH PRIVATE KEY-----"""

    redacted = redact_diagnostic_output(output)

    assert "PORT=8080" in redacted
    assert "HOST=127.0.0.1" in redacted
    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "supersecret" not in redacted
    assert "BEGIN OPENSSH PRIVATE KEY" not in redacted
    assert "DB_PASSWORD=[REDACTED]" in redacted
