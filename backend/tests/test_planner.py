import pytest

from app.agent.planner import Planner
from app.core.errors import AgentError
from app.schemas.runs import CommandClassification


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def complete_json(self, messages, timeout=30.0):
        self.messages = messages
        return self.payload


def test_planner_parses_one_command_proposal():
    provider = FakeProvider(
        {
            "intent": "Check nginx status",
            "command": "systemctl status nginx",
            "expected_signal": "Service is active or logs show failure cause",
            "risk_level": "low",
            "command_class_hint": "read_only",
        }
    )
    planner = Planner(provider=provider)

    proposal = planner.propose_next_command({"title": "API down"}, {"system": {"ip": "10.0.0.5"}}, [], "policy")

    assert proposal.command == "systemctl status nginx"
    assert proposal.command_class_hint == CommandClassification.READ_ONLY
    assert provider.messages[0]["role"] == "system"


def test_planner_prompt_encodes_conservative_diagnosis_policy():
    provider = FakeProvider(
        {
            "intent": "Check recent nginx failures before changing anything",
            "command": "journalctl -u nginx -n 80 --no-pager",
            "expected_signal": "Recent logs identify whether nginx failed because of configuration, port, or permission errors",
            "risk_level": "low",
            "command_class_hint": "read_only",
            "phase": "diagnose",
            "evidence_basis": "ticket symptom only",
            "evidence_gap": "service failure cause",
        }
    )
    planner = Planner(provider=provider)

    proposal = planner.propose_next_command({"title": "API down"}, {"system": {"ip": "10.0.0.5"}}, [], "policy")
    prompt = provider.messages[0]["content"]

    assert proposal.phase == "diagnose"
    assert "Do not assume context" in prompt
    assert "Diagnose before fixing" in prompt
    assert "Be very conservative with mutation" in prompt
    assert "must not use sudo" in prompt
    assert "Do not use &&, ||, ;, pipes" in prompt
    assert "hidden Linux service incidents" in prompt
    assert "phase, evidence_basis, evidence_gap" in prompt


def test_planner_prompt_includes_service_playbook_guidance():
    provider = FakeProvider(
        {
            "intent": "Check health",
            "command": "curl --max-time 5 -fsS http://localhost:8080/health",
            "expected_signal": "Returns ok",
        }
    )

    Planner(provider=provider).propose_next_command({}, {}, [], "policy")

    system_prompt = provider.messages[0]["content"]
    assert "Do not repeat a command" in system_prompt
    assert "Prefer read-only commands without sudo" in system_prompt
    assert "systemctl cat" in system_prompt
    assert "EnvironmentFile" in system_prompt
    assert "curl --max-time 5 -fsS" in system_prompt
    assert "explicit customer-facing health URL" in system_prompt
    assert "public validation command" in system_prompt


def test_planner_includes_anti_loop_context_for_recent_observations():
    provider = FakeProvider(
        {
            "intent": "Inspect the discovered customer status service instead of repeating listener checks",
            "command": "systemctl --no-pager status customer-status.service",
            "expected_signal": "Service state explains why port 8080 is not listening",
        }
    )
    observations = [
        {"command": "ss -ltn sport = :8080", "status": "completed", "exit_code": 0, "output": ""},
        {"command": "systemctl list-unit-files --type=service --all | grep -iE 'status|api'", "status": "completed", "exit_code": 0, "output": "customer-status.service disabled enabled"},
        {"command": "ss -ltn sport = :8080", "status": "completed", "exit_code": 0, "output": ""},
        {"command": "lsof -nP -iTCP:8080 -sTCP:LISTEN", "status": "rejected", "exit_code": None, "output": ""},
        {"source": "technician", "status": "guidance", "guidance": "try again, but don't use lsof"},
    ]

    Planner(provider=provider).propose_next_command({}, {}, observations, "policy")

    system_prompt = provider.messages[0]["content"]
    user_prompt = provider.messages[1]["content"]
    assert "anti_loop_context" in user_prompt
    assert "ss -ltn sport = :8080 returned no output" in user_prompt
    assert "'repeated_commands': ['ss -ltn sport = :8080']" in user_prompt
    assert "try again, but don't use lsof" in user_prompt
    assert "Treat successful empty output" in system_prompt
    assert "pivot to that resource" in system_prompt


def test_planner_includes_related_ticket_as_historical_context_only():
    provider = FakeProvider(
        {
            "intent": "Check nginx status before applying any prior fix",
            "command": "systemctl status nginx",
            "expected_signal": "Service state is visible",
        }
    )
    related_ticket = {
        "ticket_id": 7000,
        "title": "Prior API outage",
        "commands": ["sudo systemctl restart nginx"],
        "root_cause": "nginx proxy used the wrong port",
    }

    Planner(provider=provider).propose_next_command({}, {}, [], "policy", related_ticket=related_ticket)

    system_prompt = provider.messages[0]["content"]
    user_prompt = provider.messages[1]["content"]
    assert "historical assistance only" in system_prompt
    assert "Do not copy historical commands blindly" in system_prompt
    assert "'related_ticket':" in user_prompt
    assert "Prior API outage" in user_prompt


def test_planner_ignores_invalid_optional_command_class_hint():
    provider = FakeProvider(
        {
            "intent": "Check listening port",
            "command": "ss -ltnp | grep ':8080'",
            "expected_signal": "Shows whether a service listens on port 8080",
            "command_class_hint": "read-only network socket inspection",
        }
    )

    proposal = Planner(provider=provider).propose_next_command({}, {}, [], "policy")

    assert proposal.command == "ss -ltnp | grep ':8080'"
    assert proposal.command_class_hint is None


def test_planner_rejects_invalid_provider_payload():
    planner = Planner(provider=FakeProvider({"command": "uptime"}))

    with pytest.raises(AgentError):
        planner.propose_next_command({}, {}, [], "policy")
