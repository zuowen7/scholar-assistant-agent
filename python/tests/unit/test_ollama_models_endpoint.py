"""Ollama list_models() 和 /api/ollama/models 端点测试"""
from unittest.mock import Mock, patch

import pytest


class TestOllamaClientListModels:
    """测试 OllamaClient.list_models() 方法"""

    def test_returns_model_names(self):
        """正常返回模型名列表。"""
        from src.translator.ollama_client import OllamaClient

        client = OllamaClient(base_url="http://localhost:11434")
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen3:8b", "modified_at": "2025-01-01", "size": 5000000000},
                {"name": "llama3.1:8b", "modified_at": "2025-01-02", "size": 4800000000},
            ]
        }

        with patch.object(client, "_get_http_client") as mock_client:
            mock_client.return_value.get.return_value = mock_resp
            models = client.list_models()

        assert isinstance(models, list)
        assert len(models) == 2
        assert "qwen3:8b" in models
        assert "llama3.1:8b" in models

    def test_empty_models(self):
        """Ollama 返回空列表。"""
        from src.translator.ollama_client import OllamaClient

        client = OllamaClient()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}

        with patch.object(client, "_get_http_client") as mock_client:
            mock_client.return_value.get.return_value = mock_resp
            models = client.list_models()

        assert models == []

    def test_connection_error_returns_empty(self):
        """连接失败时返回空列表（不抛异常）。"""
        from src.translator.ollama_client import OllamaClient

        client = OllamaClient()
        with patch.object(client, "_get_http_client") as mock_client:
            mock_client.return_value.get.side_effect = Exception("Connection refused")
            models = client.list_models()

        assert models == []

    def test_calls_correct_url(self):
        """验证调用了正确的 Ollama API endpoint。"""
        from src.translator.ollama_client import OllamaClient

        client = OllamaClient(base_url="http://192.168.1.1:11434")
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}

        with patch.object(client, "_get_http_client") as mock_client:
            mock_client.return_value.get.return_value = mock_resp
            client.list_models()

        mock_client.return_value.get.assert_called_once()
        url = mock_client.return_value.get.call_args[0][0]
        assert "192.168.1.1:11434/api/tags" in url or url.endswith("/api/tags")
