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


class QueueProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.messages = []

    def complete_json(self, messages, timeout=30.0):
        self.messages.append(messages)
        return self.payloads.pop(0)


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


def test_diagnosis_agent_can_handoff_to_execution_agent():
    provider = QueueProvider(
        [
            {"mode": "handoff_to_execution", "reason": "nginx is inactive and should be started"},
            {
                "intent": "Start nginx after diagnosis showed it is inactive.",
                "command": "systemctl start nginx",
                "expected_signal": "systemctl exits successfully and nginx can be validated next.",
                "risk_level": "medium",
                "command_class_hint": "mutating",
                "phase": "fix",
                "rollback_note": "Stop nginx again if this reveals an incorrect target service.",
            },
        ]
    )

    proposal = Planner(provider=provider).propose_diagnosis_command({"title": "API down"}, {}, [], "policy")

    assert proposal.command == "systemctl start nginx"
    assert "diagnosis agent" in provider.messages[0][0]["content"]
    assert "execution agent" in provider.messages[1][0]["content"]
    assert "nginx is inactive" in provider.messages[1][1]["content"]


def test_execution_agent_returns_to_diagnosis_when_fix_would_be_premature():
    provider = QueueProvider(
        [
            {
                "mode": "needs_more_diagnosis",
                "reason": "The failing service name is still unknown.",
                "diagnostic_question": "Which systemd unit owns the failing API port?",
            },
            {
                "intent": "Find the service listening near the reported API port before changing anything.",
                "command": "ss -ltnp",
                "expected_signal": "Output identifies the process and port ownership.",
                "risk_level": "low",
                "command_class_hint": "read_only",
                "phase": "diagnose",
            },
        ]
    )

    proposal = Planner(provider=provider).propose_execution_command({"title": "API down"}, {}, [], "policy")

    assert proposal.command == "ss -ltnp"
    assert "execution agent" in provider.messages[0][0]["content"]
    assert "diagnosis agent" in provider.messages[1][0]["content"]
    assert "Which systemd unit" in provider.messages[1][1]["content"]


def test_verification_agent_failure_always_returns_to_diagnosis():
    provider = QueueProvider(
        [
            {
                "mode": "return_to_diagnosis",
                "reason": "Health check still returns 503 after the fix.",
                "diagnostic_question": "Why does the service still return 503?",
            },
            {
                "intent": "Inspect recent service logs because verification still fails.",
                "command": "journalctl -u nginx -n 80 --no-pager",
                "expected_signal": "Logs identify the remaining failure cause.",
                "risk_level": "low",
                "command_class_hint": "read_only",
                "phase": "diagnose",
            },
        ]
    )

    proposal = Planner(provider=provider).propose_verification_command({"title": "API down"}, {}, [], "policy")

    assert proposal.command == "journalctl -u nginx -n 80 --no-pager"
    assert "verification agent" in provider.messages[0][0]["content"]
    assert "diagnosis agent" in provider.messages[1][0]["content"]
    assert "Health check still returns 503" in provider.messages[1][1]["content"]
