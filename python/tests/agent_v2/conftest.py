"""Shared fixtures for agent_v2 tests."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.agent_v2.providers.mock_provider import MockProvider, Scenario
from src.agent_v2.types import InputMessage, Message, MessageRole, TokenUsage


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    (tmp_path / "main.md").write_text("# Hello\n\nThis is a test document.", encoding="utf-8")
    (tmp_path / "main.py").write_text("def hello():\n    print('hello')\n    # TODO: fix\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "data.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def user_messages() -> list[Message]:
    return [Message(role=MessageRole.USER, blocks=[__import__("src.agent_v2.types", fromlist=["TextBlock"]).TextBlock(text="hello")])]


def make_user_message(text: str) -> Message:
    from src.agent_v2.types import TextBlock
    return Message(role=MessageRole.USER, blocks=[TextBlock(text=text)])
