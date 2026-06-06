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


def test_planner_rejects_invalid_provider_payload():
    planner = Planner(provider=FakeProvider({"command": "uptime"}))

    with pytest.raises(AgentError):
        planner.propose_next_command({}, {}, [], "policy")
