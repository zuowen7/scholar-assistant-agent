import httpx
import pytest

from src.agent_v2.tools.academic_tools import register_academic_tools
from src.agent_v2.tools.registry import ToolRegistry


class _Response:
    def __init__(self, data: dict, *, content: bytes = b"") -> None:
        self.status_code = 200
        self._data = data
        self.content = content

    def json(self) -> dict:
        return self._data


class _Client:
    def __init__(self, response: _Response, calls: list[tuple[str, dict]]) -> None:
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url: str, *, json: dict):
        self.calls.append((url, json))
        return self.response


@pytest.mark.asyncio
async def test_export_latex_writes_result_inside_workspace(tmp_path, monkeypatch):
    source = tmp_path / "paper.md"
    source.write_text("# Paper", encoding="utf-8")
    calls = []
    client = _Client(_Response({"success": True, "tex": "\\section{Paper}"}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("export_document", {"file_path": "paper.md", "format": "latex"})

    assert not result.is_error
    assert (tmp_path / "paper.tex").read_text(encoding="utf-8") == "\\section{Paper}"
    assert calls[0][0].endswith("/api/export")


@pytest.mark.asyncio
async def test_export_word_copies_generated_file_into_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "paper.md"
    source.write_text("# Paper", encoding="utf-8")
    generated = tmp_path / "generated.docx"
    generated.write_bytes(b"docx")
    calls = []
    client = _Client(_Response({"path": str(generated)}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(workspace)
    register_academic_tools(registry)

    result = await registry.execute("export_document", {"file_path": "paper.md", "format": "docx"})

    assert not result.is_error
    assert (workspace / "paper.docx").read_bytes() == b"docx"
    assert calls[0][0].endswith("/api/export/word")
