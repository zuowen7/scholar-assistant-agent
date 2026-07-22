"""Academic Agent tool registration regressions."""

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
