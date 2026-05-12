"""End-to-end integration tests for Argument Companion v3.

Tests all /api/companion/* endpoints via TestClient (no live server).
Only `call_llm_chat` is mocked; real business logic (store saves, anchor
creation, promise extraction, SSE serialisation) runs end-to-end.

Coverage:
  Ledger:  build (SSE), GET, upsert-promise, delete-promise, relocate, delete
  Review:  run (SSE), GET, list, update-point-status, rebut (SSE), delete
  Phase5:  import-real-reviews (SSE), download (FileResponse), suggest-experiment
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ── Config fixture ────────────────────────────────────────────────────────────

MINIMAL_CONFIG = """\
translator:
  engine: ollama
  model: qwen3:8b
  ollama_base_url: http://localhost:11434
  temperature: 0.3
  timeout: 300.0
chunker:
  max_tokens: 2048
  overlap_tokens: 128
formatter:
  output_format: bilingual
agent:
  model: qwen3:8b
  max_steps: 3
features:
  argument_companion: true
"""


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api_factory import create_app

    test_dir = tempfile.mkdtemp()
    config_dir = Path(test_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "default.yaml").write_text(MINIMAL_CONFIG, encoding="utf-8")

    with patch("api_factory.CONFIG_PATH", config_dir / "default.yaml"):
        with patch("api_factory.RUNTIME_DIR", Path(test_dir)):
            with patch("api_factory.BASE_DIR", Path(test_dir)):
                app = create_app()
                c = TestClient(app, raise_server_exceptions=True)
                yield c

    shutil.rmtree(test_dir, ignore_errors=True)


# ── LLM mock helpers ──────────────────────────────────────────────────────────

# Canned LLM responses for build_ledger (2 sequential calls)
_LEDGER_PROMISE_JSON = json.dumps({
    "promises": [{
        "local_id": "p1",
        "kind": "contribution",
        "text": "We propose a novel method",
        "verbatim_quote": "We propose a novel method",
    }]
})
_LEDGER_DISCHARGE_JSON = json.dumps([{
    "promise_local_id": "p1",
    "status": "unpaid",
    "discharge_quotes": [],
    "note": "Not demonstrated in body",
}])

# Canned LLM response for run_review (2 sequential calls: coherence + main)
_REVIEW_COHERENCE_JSON = "[]"
_REVIEW_MAIN_JSON = json.dumps([{
    "category": "baseline",
    "severity": "major",
    "title": "Weak baselines",
    "detail": "The paper compares against outdated baselines.",
    "verbatim_quote": "",
}])

# Canned LLM response for import_real_reviews (1 call)
_IMPORT_JSON = json.dumps([{
    "reviewer_label": "Reviewer 1",
    "severity": "major",
    "category": "baseline",
    "title": "Weak baselines",
    "detail": "Need stronger baselines.",
    "quote_from_paper": "",
}])

# Canned LLM response for rebuttal (1 call)
_REBUTTAL_JSON = "Fair point, but our 2024 baselines are competitive."

# Canned LLM response for suggest_experiment (1 call)
_SUGGEST_JSON = "Run ablation: remove the novel component and compare FLOPs."


def _ledger_llm_side_effect():
    """Sequential LLM mock for build_ledger: call1=promises, call2=discharge."""
    calls = [_LEDGER_PROMISE_JSON, _LEDGER_DISCHARGE_JSON]
    it = iter(calls)
    async def _mock(prompt, *args, **kwargs):
        try:
            return next(it)
        except StopIteration:
            return "[]"
    return _mock


def _review_llm_side_effect():
    """Sequential LLM mock for run_review: call1=coherence, call2=main review."""
    calls = [_REVIEW_COHERENCE_JSON, _REVIEW_MAIN_JSON]
    it = iter(calls)
    async def _mock(prompt, *args, **kwargs):
        try:
            return next(it)
        except StopIteration:
            return "[]"
    return _mock


# ── SSE response parser ───────────────────────────────────────────────────────

def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE response text into list of {event, data} dicts."""
    events: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            raw = line[len("data:"):].strip()
            try:
                current["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current["data"] = raw
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


# ── Shared mutable state (populated by earlier tests in each class) ───────────

_state: dict = {}

DOC_ID = "e2e_test_doc"
DOC_TITLE = "E2E Test Paper"
DOC_TEXT = (
    "We propose a novel method (Contribution). "
    "Our model achieves state-of-the-art results on benchmark X (Claim). "
    "We hypothesize that sparse attention reduces compute (Hypothesis). "
    "In experiments we verify the claim. "
    "Results show 5% improvement."
)


# ── 1. Ledger endpoints ───────────────────────────────────────────────────────

class TestLedgerEndpoints:

    def test_build_ledger_sse_200(self, client):
        mock = _ledger_llm_side_effect()
        with patch("src.argument.ledger.call_llm_chat", mock):
            resp = client.post(
                "/api/companion/ledger/build",
                json={"doc_id": DOC_ID, "doc_title": DOC_TITLE, "text": DOC_TEXT},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_sse(resp.text)
        types = [e.get("event") for e in events]
        assert "promise" in types or "complete" in types, f"No promise/complete in {types}"

    def test_build_ledger_stores_promise(self, client):
        """After build, GET ledger should return promises stored by real build_ledger."""
        mock = _ledger_llm_side_effect()
        with patch("src.argument.ledger.call_llm_chat", mock):
            client.post(
                "/api/companion/ledger/build",
                json={"doc_id": DOC_ID, "doc_title": DOC_TITLE, "text": DOC_TEXT},
            )
        resp = client.get(f"/api/companion/ledger/{DOC_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_id"] == DOC_ID
        assert len(data["promises"]) >= 1
        _state["promise_id"] = data["promises"][0]["id"]

    def test_get_ledger_404_unknown_doc(self, client):
        resp = client.get("/api/companion/ledger/no_such_doc_xyz")
        assert resp.status_code == 404

    def test_upsert_promise(self, client):
        resp = client.put(
            f"/api/companion/ledger/{DOC_ID}/promise",
            json={
                "text": "Manual promise for testing",
                "kind": "claim",
                "source_anchor_id": "a_manual",
                "status": "unpaid",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Manual promise for testing"
        assert data["user_overridden"] is True
        _state["manual_promise_id"] = data["id"]

    def test_delete_promise(self, client):
        pid = _state.get("manual_promise_id")
        if not pid:
            pytest.skip("No manual promise created")
        resp = client.delete(f"/api/companion/ledger/{DOC_ID}/promise/{pid}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_relocate(self, client):
        resp = client.post(
            f"/api/companion/ledger/{DOC_ID}/relocate",
            json={"text": DOC_TEXT + " (updated)"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_id"] == DOC_ID


# ── 2. Review endpoints ───────────────────────────────────────────────────────

class TestReviewEndpoints:

    def test_run_review_sse_200(self, client):
        mock = _review_llm_side_effect()
        with patch("src.argument.reviewer.call_llm_chat", mock):
            resp = client.post(
                "/api/companion/review",
                json={
                    "doc_id": DOC_ID,
                    "doc_title": DOC_TITLE,
                    "text": DOC_TEXT,
                    "venue": "NeurIPS",
                    "persona": "reviewer2",
                },
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_sse(resp.text)
        types = [e.get("event") for e in events]
        assert "complete" in types, f"No complete event in {types}"

        # Grab session_id from complete event for downstream tests
        complete_ev = next(e for e in events if e.get("event") == "complete")
        data = complete_ev["data"]
        if isinstance(data, dict):
            sid = data.get("session_id")
        else:
            # data is a JSON string that failed to parse
            sid = json.loads(data).get("session_id") if isinstance(data, str) else None
        assert sid, f"No session_id in complete event: {complete_ev}"
        _state["session_id"] = sid

    def test_review_has_at_least_one_point(self, client):
        """The deterministic rw_check adds 'no Related Work section' → at least 1 point."""
        sid = _state.get("session_id")
        if not sid:
            pytest.skip("No session created")
        resp = client.get(f"/api/companion/review/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == sid
        assert len(data["points"]) >= 1
        _state["point_id"] = data["points"][0]["id"]

    def test_get_review_session_404(self, client):
        resp = client.get("/api/companion/review/no_such_session_xyz")
        assert resp.status_code == 404

    def test_list_reviews(self, client):
        resp = client.get(f"/api/companion/reviews?doc_id={DOC_ID}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_update_point_status_accepted(self, client):
        sid = _state.get("session_id")
        pid = _state.get("point_id")
        if not sid or not pid:
            pytest.skip("No session/point created")
        resp = client.put(
            f"/api/companion/review/{sid}/point/{pid}",
            json={"status": "accepted"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_update_point_status_invalid(self, client):
        sid = _state.get("session_id")
        pid = _state.get("point_id")
        if not sid or not pid:
            pytest.skip("No session/point created")
        resp = client.put(
            f"/api/companion/review/{sid}/point/{pid}",
            json={"status": "invalid_status_xyz"},
        )
        assert resp.status_code == 422

    def test_rebut_sse_200(self, client):
        sid = _state.get("session_id")
        pid = _state.get("point_id")
        if not sid or not pid:
            pytest.skip("No session/point created")

        mock = AsyncMock(return_value=_REBUTTAL_JSON)
        with patch("src.argument.reviewer.call_llm_chat", mock):
            resp = client.post(
                f"/api/companion/review/{sid}/point/{pid}/rebut",
                json={"message": "We compare against SOTA 2024 baselines.", "text": DOC_TEXT},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_sse(resp.text)
        types = [e.get("event") for e in events]
        assert "reviewer_reply" in types or "complete" in types, f"Events: {types}"

    def test_rebut_404_missing_session(self, client):
        resp = client.post(
            "/api/companion/review/no_such_session/point/p1/rebut",
            json={"message": "test", "text": ""},
        )
        assert resp.status_code == 404


# ── 3. Phase 5 endpoints ──────────────────────────────────────────────────────

class TestPhase5Endpoints:

    def test_import_reviews_sse_200(self, client):
        mock = AsyncMock(return_value=_IMPORT_JSON)
        with patch("src.argument.reviewer.call_llm_chat", mock):
            resp = client.post(
                "/api/companion/review/import",
                json={
                    "doc_id": DOC_ID,
                    "doc_title": DOC_TITLE,
                    "text": DOC_TEXT,
                    "reviews_raw": "Reviewer 1: The baselines are not strong enough.",
                },
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_sse(resp.text)
        types = [e.get("event") for e in events]
        assert "review_point" in types, f"No review_point in {types}"
        assert "complete" in types, f"No complete in {types}"

        complete_ev = next(e for e in events if e.get("event") == "complete")
        data = complete_ev["data"]
        if isinstance(data, str):
            data = json.loads(data)
        sid = data.get("session_id")
        assert sid, f"No session_id: {complete_ev}"
        _state["imported_session_id"] = sid

    def test_import_reviews_422_missing_field(self, client):
        resp = client.post(
            "/api/companion/review/import",
            json={"doc_id": DOC_ID, "text": DOC_TEXT},  # missing reviews_raw
        )
        assert resp.status_code == 422

    def test_import_reviews_point_source_imported(self, client):
        sid = _state.get("imported_session_id")
        if not sid:
            pytest.skip("No imported session created")
        resp = client.get(f"/api/companion/review/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        sources = [p["source"] for p in data["points"]]
        assert all(s == "imported" for s in sources), f"Expected imported, got {sources}"

    def test_import_reviews_reviewer_label_set(self, client):
        sid = _state.get("imported_session_id")
        if not sid:
            pytest.skip("No imported session created")
        resp = client.get(f"/api/companion/review/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        labels = [p.get("reviewer_label") for p in data["points"]]
        assert any(l is not None for l in labels), f"No reviewer_label set: {labels}"

    def test_download_review_200(self, client):
        sid = _state.get("session_id")
        if not sid:
            pytest.skip("No review session created")
        resp = client.get(f"/api/companion/download/review/{sid}")
        assert resp.status_code == 200
        # Content should be markdown — at least contain session ID or a heading
        assert "#" in resp.text or sid in resp.text, "Response doesn't look like markdown"

    def test_download_review_404(self, client):
        resp = client.get("/api/companion/download/review/no_such_session_xyz")
        assert resp.status_code == 404

    def test_suggest_experiment_200(self, client):
        pid = _state.get("promise_id")
        if not pid:
            pytest.skip("No promise created")
        mock = AsyncMock(return_value=_SUGGEST_JSON)
        with patch("src.argument.ledger.suggest_experiment_for_promise", mock):
            resp = client.post(
                f"/api/companion/ledger/{DOC_ID}/promise/{pid}/suggest-experiment",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestion" in data
        assert len(data["suggestion"]) > 0

    def test_suggest_experiment_404_missing_ledger(self, client):
        resp = client.post(
            "/api/companion/ledger/no_such_doc/promise/p_fake/suggest-experiment",
        )
        assert resp.status_code == 404

    def test_suggest_experiment_404_missing_promise(self, client):
        resp = client.post(
            f"/api/companion/ledger/{DOC_ID}/promise/no_such_promise/suggest-experiment",
        )
        assert resp.status_code == 404


# ── 4. Ledger + review delete (teardown) ──────────────────────────────────────

class TestDeleteEndpoints:

    def test_delete_review_session(self, client):
        sid = _state.get("session_id")
        if not sid:
            pytest.skip("No session created")
        resp = client.delete(f"/api/companion/review/{sid}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_deleted_review_is_gone(self, client):
        sid = _state.get("session_id")
        if not sid:
            pytest.skip("No session to verify deletion")
        resp = client.get(f"/api/companion/review/{sid}")
        assert resp.status_code == 404

    def test_delete_ledger(self, client):
        resp = client.delete(f"/api/companion/ledger/{DOC_ID}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_ledger_404_after_delete(self, client):
        resp = client.delete(f"/api/companion/ledger/{DOC_ID}")
        assert resp.status_code == 404
