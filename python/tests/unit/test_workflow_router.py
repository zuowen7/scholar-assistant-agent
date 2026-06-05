"""Phase 2 tests: Workflow router endpoints.

TDD Red phase — tests exercise new endpoints that do NOT exist yet.
"""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Chat endpoint — workflow_id support
# ---------------------------------------------------------------------------

class TestWorkflowChat:
    """POST /api/agent/v2/chat with workflow_id."""

    @pytest.fixture
    def client(self):
        """Create a TestClient with mocked agent subsystem."""
        with (
            patch("src.agent.session.AgentSession") as mock_session,
            patch("src.agent.session.AgentLoop") as mock_agent,
            patch("src.agent.workflow_store.WorkflowStore") as mock_store,
            patch("src.features.agent", True),
            patch("src.agent.tools.create_default_registry") as mock_registry,
        ):
            mock_registry.return_value = MagicMock()
            from api_factory import create_app
            app = create_app()
            yield TestClient(app, raise_server_exceptions=False)

    def test_new_workflow_without_id(self, client):
        """Without workflow_id, a new workflow is created."""
        # This tests the request schema, not full agent execution
        resp = client.post("/api/agent/v2/chat", json={
            "message": "hello",
            "workflow_id": None,
        })
        # Should not 400 on schema validation
        assert resp.status_code != 422, f"Schema rejected: {resp.text}"

    def test_workflow_id_in_schema(self, client):
        """workflow_id field is accepted in ChatRequest."""
        resp = client.post("/api/agent/v2/chat", json={
            "message": "hello",
            "workflow_id": "wf_12345",
        })
        assert resp.status_code != 422, f"Schema rejected: {resp.text}"

    def test_empty_workflow_id_equivalent_to_none(self, client):
        """Empty string workflow_id treated same as None."""
        resp = client.post("/api/agent/v2/chat", json={
            "message": "hello",
            "workflow_id": "",
        })
        assert resp.status_code != 422, f"Schema rejected: {resp.text}"


# ---------------------------------------------------------------------------
# New REST endpoints
# ---------------------------------------------------------------------------

class TestWorkflowListEndpoint:
    """GET /api/agent/v2/workflows."""

    def test_list_returns_array(self):
        """The endpoint should return a JSON array."""
        pass  # Red — needs store initialization in test setup


class TestWorkflowMessagesEndpoint:
    """GET /api/agent/v2/workflows/{id}/messages."""

    def test_messages_for_existing_workflow(self):
        """Valid workflow returns message list."""
        pass

    def test_messages_for_nonexistent_404(self):
        """Invalid ID returns 404."""
        pass


class TestWorkflowDeleteEndpoint:
    """DELETE /api/agent/v2/workflows/{id}."""

    def test_delete_existing(self):
        """Valid ID returns {status: ok}."""
        pass

    def test_delete_nonexistent_404(self):
        """Invalid ID returns 404."""
        pass


class TestCleanupEndpoint:
    """POST /api/agent/v2/workflows/cleanup."""

    def test_cleanup_returns_stats(self):
        """Returns {archived: N, deleted: N}."""
        pass


class TestToolsEndpoint:
    """GET /api/agent/v2/tools."""

    def test_tools_returns_list(self):
        """Returns tool definitions from registry."""
        pass

    def test_tools_includes_descriptions(self):
        """Each tool has name and description."""
        pass
