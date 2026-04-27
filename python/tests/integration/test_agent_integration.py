"""Agent Loop + ToolRegistry integration tests.

Tests the core Agent subsystem components together:
- ToolRegistry: tool registration, execution, Ollama format export
- RAGStore: full document lifecycle with ChromaDB
- AgentLoop: message building with memory and RAG injection
- ErrorClassifier: error classification and recovery strategies
- HookManager: lifecycle hook registration and triggering
- PromptBuilder: system prompt assembly with tools
"""

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agent.agent import AgentLoop
from src.agent.error_classifier import (
    ErrorType,
    RecoveryAction,
    RetryManager,
    classify_error,
    get_recovery,
)
from src.agent.hooks import HookContext, HookManager, HookPoint
from src.agent.memory import MemoryManager
from src.agent.models import AgentEvent, DocumentInfo, Message, ToolCall
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.rag import RAGStore
from src.agent.skill_system import SkillRegistry
from src.agent.tools import ToolRegistry, create_default_registry


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def registry():
    """Default ToolRegistry with all built-in tools registered."""
    return create_default_registry()


@pytest.fixture
def rag_store(temp_dir):
    """RAGStore using a temporary directory for ChromaDB storage."""
    return RAGStore(
        persist_dir=temp_dir,
        collection_name="test_collection",
    )


@pytest.fixture
def memory_manager(temp_dir):
    """MemoryManager using a temporary directory."""
    return MemoryManager(data_dir=temp_dir)


@pytest.fixture
def agent_loop(temp_dir):
    """AgentLoop with temp storage, no external connections."""
    registry = ToolRegistry()
    memory = MemoryManager(data_dir=temp_dir)
    skills = SkillRegistry(skills_dir=str(Path(temp_dir) / "skills"))
    builder = PromptBuilder(tool_registry=registry)
    loop = AgentLoop(
        ollama_base_url="http://localhost:11499",  # non-existent port
        model="test-model",
        tool_registry=registry,
        max_steps=3,
        system_prompt="",  # Must be empty so PromptBuilder is used
        temperature=0.0,
        num_predict=256,
        timeout=5.0,
        memory_manager=memory,
        skill_registry=skills,
        prompt_builder=builder,
        memory_dir=str(Path(temp_dir) / "memory"),
    )
    return loop


# ── 1. ToolRegistry execute all default tools ───────────────────────────


