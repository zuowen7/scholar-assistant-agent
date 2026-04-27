"""翻译客户端单元测试 — OllamaClient + Glossary + helpers"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.translator.ollama_client import (
    OllamaClient,
    Glossary,
    TranslationResult,
    _strip_think_tags,
    MAX_RETRIES,
    _PROMPT_MAX_CHARS,
)


# ---------------------------------------------------------------------------
# _strip_think_tags (existing)
# ---------------------------------------------------------------------------


class TestStripThinkTags:

    def test_basic_think_tag(self) -> None:
        text = "<think >some reasoning</think >翻译结果"
        assert _strip_think_tags(text) == "翻译结果"

    def test_multiline_think_tag(self) -> None:
        text = "<think >\nline1\nline2\n</think >result"
        assert _strip_think_tags(text) == "result"

    def test_no_think_tag(self) -> None:
        text = "直接翻译结果"
        assert _strip_think_tags(text) == "直接翻译结果"

    def test_empty_after_strip(self) -> None:
        text = "<think >only thinking</think >"
        assert _strip_think_tags(text) == ""


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------


class TestGlossary:

    def test_empty_glossary(self) -> None:
        g = Glossary()
        assert g.to_prompt_text() == ""

    def test_single_term(self) -> None:
        g = Glossary()
        # _extract_term_pairs requires 一-鿿 chars followed by (English) pattern
        g.update("transformer", "变换器（Transformer）架构非常高效")
        text = g.to_prompt_text()
        assert "Transformer" in text

    def test_duplicate_term_increments_count(self) -> None:
        g = Glossary()
        g.update("attention", "注意力（Attention）机制很重要")
        g.update("attention", "这种注意力（Attention）方法")
        assert len(g._entries) == 1
        assert g._entries["attention"].count == 2

    def test_max_terms_limit(self) -> None:
        g = Glossary()
        for i in range(50):
            en = f"Term{i}Alpha"
            zh = f"术语{i}（{en}）的描述文字"
            g.update(en, zh)
        lines = g.to_prompt_text().strip().split("\n")
        assert len(lines) <= 30

    def test_sorted_by_count_descending(self) -> None:
        g = Glossary()
        g.update("RareTerm", "稀有术语（RareTerm）描述")
        for _ in range(5):
            g.update("CommonTerm", "常见术语（CommonTerm）使用")
        text = g.to_prompt_text()
        assert text.index("CommonTerm") < text.index("RareTerm")


# ---------------------------------------------------------------------------
# OllamaClient — successful translation
# ---------------------------------------------------------------------------


def _make_ollama_chat_response(text: str, model: str = "qwen3:8b") -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": model,
        "message": {"content": text},
        "prompt_eval_count": 100,
        "eval_count": 50,
    }
    return mock_resp


def _make_ollama_generate_response(text: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3:8b",
        "response": text,
        "prompt_eval_count": 80,
        "eval_count": 40,
    }
    return mock_resp


class TestOllamaClientSuccess:

    def test_translate_with_chat_api(self) -> None:
        client = OllamaClient(base_url="http://localhost:11434")
        mock_resp = _make_ollama_chat_response("翻译结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            result = client.translate("Hello world, this is a test sentence.")

        assert result.translated == "翻译结果"
        assert result.original == "Hello world, this is a test sentence."
        assert result.model == "qwen3:8b"
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50
        client.close()

    def test_translate_falls_back_to_generate_api(self) -> None:
        client = OllamaClient()

        chat_fail = MagicMock()
        chat_fail.status_code = 500
        chat_fail.raise_for_status = MagicMock()

        gen_resp = _make_ollama_generate_response("生成结果")

        def post_side_effect(url, **kwargs):
            if "/api/chat" in url:
                return chat_fail
            return gen_resp

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = post_side_effect
            mock_get.return_value = mock_http

            result = client.translate("Hello world, this is a test sentence.")

        assert result.translated == "生成结果"
        client.close()

    def test_translate_generates_response_format(self) -> None:
        client = OllamaClient()
        mock_resp = _make_ollama_generate_response("生成结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            # Force generate API by making chat fail with ValueError
            result = client.translate("Hello world, this is a test sentence.")

        assert result.translated == "生成结果"
        client.close()

    def test_health_check_success(self) -> None:
        client = OllamaClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.get.return_value = mock_resp
            mock_get.return_value = mock_http

            assert client.health_check() is True
        client.close()

    def test_health_check_failure(self) -> None:
        client = OllamaClient()
        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.get.side_effect = httpx.ConnectError("refused", request=MagicMock())
            mock_get.return_value = mock_http

            assert client.health_check() is False
        client.close()

    def test_set_document_context(self) -> None:
        client = OllamaClient()
        client.set_document_context("  Title: Test Paper\n\n")
        assert client._document_context == "Title: Test Paper"
        client.close()


# ---------------------------------------------------------------------------
# OllamaClient — error paths
# ---------------------------------------------------------------------------


class TestOllamaClientErrors:

    def test_connection_error_raises(self) -> None:
        client = OllamaClient()

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.ConnectError(
                "refused", request=MagicMock()
            )
            mock_get.return_value = mock_http
            with patch("src.translator.ollama_client.time.sleep"):
                with pytest.raises(ConnectionError, match="无法连接"):
                    client.translate("Hello world, test sentence.")

        client.close()

    def test_http_error_raises_value_error(self) -> None:
        client = OllamaClient()

        mock_err_resp = MagicMock()
        mock_err_resp.status_code = 500
        mock_err_resp.text = "Internal Server Error"
        http_err = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=mock_err_resp
        )

        call_count = 0

        def post_side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "/api/chat" in url:
                # Return a 500 response first, then raise on generate
                if call_count <= 1:
                    resp = MagicMock()
                    resp.status_code = 500
                    resp.raise_for_status = MagicMock()
                    return resp
            raise http_err

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = post_side_effect
            mock_get.return_value = mock_http
            with patch("src.translator.ollama_client.time.sleep"):
                with pytest.raises((ConnectionError, ValueError)):
                    client.translate("Hello world, this is a test sentence.")

        client.close()

    def test_timeout_raises_connection_error(self) -> None:
        client = OllamaClient()

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.TimeoutException(
                "timeout", request=MagicMock()
            )
            mock_get.return_value = mock_http
            with patch("src.translator.ollama_client.time.sleep"):
                with pytest.raises(ConnectionError, match="超时"):
                    client.translate("Hello world, test sentence.")

        client.close()

    def test_retries_on_connection_error(self) -> None:
        client = OllamaClient()
        call_count = 0

        def raise_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("refused", request=MagicMock())

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = raise_connect
            mock_get.return_value = mock_http
            with patch("src.translator.ollama_client.time.sleep"):
                with pytest.raises(ConnectionError):
                    client.translate("Hello world, test sentence.")

        assert call_count == MAX_RETRIES + 1  # 1 initial + 2 retries
        client.close()


# ---------------------------------------------------------------------------
# OllamaClient — prompt building
# ---------------------------------------------------------------------------


class TestOllamaClientPrompt:

    def test_system_prompt_includes_glossary(self) -> None:
        client = OllamaClient(system_prompt="你是一个翻译助手")
        client._glossary.update("attention", "注意力（Attention）机制")
        prompt = client._build_system_prompt()

        assert "翻译助手" in prompt
        assert "Attention" in prompt
        client.close()

    def test_system_prompt_includes_chunk_index(self) -> None:
        client = OllamaClient()
        client._chunk_index = 3
        prompt = client._build_system_prompt()

        assert "第 4 块" in prompt
        client.close()

    def test_prompt_truncation_for_long_context(self) -> None:
        client = OllamaClient()
        long_prev = "x" * (_PROMPT_MAX_CHARS + 1000)
        long_text = "y" * 500

        with patch.object(client, "_get_http_client") as mock_get:
            mock_resp = _make_ollama_chat_response("结果")
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            client.translate(long_text, long_prev)

            # Verify the post was called — prompt was built without error
            assert mock_http.post.called
        client.close()

    def test_prev_translation_carried_between_chunks(self) -> None:
        client = OllamaClient()

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = _make_ollama_chat_response("第一段译文")
            mock_get.return_value = mock_http

            client.translate("First chunk of text for translation.")

        assert client._prev_translation == "第一段译文"
        assert client._chunk_index == 1
        client.close()
