"""Academic Agent tool registration regressions."""

import json

import pytest

from src.agent_v2.tools.academic_tools import register_academic_tools
from src.agent_v2.tools.registry import ToolRegistry


@pytest.fixture()
def registry(tmp_path):
    value = ToolRegistry(workspace_root=tmp_path)
    register_academic_tools(value)
    return value


def test_argument_companion_tools_are_registered_as_read_only(registry):
    names = {definition.name for definition in registry.definitions()}
    permissions = dict(registry.permission_specs())

    assert {"read_argument_graph", "read_argument_ledger", "read_reviewer_state"} <= names
    assert permissions["read_argument_graph"] == "read-only"
    assert permissions["read_argument_ledger"] == "read-only"
    assert permissions["read_reviewer_state"] == "read-only"


@pytest.mark.asyncio
async def test_ledger_and_reviewer_tools_require_a_real_identifier(registry):
    ledger = await registry.execute("read_argument_ledger", {})
    reviewer = await registry.execute("read_reviewer_state", {})

    assert ledger.is_error is True
    assert "doc_id is required" in ledger.output
    assert reviewer.is_error is True
    assert "session_id or doc_id is required" in reviewer.output


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    payloads = {}
    status_codes = {}

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, **_kwargs):
        if url.endswith("/api/companion/ledger"):
            key = "ledger"
        elif "/api/companion/review/" in url and "review_detail" in self.payloads:
            key = "review_detail"
        else:
            key = "review"
        return _FakeResponse(self.payloads[key], self.status_codes.get(key, 200))


@pytest.mark.asyncio
async def test_ledger_tool_returns_summary_then_cursor_pages_with_integrity_metadata(
    registry, monkeypatch, tmp_path
):
    import httpx

    doc = tmp_path / "draft" / "main.md"
    doc.parent.mkdir()
    doc.write_text("current manuscript", encoding="utf-8")
    _FakeAsyncClient.payloads = {
        "ledger": {
            "id": "L1",
            "doc_id": str(doc),
            "doc_hash": "stale-hash",
            "promises": [
                {"id": "p1", "text": "first"},
                {"id": "p2", "text": "second"},
                {"id": "p3", "text": "third"},
            ],
            "anchors": [],
        },
        "review": {},
    }
    _FakeAsyncClient.status_codes = {}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    summary = json.loads(
        (await registry.execute("read_argument_ledger", {"doc_id": str(doc)})).output
    )
    page = json.loads(
        (
            await registry.execute(
                "read_argument_ledger",
                {"doc_id": str(doc), "mode": "detail", "cursor": 0, "limit": 2},
            )
        ).output
    )

    assert summary["mode"] == "summary"
    assert summary["total_items"] == 3
    assert summary["source_version"]
    assert summary["stale"] is True
    assert summary["complete"] is False
    assert summary["next_cursor"] == 0
    assert page["complete"] is False
    assert page["returned_items"] == 2
    assert page["next_cursor"] == 2
    assert [item["id"] for item in page["items"]] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_reviewer_tool_can_fetch_selected_item_ids_without_registry_truncation(
    registry, monkeypatch
):
    import httpx

    _FakeAsyncClient.payloads = {
        "ledger": {},
        "review": {
            "id": "R1",
            "doc_id": "missing.md",
            "points": [
                {"id": "rp1", "title": "first"},
                {"id": "rp2", "title": "second"},
            ],
            "anchors": [],
        },
    }
    _FakeAsyncClient.status_codes = {}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await registry.execute(
        "read_reviewer_state",
        {"session_id": "R1", "mode": "detail", "item_ids": ["rp2"], "limit": 5},
    )
    payload = json.loads(result.output)

    assert result.truncated is False
    assert payload["complete"] is True
    assert payload["returned_items"] == 1
    assert payload["items"][0]["id"] == "rp2"


@pytest.mark.asyncio
async def test_missing_reviewer_state_is_a_successful_complete_absence(registry, monkeypatch):
    import httpx

    _FakeAsyncClient.payloads = {"ledger": {}, "review": {"detail": "not found"}}
    _FakeAsyncClient.status_codes = {"review": 404}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await registry.execute(
        "read_reviewer_state",
        {"doc_id": "draft/main.md"},
    )
    payload = json.loads(result.output)

    assert result.is_error is False
    assert result.metadata["available"] is False
    assert payload["available"] is False
    assert payload["complete"] is True
    assert payload["query"]["doc_id"] == "draft/main.md"


@pytest.mark.asyncio
async def test_doc_id_reviewer_lookup_expands_one_real_session(registry, monkeypatch):
    import httpx

    _FakeAsyncClient.payloads = {
        "ledger": {},
        "review": [{"session_id": "R_unique", "point_count": 1, "open_count": 1}],
        "review_detail": {
            "id": "R_unique",
            "doc_id": "draft/main.md",
            "doc_hash": "hash",
            "points": [
                {
                    "id": "rp1",
                    "severity": "major",
                    "title": "Missing comparison",
                }
            ],
            "anchors": [],
        },
    }
    _FakeAsyncClient.status_codes = {}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await registry.execute(
        "read_reviewer_state",
        {
            "doc_id": "draft/main.md",
            "mode": "detail",
            "collection": "points",
            "limit": 10,
        },
    )
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["source_id"] == "R_unique"
    assert payload["items"][0]["id"] == "rp1"
    assert payload["complete"] is True
