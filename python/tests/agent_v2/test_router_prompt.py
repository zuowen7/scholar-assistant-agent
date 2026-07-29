from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent_v2.router import _build_system_prompt, register_agent_v2_routes
from src.agent_v2.runtime.session import Session
from src.agent_v2.types import Message, MessageRole, TextBlock, ToolResultBlock, ToolUseBlock


def test_system_prompt_exposes_current_date_to_agent():
    prompt = _build_system_prompt("C:/workspace", [])

    assert f"Current date: {date.today().isoformat()}" in prompt


def test_system_prompt_makes_the_latest_user_turn_authoritative():
    prompt = _build_system_prompt("C:/workspace", [])

    assert "latest user message is the active task" in prompt
    assert "Do not resume unrelated unfinished work" in prompt
    assert "run_sub_agent cannot execute commands" in prompt


def test_persisted_session_messages_are_available_to_the_history_panel(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    session = Session(workspace="C:/paper", model="test-model", session_id="sess_history")
    session.append(
        Message(
            role=MessageRole.USER,
            blocks=[
                TextBlock(
                    text="Review the draft\n\n<editor_context>private draft body</editor_context>",
                )
            ],
        )
    )
    session.append(
        Message(
            role=MessageRole.ASSISTANT,
            blocks=[
                TextBlock(text="Review is already complete."),
                ToolUseBlock(id="call_1", name="read_file", input='{"file_path":"draft.md"}'),
            ],
        )
    )
    session.append(
        Message(
            role=MessageRole.TOOL,
            blocks=[
                ToolResultBlock(tool_use_id="call_1", tool_name="read_file", output="draft text"),
            ],
        )
    )
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
    assert len(messages) == 2
    assert messages[1]["content"] == "Review complete"
    assert messages[1]["events"][0]["metadata"]["tool_name"] == "read_file"
    assert messages[1]["events"][0]["event_id"] == "call_1"
    assert messages[1]["events"][1]["content"] == "draft text"
    assert messages[1]["events"][1]["event_id"] == "call_1"

    listing = client.get("/api/agent/v2/sessions")
    assert listing.status_code == 200
    summary = listing.json()[0]
    assert summary["id"] == "sess_history"
    assert summary["query"] == "Review the draft"
    assert summary["messages"] == 4


def test_partial_session_history_keeps_structured_recovery_state(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    session = Session(workspace="C:/paper", model="test-model", session_id="sess_partial")
    session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="Create two figures")]))
    session.append(
        Message(
            role=MessageRole.ASSISTANT,
            blocks=[
                ToolUseBlock(
                    id="call_1",
                    name="write_file",
                    input='{"file_path":"figures.py","content":"..."}',
                )
            ],
        )
    )
    session.append(
        Message(
            role=MessageRole.TOOL,
            blocks=[
                ToolResultBlock(
                    tool_use_id="call_1",
                    tool_name="write_file",
                    output="ok",
                )
            ],
        )
    )
    session.set_outcome(
        "PARTIAL",
        {
            "stop_code": "model_call_budget_exhausted",
            "stop_reason": "Agent model-call limit reached (16) before completion.",
            "tool_counts": {
                "success": 1,
                "error": 0,
                "denied": 0,
                "skipped": 0,
                "no_change": 0,
            },
            "changed_files": ["C:/paper/figures.py"],
            "unexecuted": [],
        },
    )
    session.save(tmp_path / "sess_partial.jsonl")

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path)
    app = FastAPI()
    register_agent_v2_routes(app)
    messages = (
        TestClient(app).get("/api/agent/v2/workflows/sess_partial/messages").json()["messages"]
    )

    assistant = messages[-1]
    response = assistant["events"][-1]
    assert response["type"] == "response"
    assert response["metadata"]["partial"] is True
    assert response["metadata"]["stop_code"] == "model_call_budget_exhausted"
    assert response["metadata"]["changed_count"] == 1
    assert "C:/paper/figures.py" not in assistant["content"]


def test_session_history_rejects_invalid_or_missing_ids(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path)
    app = FastAPI()
    register_agent_v2_routes(app)
    client = TestClient(app)

    assert client.get("/api/agent/v2/workflows/invalid%20id/messages").status_code == 400
    assert client.get("/api/agent/v2/workflows/sess_missing/messages").status_code == 404


def test_agent_stats_reports_runtime_budget_config(monkeypatch):
    import src.agent_v2.router as router

    monkeypatch.setattr(
        router,
        "_load_agent_config",
        lambda: {
            "model": "test",
            "provider": "mock",
            "max_steps": 41,
            "max_tool_calls": 17,
            "soft_tool_calls": 13,
            "max_model_calls": 9,
            "max_mutation_attempts": 7,
            "max_active_seconds": 123,
        },
    )
    app = FastAPI()
    register_agent_v2_routes(app)

    stats = TestClient(app).get("/api/agent/stats")

    assert stats.status_code == 200
    assert stats.json()["max_steps"] == 41
    assert stats.json()["max_tool_calls"] == 17
    assert stats.json()["soft_tool_calls"] == 13
    assert stats.json()["max_model_calls"] == 9
    assert stats.json()["max_mutation_attempts"] == 7
    assert stats.json()["max_active_seconds"] == 123


