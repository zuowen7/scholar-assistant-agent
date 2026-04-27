"""MCP Server integration tests.

Launches the MCP server as a subprocess via stdio and verifies:
- list_tools returns >= 16 tools
- a non-LLM tool (format_latex_formula) returns a non-empty string
- translate_text returns non-empty when Ollama/cloud LLM is reachable

Requires: pip install mcp
Run with:  pytest tests/integration/test_mcp_server.py -v
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

SERVER_MODULE = "src.agent.mcp_server"
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
PYTHON_EXEC = sys.executable


def _server_params():
    from mcp import StdioServerParameters

    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([PROJECT_ROOT] + os.environ.get("PYTHONPATH", "").split(os.pathsep)),
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
    }
    return StdioServerParameters(
        command=PYTHON_EXEC,
        args=["-m", SERVER_MODULE],
        env=env,
    )


def _run_async(coro):
    return asyncio.run(coro)


async def _with_session(fn):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    params = _server_params()
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await fn(session)


def test_list_tools_count():
    async def check(session):
        result = await session.list_tools()
        return result.tools

    tools = _run_async(_with_session(check))
    assert len(tools) >= 16, f"Expected >= 16 tools, got {len(tools)}"
    names = [t.name for t in tools]
    assert "translate_text" in names
    assert "crawl_arxiv" in names
    assert "analyze_chart_image" in names


def test_format_latex_formula_returns_nonempty():
    async def check(session):
        return await session.call_tool(
            "format_latex_formula",
            {"formula": r"E = mc^2", "display": True},
        )

    result = _run_async(_with_session(check))
    assert result.isError is not True, f"Tool error: {result.content}"
    text = result.content[0].text
    assert text and text.strip(), "format_latex_formula returned empty"


@pytest.mark.skipif(
    not os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_BASE_URL") == "",
    reason="Ollama not configured (set OLLAMA_BASE_URL to enable)",
)
def test_translate_text_returns_nonempty():
    async def check(session):
        return await session.call_tool("translate_text", {"text": "Hello"})

    result = _run_async(_with_session(check))
    if result.isError:
        pytest.skip(f"LLM unavailable: {result.content[0].text}")
    text = result.content[0].text
    assert text and text.strip(), "translate_text returned empty"