class TestToolRegistryDefaults:
    """Tests for ToolRegistry with the default tool set."""

    def test_tool_registry_execute_all_default_tools(self, registry):
        """Create default registry, verify all tools are callable with safe args.

        Each tool is called with minimal safe arguments. Tools that require
        external services (LLM, arXiv, web) may return error strings, but
        must not raise unhandled exceptions.
        """
        all_tools = registry.list_tools()
        assert len(all_tools) >= 15, (
            f"Expected at least 15 default tools, got {len(all_tools)}: "
            f"{[t.name for t in all_tools]}"
        )

        safe_args = {
            "translate_text": {"text": "Hello", "source_lang": "en", "target_lang": "zh"},
            "parse_document": {"file_path": "nonexistent_test.pdf"},
            "search_documents": {"query": "test query", "top_k": 1},
            "crawl_arxiv": {"query": "test", "max_results": 1},
            "polish_text": {"text": "test", "style": "academic"},
            "summarize_text": {"text": "A short test sentence.", "max_sentences": 1},
            "generate_outline": {"topic": "test topic", "sections": 2},
            "expand_section": {"section": "test section", "context": ""},
            "save_file": {"file_path": "test_out.txt", "content": "hello"},
            "read_file": {"file_path": "nonexistent_file.txt"},
            "format_bibliography": {
                "bibtex_entry": "@article{test, title={Test}}",
                "style": "ieee",
                "target_lang": "en",
            },
            "shell_exec": {"command": "echo integration_test"},
            "python_exec": {"code": "print('hello from python_exec')"},
            "web_fetch": {"url": "https://httpbin.org/html", "extract_text": True},
            "web_search": {"query": "integration test query", "max_results": 1},
            "export_pdf": {"markdown": "# Test", "template_id": "generic_article", "title": "Test"},
            "manage_knowledge": {"action": "list"},
            # Special elements tools
            "analyze_markdown_elements": {"text": "# Title\nSome text with $x=1$"},
            "extract_image_for_analysis": {"image_path": "nonexistent.png"},
            "parse_table_structure": {"table_markdown": "| A | B |\n|---|---|\n| 1 | 2 |"},
            "generate_table_markdown": {"headers": ["A", "B"], "rows": [["1", "2"]]},
            "format_latex_formula": {"formula": "E=mc^2"},
            "get_citation_context": {"text": "As shown by [@smith2020]", "citation_key": "smith2020"},
            "analyze_image_with_vision": {"image_path": "nonexistent.png"},
            "analyze_chart_image": {"image_path": "nonexistent.png"},
        }

        for tool_def in all_tools:
            args = safe_args.get(tool_def.name)
            if args is None:
                continue  # skip tools without safe test args
            result = asyncio.run(registry.execute(tool_def.name, args))
            assert isinstance(result, str), (
                f"Tool {tool_def.name} should return str, got {type(result)}"
            )
            # Result must not be empty (even errors produce messages)
            assert len(result) > 0, f"Tool {tool_def.name} returned empty string"

    def test_tool_registry_ollama_format(self, registry):
        """Verify to_ollama_tools() returns valid JSON schema for all tools."""
        ollama_tools = registry.to_ollama_tools()
        assert isinstance(ollama_tools, list)
        assert len(ollama_tools) == len(registry.list_tools())

        for tool_schema in ollama_tools:
            # Top-level structure
            assert tool_schema["type"] == "function", (
                f"Expected type='function', got {tool_schema.get('type')}"
            )
            func = tool_schema["function"]
            assert "name" in func and isinstance(func["name"], str)
            assert "description" in func and isinstance(func["description"], str)
            assert "parameters" in func and isinstance(func["parameters"], dict)

            # Parameters must be valid JSON Schema
            params = func["parameters"]
            assert params["type"] == "object"
            assert "properties" in params

            # Name must not be empty
            assert len(func["name"]) > 0

            # Description must not be empty
            assert len(func["description"]) > 0

            # Verify JSON serializability (no Python objects leaking)
            serialized = json.dumps(tool_schema)
            assert isinstance(serialized, str)


# ── 3. RAG Knowledge lifecycle ──────────────────────────────────────────


class TestRAGKnowledgeLifecycle:
    """Full document lifecycle test: ingest, list, retrieve, delete."""

    def test_manage_knowledge_lifecycle(self, rag_store):
        """Create RAGStore with temp dir, ingest text, list, retrieve, delete."""
        doc_id = "test_paper_001"
        text = (
            "The transformer architecture has revolutionized natural language processing. "
            "Self-attention mechanisms allow the model to weigh the importance of different "
            "words in a sequence. Multi-head attention provides multiple representation "
            "subspaces, enabling the model to capture diverse patterns."
        )
        metadata = {"title": "Attention Is All You Need", "source": "test"}

        # Step 1: Ingest
        chunk_count = rag_store.ingest_document(doc_id, text, metadata=metadata)
        assert chunk_count >= 1, f"Expected at least 1 chunk, got {chunk_count}"

        # Step 2: List
        docs = rag_store.list_documents()
        assert len(docs) >= 1
        found = [d for d in docs if d.id == doc_id]
        assert len(found) == 1
        doc_info = found[0]
        assert doc_info.title == "Attention Is All You Need"
        assert doc_info.chunk_count >= 1

        # Step 3: Retrieve
        results = rag_store.retrieve_context("transformer architecture", top_k=3)
        assert len(results) >= 1
        assert "transformer" in results[0]["text"].lower()
        assert "metadata" in results[0]
        assert "distance" in results[0]

        # Step 4: Delete
        rag_store.delete_document(doc_id)
        docs_after = rag_store.list_documents()
        found_after = [d for d in docs_after if d.id == doc_id]
        assert len(found_after) == 0

    def test_rag_ingest_empty_text(self, rag_store):
        """Empty text should not create any chunks."""
        count = rag_store.ingest_document("empty_doc", "")
        assert count == 0

    def test_rag_retrieve_empty_store(self, rag_store):
        """Retrieving from an empty store should return empty list."""
        results = rag_store.retrieve_context("anything", top_k=5)
        assert results == []

    def test_rag_count_chunks(self, rag_store):
        """count_chunks should reflect ingested documents."""
        assert rag_store.count_chunks() == 0
        rag_store.ingest_document(
            "doc1",
            "First test document. " * 20,
            metadata={"title": "Doc 1"},
        )
        assert rag_store.count_chunks() >= 1


