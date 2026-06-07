import json
from pathlib import Path


def test_seed_knowledge_contains_one_completed_ticket_workflow():
    seed_path = Path(__file__).resolve().parents[1] / "seed_knowledge.json"
    items = json.loads(seed_path.read_text(encoding="utf-8"))

    assert len(items) == 5
    assert {item["ticket_id"] for item in items} == {7001}
    assert {item["chunk_type"] for item in items} == {"problem", "diagnosis", "commands", "fix", "validation"}

    combined = "\n".join(item["content"] for item in items)
    assert "Final status: DONE" in combined
    assert "audit trail" in combined
    assert "activity submitted" in combined.lower()
    assert "ticket status patched to DONE" in combined
    assert "Command:" in combined
    assert "Response snippet:" in combined
    assert "no secret output" in combined.lower()
    assert "Status API unavailable" in combined
    assert "Customer reports API is down" in combined
    assert "502 Bad Gateway" in combined
    assert "http://localhost:8080/health" in combined
    assert "after reboot" in combined
    assert "no listener on port 8080" in combined
    assert "startup persistence" in combined
    assert "&&" not in combined
