from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent_v2.router import _build_system_prompt, register_agent_v2_routes
from src.agent_v2.runtime.session import Session
from src.agent_v2.types import Message, MessageRole, TextBlock, ToolResultBlock, ToolUseBlock


def test_system_prompt_exposes_current_date_to_agent():
    prompt = _build_system_prompt("C:/workspace", [])

    assert f"Current date: {date.today().isoformat()}" in prompt


def test_persisted_session_messages_are_available_to_the_history_panel(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    session = Session(workspace="C:/paper", model="test-model", session_id="sess_history")
    session.append(Message(role=MessageRole.USER, blocks=[TextBlock(
        text="Review the draft\n\n<editor_context>private draft body</editor_context>",
    )]))
    session.append(Message(role=MessageRole.ASSISTANT, blocks=[
        ToolUseBlock(id="call_1", name="read_file", input='{"file_path":"draft.md"}'),
    ]))
    session.append(Message(role=MessageRole.TOOL, blocks=[
        ToolResultBlock(tool_use_id="call_1", tool_name="read_file", output="draft text"),
    ]))
    session.append(Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="Review complete")]))
    session.save(tmp_path / "sess_history.jsonl")

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path)
    app = FastAPI()
    register_agent_v2_routes(app)
    client = TestClient(app)

    history = client.get("/api/agent/v2/workflows/sess_history/messages")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Review the draft"
    assert "private draft body" not in messages[0]["content"]
    assert messages[1]["events"][0]["metadata"]["tool_name"] == "read_file"
    assert messages[2]["events"][0]["content"] == "draft text"
    assert messages[3]["content"] == "Review complete"

    listing = client.get("/api/agent/v2/sessions")
    assert listing.status_code == 200
    summary = listing.json()[0]
    assert summary["id"] == "sess_history"
    assert summary["query"] == "Review the draft"
    assert summary["messages"] == 4


def test_session_history_rejects_invalid_or_missing_ids(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path)
    app = FastAPI()
    register_agent_v2_routes(app)
    client = TestClient(app)

    assert client.get("/api/agent/v2/workflows/invalid%20id/messages").status_code == 400
    assert client.get("/api/agent/v2/workflows/sess_missing/messages").status_code == 404