# ── 4. Agent message building with memory ───────────────────────────────


class TestAgentMessageBuilding:
    """Tests for AgentLoop._build_messages with memory and RAG injection."""

    def test_agent_build_messages_with_memory(self, temp_dir):
        """Inject memory context, verify messages include memory content."""
        memory = MemoryManager(data_dir=temp_dir)
        skills = SkillRegistry(skills_dir=str(Path(temp_dir) / "skills"))
        builder = PromptBuilder(tool_registry=ToolRegistry())
        agent_loop = AgentLoop(
            ollama_base_url="http://localhost:11499",
            model="test-model",
            max_steps=3,
            system_prompt="",  # empty to use PromptBuilder
            prompt_builder=builder,
            memory_manager=memory,
            skill_registry=skills,
            memory_dir=str(Path(temp_dir) / "memory"),
        )
        # Add a memory entry
        agent_loop.memory.add_memory(
            content="User prefers concise Chinese replies",
            category="preference",
            source="user_input",
            importance=0.8,
        )

        # Build messages with a short query that is a verbatim substring of
        # the memory content. search_memories uses LIKE %query%, so the entire
        # query string must appear as a contiguous substring.
        messages = agent_loop._build_messages("prefers")

        # First message should be system prompt
        assert messages[0].role == "system"
        system_content = messages[0].content

        # System prompt should contain memory context
        assert "memory-context" in system_content or "concise" in system_content

        # Last message should be the user query
        assert messages[-1].role == "user"

    def test_agent_build_messages_with_rag(self, temp_dir):
        """Inject RAG store, verify context injection in messages."""
        # Create RAG store with a document
        rag = RAGStore(
            persist_dir=temp_dir,
            collection_name="rag_test",
        )
        rag.ingest_document(
            "doc_rag_test",
            "Machine learning is a subset of artificial intelligence that enables "
            "systems to learn and improve from experience without being explicitly programmed.",
            metadata={"title": "ML Introduction"},
        )

        # Create AgentLoop with RAG
        loop = AgentLoop(
            ollama_base_url="http://localhost:11499",
            model="test-model",
            tool_registry=ToolRegistry(),
            rag_store=rag,
            system_prompt="You are a test assistant.",
        )

        messages = loop._build_messages("What is machine learning?")

        # Should have system messages, possibly one with RAG context
        system_msgs = [m for m in messages if m.role == "system"]
        assert len(system_msgs) >= 1

        # At least one system message should reference the knowledge base
        rag_context_found = any(
            "知识库" in m.content or "文档片段" in m.content or "Machine learning" in m.content
            for m in system_msgs
        )
        assert rag_context_found, "RAG context should be injected into messages"

    def test_agent_build_messages_with_history(self, agent_loop):
        """Verify history messages are included (with truncation)."""
        # Create many history messages
        history = [
            Message(role="user", content=f"Question {i}")
            for i in range(25)
        ]

        messages = agent_loop._build_messages("New question", history=history)

        # Should include system + truncated history + current query
        user_msgs = [m for m in messages if m.role == "user"]
        assert len(user_msgs) <= 25  # truncated + current
        assert messages[-1].content == "New question"


# ── 6. Error classifier round-trip ──────────────────────────────────────


