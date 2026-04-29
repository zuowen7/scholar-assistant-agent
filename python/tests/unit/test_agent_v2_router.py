"""Agent v2 router 端点单元测试 — undo、tool whitelist、sessions。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent.change_journal import ChangeJournal


# ---------------------------------------------------------------------------
# Fixtures — 构造最小可测试 FastAPI app
# ---------------------------------------------------------------------------


def _make_app_with_agent_routes():
    """构造注册了 agent router 的 FastAPI app，mock 掉 Agent 依赖。"""
    app = FastAPI()

    # Mock agent 模块 + features flag
    mock_modules = {
        "src.agent": MagicMock(__path__=["src/agent"]),
        "src.agent.agent": MagicMock(),
        "src.agent.context_compressor": MagicMock(),
        "src.agent.memory": MagicMock(),
        "src.agent.models": MagicMock(),
        "src.agent.prompt_builder": MagicMock(),
        "src.agent.rag": MagicMock(),
        "src.agent.session": MagicMock(),
        "src.agent.skill_system": MagicMock(),
        "src.agent.tools": MagicMock(),
        "src.agent.trajectory": MagicMock(),
        "src.agent.workspace": MagicMock(),
        "src.agent.change_journal": MagicMock(),
        "src.agent.llm_client": MagicMock(),
        "src.translator.cloud_client": MagicMock(PROVIDER_PRESETS={}),
        "src.features": MagicMock(agent=True, plugin=False, argument=False, mcp=False),
    }

    with patch.dict("sys.modules", mock_modules):
        # 重新导入 router 以使用 mock
        import importlib
        import python.routers.agent as agent_router
        importlib.reload(agent_router)

        # 简化的 register — 不真正初始化 agent 子系统
        session_pool: dict = {}

        @app.post("/api/agent/v2/undo/{session_id}")
        async def v2_undo(session_id: str):
            if not agent_router._AGENT_AVAILABLE:
                from fastapi import HTTPException
                raise HTTPException(503, "Agent 模块未安装")
            session = session_pool.get(session_id)
            if session is None:
                from fastapi import HTTPException
                raise HTTPException(404, f"Session {session_id} 不存在")
            if session.journal is None:
                from fastapi import HTTPException
                raise HTTPException(400, "Session 无变更日志")
            reverted = session.journal.undo(count=1)
            return {"status": "ok", "reverted": len(reverted)}

        @app.get("/api/agent/v2/sessions")
        async def v2_list_sessions():
            return [
                {"id": s["id"], "state": s.get("state", "executing")}
                for s in session_pool.values()
            ]

    return app, session_pool


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


class TestToolWhitelist:
    """V2 tool whitelist was removed — registry handles tool gating now."""


# ---------------------------------------------------------------------------
# Undo endpoint (直接测试 router 逻辑)
# ---------------------------------------------------------------------------


class TestUndoEndpoint:
    def _make_session_mock(self, journal):
        session = MagicMock()
        session.journal = journal
        return session

    @pytest.mark.anyio
    async def test_undo_with_journal(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "workspace"
            ws.mkdir()
            test_file = ws / "test.py"
            test_file.write_text("original", encoding="utf-8")

            backup_root = ws / ".agent_backup"
            journal = ChangeJournal(backup_root=backup_root)

            # 备份 + entry
            bid = journal.generate_backup_id()
            journal.backup_file(bid, test_file, ws)
            journal.append_entry(
                backup_id=bid, session_id="s1", event_id="e1",
                tool="str_replace", file="test.py", operation="edit",
            )

            # 修改文件
            test_file.write_text("modified", encoding="utf-8")

            # undo
            reverted = journal.undo(count=1)
            assert len(reverted) == 1
            assert test_file.read_text(encoding="utf-8") == "original"

    @pytest.mark.anyio
    async def test_undo_empty_journal(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "workspace"
            ws.mkdir()
            backup_root = ws / ".agent_backup"
            journal = ChangeJournal(backup_root=backup_root)

            reverted = journal.undo(count=1)
            assert reverted == []
