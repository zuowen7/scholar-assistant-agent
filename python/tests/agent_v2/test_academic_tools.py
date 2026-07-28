import httpx
import pytest

from src.agent_v2.tools.academic_tools import _validate_public_http_url, register_academic_tools
from src.agent_v2.tools.registry import ToolRegistry


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "http://localhost/private",
        "http://[::1]/private",
        "http://10.0.0.1/private",
        "http://172.16.0.1/private",
        "http://192.168.1.1/private",
        "http://169.254.169.254/latest/meta-data",
        "http://[::ffff:127.0.0.1]/private",
    ],
)
def test_web_fetch_rejects_non_public_targets(url: str):
    """SEC-03: web fetch must reject local, private and link-local targets."""
    allowed, reason = _validate_public_http_url(url, resolved_ips=None)
    assert allowed is False
    assert reason


def test_web_fetch_accepts_public_https_literal():
    allowed, reason = _validate_public_http_url(
        "https://example.com/paper",
        resolved_ips=["93.184.216.34"],
    )
    assert allowed is True
    assert reason == ""


def test_web_fetch_rejects_nonstandard_ports():
    allowed, reason = _validate_public_http_url(
        "https://example.com:8443/paper",
        resolved_ips=["93.184.216.34"],
    )
    assert allowed is False
    assert "port" in reason


@pytest.mark.asyncio
async def test_web_fetch_rechecks_dns_after_connection(monkeypatch, tmp_path):
    import src.agent_v2.tools.academic_tools as academic_tools

    resolutions = iter(
        [
            (True, ""),
            (True, ""),
            (False, "non-public network target is not allowed: 127.0.0.1"),
        ]
    )

    async def resolve(_url):
        return next(resolutions)

    class FetchResponse:
        status_code = 200
        headers = {}
        text = "private response must not be returned"

    class FetchClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, _url):
            return FetchResponse()

    monkeypatch.setattr(academic_tools, "_resolve_public_http_url", resolve)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FetchClient())
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("web_fetch", {"url": "https://example.com/paper"})

    assert result.is_error is True
    assert "non-public network target" in result.output


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
async def test_export_preflight_rejects_missing_image_before_api_call(tmp_path, monkeypatch):
    source = tmp_path / "paper.md"
    source.write_text("![Figure](figures/missing.png)", encoding="utf-8")
    calls = []
    client = _Client(_Response({"tex": "unused"}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("export_document", {"file_path": "paper.md", "format": "latex"})

    assert result.is_error is True
    assert "missing image: figures/missing.png" in result.output
    assert calls == []


@pytest.mark.asyncio
async def test_export_preflight_rejects_missing_template_before_api_call(tmp_path, monkeypatch):
    source = tmp_path / "paper.md"
    source.write_text(
        "---\ntemplate: templates/missing.tex\n---\n# Paper",
        encoding="utf-8",
    )
    calls = []
    client = _Client(_Response({"tex": "unused"}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("export_document", {"file_path": "paper.md", "format": "latex"})

    assert result.is_error is True
    assert "missing template: templates/missing.tex" in result.output
    assert calls == []


@pytest.mark.asyncio
async def test_export_preflight_rejects_resource_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "private.png").write_bytes(b"private")
    source = workspace / "paper.md"
    source.write_text("![Private](../private.png)", encoding="utf-8")
    calls = []
    client = _Client(_Response({"tex": "unused"}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(workspace)
    register_academic_tools(registry)

    result = await registry.execute("export_document", {"file_path": "paper.md", "format": "latex"})

    assert result.is_error is True
    assert "image escapes workspace: ../private.png" in result.output
    assert calls == []


@pytest.mark.asyncio
async def test_export_preflight_rejects_missing_bibliography_key(tmp_path, monkeypatch):
    source = tmp_path / "paper.md"
    source.write_text(
        "---\nbibliography: refs.bib\n---\nEvidence [@missing-key].",
        encoding="utf-8",
    )
    (tmp_path / "refs.bib").write_text(
        "@article{present-key,\n  title={Present}\n}",
        encoding="utf-8",
    )
    calls = []
    client = _Client(_Response({"tex": "unused"}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("export_document", {"file_path": "paper.md", "format": "latex"})

    assert result.is_error is True
    assert "missing bibliography key: missing-key" in result.output
    assert calls == []


@pytest.mark.asyncio
async def test_export_allows_missing_resources_only_with_explicit_flag(tmp_path, monkeypatch):
    source = tmp_path / "paper.md"
    source.write_text("![Figure](missing.png)", encoding="utf-8")
    calls = []
    client = _Client(_Response({"success": True, "tex": "\\section{Paper}"}), calls)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute(
        "export_document",
        {
            "file_path": "paper.md",
            "format": "latex",
            "allow_missing_resources": True,
        },
    )

    assert result.is_error is False
    assert "explicitly allowed" in result.output
    assert (tmp_path / "paper.tex").is_file()


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