class TestErrorClassifier:
    """Tests for error classification and recovery strategy lookup."""

    def test_error_classifier_round_trip(self):
        """Classify common errors and verify recovery strategies."""
        test_cases = [
            # (exception, expected_error_type, expected_action)
            (
                ConnectionError("timeout after 30s"),
                ErrorType.TIMEOUT,
                "retry",
            ),
            (
                Exception("connection refused to localhost"),
                ErrorType.TIMEOUT,
                "retry",
            ),
            (
                Exception("context window overflow, too long"),
                ErrorType.CONTEXT_OVERFLOW,
                "rephrase",
            ),
            (
                Exception("rate limit exceeded, too many requests"),
                ErrorType.RATE_LIMIT,
                "retry",
            ),
        ]

        for exc, expected_type, expected_action in test_cases:
            classified = classify_error(exc)
            assert classified == expected_type, (
                f"classify_error({exc!r}) = {classified}, expected {expected_type}"
            )

            recovery = get_recovery(classified)
            assert isinstance(recovery, RecoveryAction)
            assert recovery.action == expected_action, (
                f"get_recovery({classified}) action = {recovery.action}, "
                f"expected {expected_action}"
            )

    def test_auth_error_aborts(self):
        """Authentication errors should not be retryable."""
        exc = Exception("401 unauthorized, invalid API key")
        classified = classify_error(exc)
        assert classified == ErrorType.AUTH

        recovery = get_recovery(classified)
        assert recovery.action == "abort"

    def test_retry_manager_exponential_backoff(self):
        """RetryManager should compute increasing delays."""
        mgr = RetryManager(base_delay=2.0)
        error_type = ErrorType.TIMEOUT

        # First attempt
        delay0 = mgr.get_delay(error_type)
        mgr.record_attempt(error_type)

        # Second attempt
        delay1 = mgr.get_delay(error_type)
        mgr.record_attempt(error_type)

        # Exponential: delay1 should be >= delay0
        assert delay1 >= delay0, f"Expected exponential backoff: {delay1} >= {delay0}"

    def test_retry_manager_can_retry(self):
        """can_retry should respect max_retries from recovery strategy."""
        mgr = RetryManager()
        error_type = ErrorType.TIMEOUT

        # Initially can retry
        assert mgr.can_retry(error_type) is True

        # Exhaust retries
        for _ in range(5):
            mgr.record_attempt(error_type)

        # Should now be exhausted
        assert mgr.can_retry(error_type) is False


# ── 7. HookManager lifecycle ────────────────────────────────────────────


