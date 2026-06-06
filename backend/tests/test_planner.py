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


def test_planner_rejects_invalid_provider_payload():
    planner = Planner(provider=FakeProvider({"command": "uptime"}))

    with pytest.raises(AgentError):
        planner.propose_next_command({}, {}, [], "policy")
