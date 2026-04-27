"""Agent 模块终端集成测试 — 不启动 Web 服务器，直接在终端验证完整交互。

测试场景:
1. RAG 文档入库与语义检索
2. 工具注册与直接调用 (翻译、解析)
3. 完整 Agent ReAct 循环 (入库 → 提问 → 检索+翻译 → 输出)

前置条件:
- 本地 Ollama 服务已启动: ollama serve
- 已拉取模型: ollama pull qwen3:8b
- 已安装依赖: pip install -r requirements.txt

用法:
    cd python
    python test_agent.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time

# Windows GBK 终端兼容: 强制 stdout 使用 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保可以导入 src 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── 测试颜色输出 ─────────────────────────────────────────────────────────

def _header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def _step(text: str) -> None:
    print(f"  >> {text}")


def _result(text: str) -> None:
    print(f"    [OK] {text}")


def _error(text: str) -> None:
    print(f"    [FAIL] {text}")


def _output(text: str) -> None:
    # 缩进输出，每行限制 100 字符
    for line in text.split("\n"):
        display = line[:100] + ("..." if len(line) > 100 else "")
        print(f"    | {display}")


# ── 测试 1: RAG 文档入库与检索 ──────────────────────────────────────────

def test_rag() -> None:
    _header("测试 1: RAG 文档入库与语义检索")
    tmpdir = tempfile.mkdtemp(prefix="scholar_rag_test_")
    try:
        from src.agent.rag import RAGStore

        store = RAGStore(persist_dir=tmpdir, collection_name="test_docs")
        _result(f"RAG 存储初始化完成: {store.count_chunks()} 条记录")

        # 入库示例文本
        sample_text = """
        Attention Is All You Need

        Abstract: The dominant sequence transduction models are based on complex recurrent
        or convolutional neural networks that include an encoder and a decoder.
        The best performing models also connect the encoder and decoder through an attention
        mechanism. We propose a new simple network architecture, the Transformer, based
        solely on attention mechanisms, dispensing with recurrence and convolutions entirely.

        Introduction: Recurrent neural networks and convolutional neural networks have been
        widely used for sequence modeling tasks. However, their sequential nature prevents
        parallelization during training. The Transformer model addresses this limitation
        by using self-attention mechanisms to capture dependencies between tokens regardless
        of their distance in the sequence.

        The key innovation is the scaled dot-product attention mechanism, which computes
        the attention weights as softmax(QK^T / sqrt(d_k))V, where Q, K, V are query,
        key, and value matrices respectively. This allows the model to attend to all
        positions in the sequence simultaneously.
        """

        count = store.ingest_document(
            doc_id="transformer_paper",
            text=sample_text,
            metadata={"title": "Attention Is All You Need"},
        )
        _result(f"入库完成: {count} 个文本块")

        # 语义检索
        results = store.retrieve_context("什么是 self-attention 机制", top_k=3)
        _step("检索 '什么是 self-attention 机制':")
        for i, r in enumerate(results):
            _output(f"[{i + 1}] (distance={r['distance']:.4f}) {r['text'][:120]}...")

        # 列出文档
        docs = store.list_documents()
        _result(f"已入库文档: {len(docs)} 篇")
        for doc in docs:
            _output(f"  {doc.id}: {doc.chunk_count} 块, title={doc.title}")

        # 删除文档
        store.delete_document("transformer_paper")
        _result(f"删除后剩余: {store.count_chunks()} 条记录")

    except ImportError as e:
        _error(f"chromadb 未安装: {e}")
        _step("请运行: pip install chromadb")
    except Exception as e:
        _error(f"测试失败: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 测试 2: 工具注册与调用 ──────────────────────────────────────────────

def test_tools() -> None:
    _header("测试 2: 工具注册与调用")
    try:
        from src.agent.tools import ToolRegistry, create_default_registry, _crawl_arxiv

        # 创建空注册表
        registry = ToolRegistry()
        _result("空注册表创建成功")

        # 创建默认注册表（无翻译客户端）
        default_registry = create_default_registry()
        tools = default_registry.list_tools()
        _result(f"默认工具注册: {[t.name for t in tools]}")

        # 查看工具的 Ollama 格式
        ollama_tools = default_registry.to_ollama_tools()
        for t in ollama_tools:
            func = t.get("function", {})
            _output(f"  {func.get('name')}: {func.get('description', '')[:60]}...")

        # 测试 arXiv 爬取
        _step("测试 arXiv 搜索...")
        result = _crawl_arxiv("transformer attention", max_results=2)
        _output(result[:300])

    except Exception as e:
        _error(f"测试失败: {e}")


# ── 测试 3: 完整 Agent 循环 ────────────────────────────────────────────

async def test_agent_loop() -> None:
    _header("测试 3: 完整 Agent ReAct 循环 (需要 Ollama 运行)")
    try:
        import yaml
        from src.agent.agent import AgentLoop
        from src.agent.rag import RAGStore
        from src.agent.tools import create_default_registry

        # 加载配置
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config", "default.yaml",
        )
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        agent_cfg = config.get("agent", {})
        rag_cfg = agent_cfg.get("rag", {})

        # 初始化 RAG 存储
        tmpdir = tempfile.mkdtemp(prefix="scholar_agent_test_")
        store = RAGStore(
            persist_dir=tmpdir,
            collection_name=rag_cfg.get("collection_name", "test_docs"),
            chunk_size=rag_cfg.get("chunk_size", 512),
            chunk_overlap=rag_cfg.get("chunk_overlap", 64),
        )

        # 入库示例文档
        sample = """
        Attention Is All You Need (Vaswani et al., 2017)

        The Transformer model uses self-attention mechanisms to process sequences.
        The key innovation is the multi-head attention mechanism, which allows the model
        to jointly attend to information from different representation subspaces at
        different positions. The attention function can be described as mapping a query
        and a set of key-value pairs to an output. The output is computed as a weighted
        sum of the values, where the weight assigned to each value is computed by a
        compatibility function of the query with the corresponding key.

        The Transformer achieved state-of-the-art results on machine translation tasks,
        specifically on the WMT 2014 English-to-German and English-to-French translation
        tasks. The model requires significantly less time to train compared to
        architectures based on recurrent or convolutional layers.
        """

        count = store.ingest_document(
            doc_id="attention_paper",
            text=sample,
            metadata={"title": "Attention Is All You Need"},
        )
        _result(f"RAG 入库完成: {count} 个文本块")

        # 初始化工具注册表（带 RAG）
        trans_cfg = config.get("translator", {})
        registry = create_default_registry(rag_store=store)

        # Phase 1/2/3: 上下文工程 + 记忆 + Skill + 轨迹
        from src.agent.context_compressor import ContextCompressor
        from src.agent.memory import MemoryManager
        from src.agent.prompt_builder import PromptBuilder
        from src.agent.skill_system import SkillRegistry
        from src.agent.trajectory import TrajectoryRecorder

        agent_data = tmpdir + "/agent"
        memory_mgr = MemoryManager(data_dir=agent_data)
        skill_reg = SkillRegistry(data_dir=agent_data + "/skills")
        traj_rec = TrajectoryRecorder(data_dir=agent_data + "/trajectories")
        compressor = ContextCompressor(
            ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
            summary_model=agent_cfg.get("model", "qwen3:8b"),
        )
        prompt_b = PromptBuilder(tool_registry=registry)

        # 创建 Agent
        agent = AgentLoop(
            ollama_base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
            model=agent_cfg.get("model", "qwen3:8b"),
            tool_registry=registry,
            max_steps=agent_cfg.get("max_steps", 10),
            system_prompt=agent_cfg.get("system_prompt", ""),
            temperature=agent_cfg.get("temperature", 0.3),
            num_predict=agent_cfg.get("num_predict", 4096),
            context_compressor=compressor,
            prompt_builder=prompt_b,
            memory_manager=memory_mgr,
            skill_registry=skill_reg,
            trajectory_recorder=traj_rec,
        )

        # 执行查询
        queries = [
            "请搜索已入库文档中关于 attention 机制的内容，并用中文解释",
        ]

        for query in queries:
            _step(f"用户: {query}")
            print()
            async for event in agent.run(query):
                if event.type == "thinking":
                    print(f"    [THINK] {event.content}")
                elif event.type == "tool_call":
                    args_str = ""
                    if event.metadata and "arguments" in event.metadata:
                        args_str = str(event.metadata["arguments"])[:80]
                    print(f"    [TOOL] {event.content} | args: {args_str}")
                elif event.type == "tool_result":
                    duration = ""
                    if event.metadata and "duration_ms" in event.metadata:
                        duration = f" ({event.metadata['duration_ms']}ms)"
                    print(f"    [RESULT] {duration}: {event.content[:150]}...")
                elif event.type == "response":
                    print(f"\n    [AGENT] {event.content}")
                elif event.type == "error":
                    print(f"    [ERROR] {event.content}")
            print()

        # 清理
        await agent.close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    except ImportError as e:
        _error(f"缺少依赖: {e}")
        _step("请运行: pip install -r requirements.txt")
    except Exception as e:
        _error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


# ── 测试 4: Phase 1/2/3 模块 ────────────────────────────────────────────

def test_phase_modules() -> None:
    _header("测试 5: Phase 1/2/3 模块（上下文工程、记忆、Skill、轨迹、Hook、错误分类）")
    tmpdir = tempfile.mkdtemp(prefix="scholar_phase_test_", ignore_cleanup_errors=True)
    try:
        from src.agent.context_compressor import ContextCompressor
        from src.agent.memory import MemoryManager
        from src.agent.prompt_builder import PromptBuilder
        from src.agent.skill_system import SkillRegistry
        from src.agent.trajectory import TrajectoryRecorder
        from src.agent.hooks import HookManager, HookPoint, HookContext
        from src.agent.error_classifier import classify_error, ErrorType, get_recovery, RetryManager
        from src.agent.tools import ToolRegistry

        # MemoryManager
        mem = MemoryManager(data_dir=tmpdir + "/agent")
        mem.add_memory("测试记忆", category="fact", importance=0.8)
        mem.save_conversation("你好", "你好！有什么可以帮你？", success=True)
        stats = mem.get_stats()
        assert stats["memories_count"] == 1 and stats["conversations_count"] == 1
        _result(f"MemoryManager: {stats}")

        ctx = mem.get_memory_context("测试")
        assert "测试记忆" in ctx
        _result("get_memory_context 检索到相关记忆")

        # SkillRegistry
        skills = SkillRegistry(data_dir=tmpdir + "/agent/skills")
        s = skills.create_skill(
            name="test_skill",
            trigger="测试技能",
            description="用于测试的技能",
            steps=["步骤1", "步骤2"],
            notes=["注意1"],
        )
        assert skills.get("test_skill") is not None
        matched = skills.match("执行测试技能")
        assert matched is not None and matched.name == "test_skill"
        _result(f"SkillRegistry: 创建+匹配成功 ({skills.list_skills()})")

        # TrajectoryRecorder
        traj = TrajectoryRecorder(data_dir=tmpdir + "/agent/trajectories")
        traj.start("测试查询", model="test")
        traj.add_turn("user", "测试查询")
        traj.add_turn("tool", "结果", tool_name="test", duration_ms=100)
        trajectory = traj.finish("测试回答", success=True)
        assert trajectory is not None and trajectory.success
        recent = traj.get_recent(limit=5)
        assert len(recent) == 1
        _result(f"TrajectoryRecorder: 保存+读取成功 ({len(recent)} 条)")

        # HookManager
        hooks = HookManager()
        calls = []
        hooks.add_hook(HookPoint.ON_TOOL_CALL, lambda ctx: calls.append(ctx.data.get("tool_name")))
        hooks.trigger_sync(HookContext(point=HookPoint.ON_TOOL_CALL, data={"tool_name": "translate"}))
        assert calls == ["translate"]
        _result(f"HookManager: 同步触发成功 (calls={calls})")

        # ErrorClassifier
        err = Exception("rate limit exceeded")
        et = classify_error(err)
        assert et == ErrorType.RATE_LIMIT
        recovery = get_recovery(et)
        assert recovery.action == "retry"
        mgr = RetryManager()
        assert mgr.can_retry(et) is True
        msg = mgr.get_feedback_message(et)
        assert "等待" in msg
        _result(f"ErrorClassifier: 分类+恢复策略正确 ({et.value} → {recovery.action})")

        # ContextCompressor（同步部分）
        comp = ContextCompressor(summary_model=None)
        assert not comp.should_compress([{"role": "user", "content": "短消息"}])
        _result("ContextCompressor: token 估算正常")

        # PromptBuilder
        from src.agent.prompt_builder import PromptConfig
        pb = PromptBuilder(tool_registry=ToolRegistry())
        prompt = pb.build(PromptConfig(model_name="qwen3:8b"))
        assert "qwen" in prompt.lower()
        _result("PromptBuilder: 动态拼装正常")

        mem.close()

    except Exception as e:
        _error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 主入口 ─────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("=" * 60)
    print("  Scholar Assistant Agent - Test Suite")
    print("=" * 60)
    print()

    # 测试 1: RAG（同步）
    test_rag()

    # 测试 2: 工具注册（同步）
    test_tools()

    # 测试 4: Phase 1/2/3 模块（同步，不需要 Ollama）
    test_phase_modules()

    # 测试 3: 需要 Ollama（异步）
    _header("以下测试需要 Ollama 运行 (ollama serve + qwen3:8b)")
    asyncio.run(test_agent_loop())

    print()
    print("测试完成。")


if __name__ == "__main__":
    main()