class TestHookManager:
    """Tests for hook registration, triggering, and execution order."""

    def test_hook_manager_lifecycle(self):
        """Register hooks, trigger them, verify execution order."""
        manager = HookManager()
        execution_log = []

        # Register hooks using the decorator pattern
        @manager.register(HookPoint.ON_TOOL_CALL)
        def hook_tool_call(ctx: HookContext):
            execution_log.append(("tool_call", ctx.data.get("tool_name", "")))

        @manager.register(HookPoint.ON_TOOL_RESULT)
        def hook_tool_result(ctx: HookContext):
            execution_log.append(("tool_result", ctx.data.get("tool_name", "")))

        # Register hooks using add_hook
        def hook_error(ctx: HookContext):
            execution_log.append(("error", ctx.data.get("error", "")))

        manager.add_hook(HookPoint.ON_ERROR, hook_error)

        # Trigger hooks
        asyncio.run(manager.trigger(HookContext(
            point=HookPoint.ON_TOOL_CALL,
            data={"tool_name": "translate_text"},
        )))
        asyncio.run(manager.trigger(HookContext(
            point=HookPoint.ON_TOOL_RESULT,
            data={"tool_name": "translate_text"},
        )))
        asyncio.run(manager.trigger(HookContext(
            point=HookPoint.ON_ERROR,
            data={"error": "something went wrong"},
        )))

        # Verify execution log
        assert len(execution_log) == 3
        assert execution_log[0] == ("tool_call", "translate_text")
        assert execution_log[1] == ("tool_result", "translate_text")
        assert execution_log[2] == ("error", "something went wrong")

    def test_hook_execution_order(self):
        """Multiple hooks on the same point execute in registration order."""
        manager = HookManager()
        order = []

        manager.add_hook(HookPoint.ON_LLM_CALL, lambda ctx: order.append(1))
        manager.add_hook(HookPoint.ON_LLM_CALL, lambda ctx: order.append(2))
        manager.add_hook(HookPoint.ON_LLM_CALL, lambda ctx: order.append(3))

        asyncio.run(manager.trigger(HookContext(point=HookPoint.ON_LLM_CALL)))

        assert order == [1, 2, 3], f"Expected [1,2,3], got {order}"

    def test_hook_remove(self):
        """Removed hooks should not fire."""
        manager = HookManager()
        calls = []

        def my_hook(ctx):
            calls.append(1)

        manager.add_hook(HookPoint.ON_AGENT_START, my_hook)
        asyncio.run(manager.trigger(HookContext(point=HookPoint.ON_AGENT_START)))
        assert len(calls) == 1

        manager.remove_hook(HookPoint.ON_AGENT_START, my_hook)
        asyncio.run(manager.trigger(HookContext(point=HookPoint.ON_AGENT_START)))
        assert len(calls) == 1  # not called again

    def test_hook_clear(self):
        """clear() should remove all hooks."""
        manager = HookManager()
        manager.add_hook(HookPoint.ON_AGENT_START, lambda ctx: None)
        manager.add_hook(HookPoint.ON_AGENT_END, lambda ctx: None)

        assert len(manager.get_hooks(HookPoint.ON_AGENT_START)) == 1
        manager.clear()
        assert len(manager.get_hooks(HookPoint.ON_AGENT_START)) == 0


# ── 8. PromptBuilder with tools ─────────────────────────────────────────


class TestPromptBuilder:
    """Tests for PromptBuilder with tool descriptions."""

    def test_prompt_builder_with_tools(self):
        """Build prompt with tools, verify tool descriptions are present."""
        registry = ToolRegistry()

        # Register a simple tool
        from src.agent.tools import ToolDefinition

        def dummy_tool(query: str, count: int = 5) -> str:
            """A dummy tool for testing purposes.

            Args:
                query: Search query string.
                count: Number of results to return.
            """
            return f"results for {query}"

        registry.register(ToolDefinition(
            name="search",
            description="Search for information based on a query.",
            parameters=_extract_schema_from_function(dummy_tool),
            fn=dummy_tool,
        ))

        builder = PromptBuilder(tool_registry=registry)
        config = PromptConfig(model_name="qwen3:8b", memory_content="Test memory")

        prompt = builder.build(config)

        # Prompt should contain tool name
        assert "search" in prompt
        # Should contain tool description
        assert "Search for information" in prompt
        # Should contain parameters
        assert "query" in prompt
        # Should contain ReAct instruction
        assert "ReAct" in prompt
        # Should contain memory context
        assert "memory-context" in prompt
        assert "Test memory" in prompt

    def test_prompt_builder_model_adaptation(self):
        """Different models should produce different adaptation guidance."""
        registry = ToolRegistry()
        builder = PromptBuilder(tool_registry=registry)

        # Qwen model
        qwen_prompt = builder.build(PromptConfig(model_name="qwen3:8b"))
        assert "工具使用注意事项" in qwen_prompt

        # Unknown model should not have model-specific guidance
        unknown_prompt = builder.build(PromptConfig(model_name="unknown-model"))
        # Should still have ReAct instruction
        assert "ReAct" in unknown_prompt

    def test_prompt_builder_no_tools(self):
        """Builder without tools should still produce valid prompt."""
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(identity="Test assistant"))

        assert "Test assistant" in prompt
        assert "ReAct" in prompt
        # Should not contain tool section
        assert "可用工具列表" not in prompt


# ── Helper for test 8 ───────────────────────────────────────────────────

def _extract_schema_from_function(fn):
    """Import helper for schema extraction."""
    from src.agent.tools import _extract_schema_from_function as _extract
    return _extract(fn)