def test_session_path_rejects_traversal(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path)
    with pytest.raises(ValueError, match="Invalid session id"):
        router._session_path(r"..\outside")

    app = FastAPI()
    register_agent_v2_routes(app)
    client = TestClient(app)
    assert client.get("/api/agent/v2/cost/..%5Coutside").status_code == 400


def test_chat_rejects_workspace_that_does_not_match_server_grant(tmp_path):
    from src.agent_v2.runtime.workspace_grants import install_workspace_grants

    granted = tmp_path / "granted"
    other = tmp_path / "other"
    granted.mkdir()
    other.mkdir()
    app = FastAPI()
    token = install_workspace_grants(app).issue(granted)
    register_agent_v2_routes(app)

    response = TestClient(app).post(
        "/api/agent/v2/chat",
        json={
            "message": "read files",
            "workspace_root": str(other),
            "workspace_grant": token,
        },
    )

    assert response.status_code == 403
    assert "does not match" in response.json()["detail"]


def test_session_routes_require_and_filter_by_server_workspace_grant(tmp_path, monkeypatch):
    import src.agent_v2.router as router
    from src.agent_v2.runtime.workspace_grants import install_workspace_grants

    sessions_dir = tmp_path / "sessions"
    granted = tmp_path / "granted"
    other = tmp_path / "other"
    sessions_dir.mkdir()
    granted.mkdir()
    other.mkdir()
    Session(workspace=str(granted), session_id="sess_granted").save(
        sessions_dir / "sess_granted.jsonl"
    )
    Session(workspace=str(other), session_id="sess_other").save(sessions_dir / "sess_other.jsonl")
    monkeypatch.setattr(router, "_SESSION_DIR", sessions_dir)
    router._SESSION_POOL.clear()

    app = FastAPI()
    token = install_workspace_grants(app).issue(granted)
    register_agent_v2_routes(app)
    client = TestClient(app)
    headers = {"X-Workspace-Grant": token}

    assert client.get("/api/agent/v2/sessions").status_code == 403
    listing = client.get("/api/agent/v2/sessions", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == ["sess_granted"]

    own_history = client.get("/api/agent/v2/workflows/sess_granted/messages", headers=headers)
    assert own_history.status_code == 200
    assert (
        client.get("/api/agent/v2/workflows/sess_other/messages", headers=headers).status_code
        == 403
    )
    assert client.get("/api/agent/v2/cost/sess_other", headers=headers).status_code == 403
    assert client.delete("/api/agent/v2/workflows/sess_other", headers=headers).status_code == 403
    assert (sessions_dir / "sess_other.jsonl").is_file()


def test_generated_session_ids_are_unique(tmp_path, monkeypatch):
    import src.agent_v2.router as router
    from src.agent_v2.providers.mock_provider import MockProvider

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path)

    def provider():
        value = MockProvider()
        value.model = "test-model"
        return value

    monkeypatch.setattr(router, "_create_provider", provider)
    monkeypatch.setattr(
        router,
        "_load_agent_config",
        lambda: {
            "max_steps": 48,
            "max_tool_calls": 32,
            "soft_tool_calls": 28,
            "enable_run_command": False,
        },
    )
    first = router._create_runtime(str(tmp_path))
    second = router._create_runtime(str(tmp_path))

    assert first.session.session_id != second.session.session_id
    assert first.session._save_path != second.session._save_path
    assert first.tool_registry.get("run_command") is None
    assert "run_command" not in first.system_prompt


def test_selected_figure_skill_exposes_approved_command_execution(tmp_path, monkeypatch):
    import src.agent_v2.router as router
    from src.agent_v2.providers.mock_provider import MockProvider

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path / "sessions")

    def provider():
        value = MockProvider()
        value.model = "test-model"
        return value

    monkeypatch.setattr(router, "_create_provider", provider)
    monkeypatch.setattr(
        router,
        "_load_agent_config",
        lambda: {
            "max_steps": 48,
            "max_tool_calls": 32,
            "soft_tool_calls": 28,
            "enable_run_command": False,
        },
    )

    runtime = router._create_runtime(
        str(tmp_path),
        selected_skills=["nature_figure"],
    )

    assert runtime.tool_registry.get("run_command") is not None
    assert "run_command" in runtime.system_prompt


_RUNTIME_SKILL_TOOL_CONTRACTS = [
    ("academic_writing", {"read_file"}),
    ("paper_review", {"read_file", "read_argument_ledger"}),
    ("latex_formatting", {"read_file", "export_document"}),
    ("chinese_academic", {"read_file"}),
    ("methodology_critique", {"read_file"}),
    ("nature_writing", {"read_file", "write_file"}),
    ("nature_polishing", {"read_file", "write_file"}),
    (
        "nature_reviewer",
        {"read_argument_graph", "read_argument_ledger", "read_reviewer_state"},
    ),
    ("nature_response", {"read_file", "write_file", "read_reviewer_state"}),
    ("nature_citation", {"arxiv_search", "rag_search", "web_search", "web_fetch"}),
    ("nature_data", {"read_file", "write_file"}),
    (
        "nature_reader",
        {"read_file", "write_file", "translate_document", "export_document"},
    ),
    ("nature_figure", {"read_file", "write_file", "run_command"}),
    ("thesis_writing", {"read_file", "write_file"}),
]


