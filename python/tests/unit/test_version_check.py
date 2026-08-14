"""应用更新检查（GitHub Releases 代理）单元测试。

覆盖：网页端 302 提取 tag、API 兜底、双失败、成功缓存。
"""

from __future__ import annotations

import routers.translate as translate


class _FakeResponse:
    def __init__(self, status_code: int = 200, url: str = "", payload: dict | None = None):
        self.status_code = status_code
        self.url = url
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses: list):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url: str, **kwargs):
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _patch_httpx(monkeypatch, client_factory) -> None:
    monkeypatch.setattr("httpx.AsyncClient", client_factory)


class TestExtractReleaseTagFromUrl:
    def test_plain_tag(self):
        url = "https://github.com/zuowen7/scholar-assistant-agent/releases/tag/v0.6.0"
        assert translate._extract_release_tag_from_url(url) == "v0.6.0"

    def test_tag_with_query(self):
        url = "https://github.com/o/r/releases/tag/v1.2.3?utm=x#frag"
        assert translate._extract_release_tag_from_url(url) == "v1.2.3"

    def test_encoded_tag(self):
        url = "https://github.com/o/r/releases/tag/v1.0.0-beta.1%2Bfix"
        assert translate._extract_release_tag_from_url(url) == "v1.0.0-beta.1+fix"

    def test_no_release_page(self):
        assert translate._extract_release_tag_from_url("https://github.com/o/r/releases") == ""

    def test_empty(self):
        assert translate._extract_release_tag_from_url("") == ""


class TestFetchLatestRelease:
    async def test_web_redirect_success_and_cached(self, monkeypatch):
        translate._update_cache.clear()
        clients = [
            _FakeClient(
                [
                    _FakeResponse(
                        200,
                        "https://github.com/zuowen7/scholar-assistant-agent/releases/tag/v0.6.0",
                    )
                ]
            )
        ]

        def factory(**kwargs):
            return clients.pop(0)

        _patch_httpx(monkeypatch, factory)

        data = await translate._fetch_latest_release()
        assert data == {
            "ok": True,
            "latest_version": "0.6.0",
            "release_url": "https://github.com/zuowen7/scholar-assistant-agent/releases/tag/v0.6.0",
        }

        # 命中缓存：不再新建客户端（clients 已空，再建会 IndexError）
        again = await translate._fetch_latest_release()
        assert again == data

    async def test_web_failure_falls_back_to_api(self, monkeypatch):
        translate._update_cache.clear()
        clients = [
            _FakeClient([RuntimeError("TLS handshake failed")]),
            _FakeClient(
                [
                    _FakeResponse(
                        200,
                        payload={
                            "tag_name": "v0.7.0",
                            "html_url": "https://github.com/zuowen7/scholar-assistant-agent/releases/tag/v0.7.0",
                        },
                    )
                ]
            ),
        ]

        def factory(**kwargs):
            return clients.pop(0)

        _patch_httpx(monkeypatch, factory)

        data = await translate._fetch_latest_release()
        assert data["ok"] is True
        assert data["latest_version"] == "0.7.0"

    async def test_web_page_without_tag_falls_back_to_api(self, monkeypatch):
        """仓库没有 Release 时 /releases/latest 落到 /releases 页（无 tag）。"""
        translate._update_cache.clear()
        clients = [
            _FakeClient(
                [_FakeResponse(200, "https://github.com/zuowen7/scholar-assistant-agent/releases")]
            ),
            _FakeClient(
                [
                    _FakeResponse(
                        200,
                        payload={
                            "tag_name": "v0.5.1",
                            "html_url": "https://github.com/zuowen7/scholar-assistant-agent/releases/tag/v0.5.1",
                        },
                    )
                ]
            ),
        ]

        def factory(**kwargs):
            return clients.pop(0)

        _patch_httpx(monkeypatch, factory)

        data = await translate._fetch_latest_release()
        assert data["latest_version"] == "0.5.1"

    async def test_api_payload_without_html_url_uses_default(self, monkeypatch):
        translate._update_cache.clear()
        clients = [
            _FakeClient([RuntimeError("blocked")]),
            _FakeClient([_FakeResponse(200, payload={"tag_name": "v0.5.2"})]),
        ]

        def factory(**kwargs):
            return clients.pop(0)

        _patch_httpx(monkeypatch, factory)

        data = await translate._fetch_latest_release()
        assert data["latest_version"] == "0.5.2"
        assert (
            data["release_url"]
            == "https://github.com/zuowen7/scholar-assistant-agent/releases/latest"
        )

    async def test_both_fail_returns_not_ok_and_retries_next_call(self, monkeypatch):
        translate._update_cache.clear()
        clients = [
            _FakeClient([RuntimeError("web down")]),
            _FakeClient([_FakeResponse(403)]),
        ]

        def factory(**kwargs):
            return clients.pop(0)

        _patch_httpx(monkeypatch, factory)

        data = await translate._fetch_latest_release()
        assert data == {"ok": False, "latest_version": "", "release_url": ""}

        # 失败不缓存：下次调用会重新发起请求（再注入一对失败客户端即可验证）
        clients.extend([_FakeClient([RuntimeError("web down")]), _FakeClient([_FakeResponse(403)])])
        again = await translate._fetch_latest_release()
        assert again["ok"] is False
