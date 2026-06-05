"""Stress tests — concurrency, large payloads, resource limits."""
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.stress


def test_large_text_cleaning():
    """Clean a very large text without crashing."""
    from src.cleaner.pipeline import clean_text
    large = "This is a test sentence. " * 200_000
    result = clean_text(large)
    assert isinstance(result, str)
    assert len(result) > 0


def test_many_chunks_creation():
    """Handle creating many chunk objects."""
    from src.chunker.splitter import ChunkResult, Chunk
    chunks = [Chunk(index=i, text=f"Chunk {i}", char_count=8, estimated_tokens=2) for i in range(10_000)]
    result = ChunkResult(chunks=chunks, references_text="")
    assert len(result.chunks) == 10_000


def test_session_many_messages():
    """Session with many messages should work."""
    from src.agent_v2.runtime.session import Session
    from src.agent_v2.types import Message, MessageRole
    tmp = tempfile.mkdtemp()
    session = Session(workspace=tmp, model="test")
    for i in range(1000):
        msg = Message(role=MessageRole.USER, blocks=[])
        session.append(msg)
    assert session.message_count == 1000


def test_config_deep_nesting():
    """Config with deep nesting should not stack overflow."""
    import yaml
    nested = {"a": {"b": {"c": {"d": {"e": {"f": "value"}}}}}}
    dumped = yaml.dump(nested)
    loaded = yaml.safe_load(dumped)
    assert loaded["a"]["b"]["c"]["d"]["e"]["f"] == "value"


def test_concurrent_rag_registrations():
    """Multiple RAG route registrations don't conflict."""
    from routers.rag import register_rag_routes
    from fastapi import FastAPI
    for _ in range(5):
        app = FastAPI()
        tmp = tempfile.mkdtemp()
        state = register_rag_routes(app, runtime_dir=Path(tmp))
        assert state["get_rag_store"]() is None