def test_runtime_skill_contract_matrix_covers_every_skill_exposed_by_the_ui():
    import src.agent_v2.router as router
    from src.agent_v2.skills import _BUILTIN_SKILLS, SkillRegistry

    registry = SkillRegistry()
    for skill in _BUILTIN_SKILLS:
        registry.register(skill)
    registry.load_dir(router._RUNTIME_DIR / "data" / "agent_v2" / "skills")

    exposed = {item["name"] for item in registry.list_all()}
    covered = {name for name, _required_tools in _RUNTIME_SKILL_TOOL_CONTRACTS}

    assert covered == exposed


@pytest.mark.parametrize(("skill_name", "required_tools"), _RUNTIME_SKILL_TOOL_CONTRACTS)
def test_every_runtime_skill_is_selectable_with_its_runtime_tools(
    skill_name, required_tools, tmp_path, monkeypatch
):
    """Contract smoke test for every skill exposed by the Agent UI."""
    import src.agent_v2.router as router
    from src.agent_v2.providers.mock_provider import MockProvider

    monkeypatch.setattr(router, "_SESSION_DIR", tmp_path / "sessions")

    def provider():
        value = MockProvider()
        value.model = "test-model"
        return value

    monkeypatch.setattr(router, "_create_provider", provider)
    monkeypatch.setattr(
        router,
        "_load_agent_config",
        lambda: {
            "max_steps": 96,
            "max_tool_calls": 64,
            "soft_tool_calls": 56,
            "max_model_calls": 32,
            "enable_run_command": False,
        },
    )

    runtime = router._create_runtime(
        str(tmp_path),
        selected_skills=[skill_name],
    )

    assert f"<!-- SKILL: {skill_name} (agents) -->" in runtime.system_prompt
    assert required_tools <= {definition.name for definition in runtime.tool_registry.definitions()}


def test_undo_route_restores_persisted_session_after_restart(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    sessions_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.md"
    target.write_text("after", encoding="utf-8")
    session = Session(
        workspace=str(workspace),
        model="test-model",
        session_id="sess_undo",
    )
    session.record_mutation(
        turn_id="turn-1",
        tool_use_id="write-1",
        path=target,
        before_exists=True,
        before_content="before",
        after_content="after",
    )
    sessions_dir.mkdir()
    session.save(sessions_dir / "sess_undo.jsonl")

    monkeypatch.setattr(router, "_SESSION_DIR", sessions_dir)
    app = FastAPI()
    register_agent_v2_routes(app)
    response = TestClient(app).post("/api/agent/v2/undo/sess_undo")

    assert response.status_code == 200
    assert response.json()["restored_files"] == [str(target.resolve())]
    assert target.read_text(encoding="utf-8") == "before"


def test_undo_route_reports_conflict_without_overwriting_user_edit(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    sessions_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.md"
    target.write_text("user edit", encoding="utf-8")
    session = Session(
        workspace=str(workspace),
        model="test-model",
        session_id="sess_conflict",
    )
    session.record_mutation(
        turn_id="turn-1",
        tool_use_id="write-1",
        path=target,
        before_exists=True,
        before_content="before",
        after_content="agent edit",
    )
    sessions_dir.mkdir()
    session.save(sessions_dir / "sess_conflict.jsonl")

    monkeypatch.setattr(router, "_SESSION_DIR", sessions_dir)
    app = FastAPI()
    register_agent_v2_routes(app)
    response = TestClient(app).post("/api/agent/v2/undo/sess_conflict")

    assert response.status_code == 409
    assert target.read_text(encoding="utf-8") == "user edit"


def test_cloud_config_applies_environment_api_key(tmp_path, monkeypatch):
    import src.agent_v2.router as router

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "translator:\n  cloud:\n    api_key: file-key\n", encoding="utf-8"
    )
    monkeypatch.setattr(router, "_RUNTIME_DIR", tmp_path)
    monkeypatch.setenv("SCHOLAR_CLOUD_API_KEY", "environment-key")

    assert router._load_cloud_config()["api_key"] == "environment-key"


def test_cloud_fallback_propagates_thinking_mode_and_request_timeout():
    from src.agent_v2.router import _create_provider

    provider = _create_provider(
        {
            "agent": {
                "provider": "auto",
                "thinking_mode": "enabled",
                "request_timeout": 42,
            },
            "translator": {
                "cloud": {
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "test-key",
                    "model": "deepseek-v4-flash",
                }
            },
        }
    )

    assert provider.thinking_mode == "enabled"
    assert provider.timeout == 42
