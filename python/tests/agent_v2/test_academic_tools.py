import httpx
import pytest

from src.agent_v2.tools.academic_tools import (
    _fetch_pinned_public_url,
    _pinned_http_request_parts,
    _validate_public_http_url,
    register_academic_tools,
)
from src.agent_v2.tools.registry import ToolRegistry, ToolResult


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
async def test_web_fetch_uses_ip_pinned_transport_for_each_redirect(monkeypatch, tmp_path):
    import src.agent_v2.tools.academic_tools as academic_tools

    calls = []

    async def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return 302, {"location": "https://papers.example.net/final"}, ""
        return 200, {}, "<article>public paper</article>"

    monkeypatch.setattr(academic_tools, "_fetch_pinned_public_url", fetch)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("web_fetch", {"url": "https://example.com/paper"})

    assert result.is_error is False
    assert result.output == "public paper"
    assert calls == [
        "https://example.com/paper",
        "https://papers.example.net/final",
    ]


def test_web_fetch_pins_ip_but_preserves_host_and_tls_identity():
    pinned_url, host_header, sni_hostname = _pinned_http_request_parts(
        "https://example.com/paper?q=1",
        "93.184.216.34",
    )

    assert pinned_url == "https://93.184.216.34/paper?q=1"
    assert host_header == "example.com"
    assert sni_hostname == "example.com"


@pytest.mark.asyncio
async def test_pinned_fetch_connects_to_validated_ip_and_disables_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
):
    import src.agent_v2.tools.academic_tools as academic_tools

    client_options = {}
    sent_requests = []

    async def resolve(_url):
        return True, "", "93.184.216.34"

    class FetchResponse:
        status_code = 200
        headers = {}
        encoding = "utf-8"

        async def aiter_bytes(self):
            yield b"paper"

        async def aclose(self):
            return None

    class FetchClient:
        def __init__(self, **kwargs):
            client_options.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def build_request(self, method, url, *, headers):
            return httpx.Request(method, url, headers=headers)

        async def send(self, request, *, stream):
            sent_requests.append((request, stream))
            return FetchResponse()

    monkeypatch.setattr(academic_tools, "_resolve_public_http_target", resolve)
    monkeypatch.setattr(httpx, "AsyncClient", FetchClient)

    result = await _fetch_pinned_public_url("https://example.com/paper")

    assert result == (200, {}, "paper")
    assert client_options["trust_env"] is False
    request, stream = sent_requests[0]
    assert stream is True
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "example.com"
    assert request.extensions["sni_hostname"] == "example.com"


@pytest.mark.asyncio
async def test_pinned_fetch_rejects_oversized_response_before_reading(
    monkeypatch: pytest.MonkeyPatch,
):
    import src.agent_v2.tools.academic_tools as academic_tools

    closed = False
    iterated = False

    async def resolve(_url):
        return True, "", "93.184.216.34"

    class FetchResponse:
        status_code = 200
        headers = {"content-length": str(2 * 1024 * 1024 + 1)}
        encoding = "utf-8"

        async def aiter_bytes(self):
            nonlocal iterated
            iterated = True
            yield b"must not be read"

        async def aclose(self):
            nonlocal closed
            closed = True

    class FetchClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def build_request(self, method, url, *, headers):
            return httpx.Request(method, url, headers=headers)

        async def send(self, _request, *, stream):
            assert stream is True
            return FetchResponse()

    monkeypatch.setattr(academic_tools, "_resolve_public_http_target", resolve)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: FetchClient())

    result = await _fetch_pinned_public_url("https://example.com/large")

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert "too large" in result.output
    assert iterated is False
    assert closed is True


@pytest.mark.asyncio
async def test_arxiv_search_uses_https_redirects_and_clamps_result_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    client_options = {}
    calls = []

    class ArxivResponse:
        status_code = 200
        text = "<feed><title>YOLO paper</title></feed>"
        url = "https://export.arxiv.org/api/query?search_query=all%3AYOLO"

    class ArxivClient:
        def __init__(self, **kwargs):
            client_options.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, params):
            calls.append((url, params))
            return ArxivResponse()

    monkeypatch.setattr(httpx, "AsyncClient", ArxivClient)
    registry = ToolRegistry(tmp_path)
    register_academic_tools(registry)

    result = await registry.execute("arxiv_search", {"query": "YOLO", "max_results": 200})

    assert result.is_error is False
    assert client_options["follow_redirects"] is True
    assert calls == [
        (
            "https://export.arxiv.org/api/query",
            {"search_query": "all:YOLO", "max_results": "20"},
        )
    ]
    assert result.metadata["source_kind"] == "arxiv"
    assert result.metadata["max_results"] == 20


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
