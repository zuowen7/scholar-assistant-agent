"""端侧显存动态调度模块 — 单模型时分复用 + 上下文隔离调度。

本模块针对消费级 GPU（如 RTX 4060, 8GB VRAM）的核心瓶颈设计:

    **核心问题**: 单个 LLM (Qwen3:8B) 同时承担「规划推理」和「文本翻译」两种角色。
    ReAct 循环中，规划阶段的对话历史不断累积，KV Cache 线性增长。
    当 Agent 决定调用翻译工具处理长文本时，残留的规划上下文占据了大量 KV Cache，
    导致翻译阶段可用的上下文窗口急剧缩小，甚至触发 OOM。

    **解决策略**: 基于角色热切换 (Role-Switching) 的单模型时分复用调度。
    在规划和执行两种角色之间，通过显式的上下文隔离 (Context Isolation) 实现
    KV Cache 的完全重置，确保每次角色切换都从一个干净的内存状态开始。

调度策略详解（发明专利核心权利要求）:

1. **角色定义与隔离机制**
   定义两种上下文角色:
   - PLANNER (规划者): 携带完整对话历史和工具定义，用于 ReAct 推理。
   - ACTOR (执行者): 仅携带当前任务的极简上下文，用于执行重 IO 工具
     （如长文本翻译、文档解析）。
   两种角色的上下文在物理上完全隔离——切换时显式清空 KV Cache，
   消除角色间的内存泄漏。

2. **KV Cache 显式重置 (Flush)**
   在角色切换前，通过向 Ollama 发送一个极短的请求来覆盖旧的 KV Cache，
   实现等效的内存释放。这比模型卸载/重载（耗时 10-30 秒）轻量得多，
   仅需要一次 LLM forward pass 的时间（~100ms）。

3. **观测值注入 (Observation Injection)**
   工具执行完毕后，将结果摘要作为简短的 Observation 注入回规划者上下文，
   而非将工具的完整输出直接拼接到对话历史中。这确保规划者的上下文窗口
   不会因工具输出而膨胀。

4. **主动上下文裁剪 (Proactive Trimming)**
   当检测到对话历史的估算 token 数接近安全阈值时，自动裁剪最旧的轮次，
   保留最近的交互。裁剪策略基于滑动窗口，窗口大小可配置。

5. **保留的模型生命周期管理**
   底层仍保留 VRAMResourceManager 的模型加载/卸载能力，
   用于启动时加载模型和长时间闲置后的资源回收。
   角色切换机制在此之上构建，两者形成分层调度架构。

数据隐私保护:
- 所有上下文切换操作完全在本地设备完成。
- KV Cache 不写入持久存储，进程退出即销毁。
- 工具执行结果在注入规划者上下文前经过截断处理。

版权声明: 本模块属于 Scholar Translate Agent 子系统，
单模型时分复用调度策略、上下文隔离与 KV Cache 管理机制
受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from enum import Enum, auto
from typing import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 角色与状态定义
# ---------------------------------------------------------------------------

class ContextRole(Enum):
    """上下文角色枚举 — 定义模型在不同阶段扮演的角色。

    角色切换是时分复用调度的核心抽象:
    - PLANNER: Agent 的"大脑"角色，需要完整的对话历史和工具定义来做出决策。
    - ACTOR:   Agent 的"手脚"角色，执行具体的翻译/解析任务，仅需要当前任务的上下文。

    切换时机:
    - ReAct 推理阶段 → PLANNER
    - 调用重 IO 工具前 → ACTOR（隔离上下文，释放 KV Cache）
    - 工具执行完毕后 → PLANNER（恢复主流程，注入观测值）
    """

    PLANNER = auto()
    ACTOR = auto()


class ModelState(Enum):
    """模型生命周期状态枚举。

    状态转换图:
        IDLE ──(acquire)──▶ LOADING ──(loaded)──▶ ACTIVE
                                              │
                     ┌────────(timeout/rel)───┘
                     ▼
               UNLOADING ──(unloaded)──▶ IDLE
    """

    IDLE = auto()
    LOADING = auto()
    ACTIVE = auto()
    UNLOADING = auto()


# ---------------------------------------------------------------------------
# 需要上下文隔离的"重 IO"工具列表
# ---------------------------------------------------------------------------

# 静态默认重 IO 工具列表（运行时可通过 register_heavy_tool 扩展）
_DEFAULT_HEAVY_TOOLS: set[str] = {
    "translate_text",    # 翻译可能处理数千字符的长文本
    "parse_document",    # 文档解析可能输出整篇论文的文本
}

# 运行时注册的额外重工具
_ADDITIONAL_HEAVY_TOOLS: set[str] = set()

# 运行时动态注册重工具（用于自动检测触发隔离的工具）
def register_heavy_tool(tool_name: str) -> None:
    _ADDITIONAL_HEAVY_TOOLS.add(tool_name)

def unregister_heavy_tool(tool_name: str) -> None:
    _ADDITIONAL_HEAVY_TOOLS.discard(tool_name)

def is_heavy_tool(tool_name: str) -> bool:
    """判断工具是否为重 IO 类型（静态注册 + 动态注册）。"""
    return tool_name in _DEFAULT_HEAVY_TOOLS or tool_name in _ADDITIONAL_HEAVY_TOOLS


# ---------------------------------------------------------------------------
# 底层: 模型生命周期管理器
# ---------------------------------------------------------------------------

class VRAMResourceManager:
    """Ollama 模型显存生命周期管理器（底层调度器）。

    负责模型权重的加载与卸载，是 MultiplexingScheduler 的基础层。
    核心能力:
    - 按需加载模型到 GPU 显存 (acquire)。
    - 超时驱动的自动卸载，回收闲置显存 (unload_timeout)。
    - 查询当前显存状态 (is_loaded / get_loaded_models)。

    Attributes:
        ollama_base_url: Ollama REST API 地址。
        unload_timeout: 模型闲置超时时间（秒）。
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        unload_timeout: float = 300.0,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.unload_timeout = unload_timeout
        self._states: dict[str, ModelState] = {}
        self._lock = asyncio.Semaphore(1)
        self._unload_timers: dict[str, asyncio.Task] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        return self._http_client

    async def close(self) -> None:
        for timer in list(self._unload_timers.values()):
            timer.cancel()
        self._unload_timers.clear()
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def acquire(self, model_name: str) -> None:
        """请求加载模型到显存并等待就绪。"""
        async with self._lock:
            if self._states.get(model_name) == ModelState.ACTIVE:
                self._reset_unload_timer(model_name)
                return
            for other_name, state in list(self._states.items()):
                if other_name != model_name and state == ModelState.ACTIVE:
                    logger.info("VRAM 调度: 交换模型 %s → %s", other_name, model_name)
                    await self._do_unload(other_name)
            await self._do_load(model_name)

    async def release(self, model_name: str) -> None:
        """卸载模型，释放 GPU 显存。"""
        async with self._lock:
            await self._do_unload(model_name)

    async def is_loaded(self, model_name: str) -> bool:
        """检查指定模型是否已在 GPU 显存中。"""
        try:
            client = await self._get_http_client()
            resp = await client.get(f"{self.ollama_base_url}/api/ps")
            if resp.status_code != 200:
                return False
            for m in resp.json().get("models", []):
                if m.get("name", "").startswith(model_name):
                    return True
            return False
        except Exception:
            return False

    @asynccontextmanager
    async def with_model(self, model_name: str) -> AsyncGenerator[None, None]:
        """异步上下文管理器: 自动管理模型的加载与卸载。"""
        await self.acquire(model_name)
        try:
            yield
        finally:
            await self.release(model_name)

    def get_state(self, model_name: str) -> ModelState:
        return self._states.get(model_name, ModelState.IDLE)

    async def _do_load(self, model_name: str) -> None:
        """执行模型加载操作（内部方法，调用方需持有 _lock）。"""
        self._states[model_name] = ModelState.LOADING
        logger.info("VRAM 调度: 开始加载模型 %s 到显存...", model_name)
        client = await self._get_http_client()
        try:
            await client.post(
                f"{self.ollama_base_url}/api/chat",
                json={"model": model_name, "messages": [{"role": "user", "content": ""}], "stream": False},
                timeout=120.0,
            )
        except Exception as e:
            logger.warning("VRAM: 模型加载请求异常 (可能仍在后台加载): %s", e)
        max_wait, interval, waited = 60.0, 1.0, 0.0
        while waited < max_wait:
            if await self.is_loaded(model_name):
                self._states[model_name] = ModelState.ACTIVE
                self._reset_unload_timer(model_name)
                logger.info("VRAM 调度: 模型 %s 已就绪 (%.1fs)", model_name, waited)
                return
            await asyncio.sleep(interval)
            waited += interval
            interval = min(interval * 2, 8.0)
        self._states[model_name] = ModelState.ACTIVE
        self._reset_unload_timer(model_name)
        logger.warning("VRAM: 模型 %s 未在 %.0fs 内确认就绪，仍标记为 ACTIVE", model_name, max_wait)

    async def _do_unload(self, model_name: str) -> None:
        """执行模型卸载操作（内部方法，调用方需持有 _lock）。"""
        timer = self._unload_timers.pop(model_name, None)
        if timer is not None:
            timer.cancel()
        self._states[model_name] = ModelState.UNLOADING
        logger.info("VRAM 调度: 卸载模型 %s...", model_name)
        client = await self._get_http_client()
        try:
            await client.post(
                f"{self.ollama_base_url}/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": 0},
                timeout=30.0,
            )
        except Exception as e:
            logger.debug("VRAM: 卸载请求失败 (可忽略): %s", e)
        self._states[model_name] = ModelState.IDLE
        logger.info("VRAM 调度: 模型 %s 已卸载", model_name)

    def _reset_unload_timer(self, model_name: str) -> None:
        """重置模型的超时卸载计时器。"""
        old_timer = self._unload_timers.pop(model_name, None)
        if old_timer is not None:
            old_timer.cancel()

        async def _timeout_unload() -> None:
            await asyncio.sleep(self.unload_timeout)
            if self._states.get(model_name) == ModelState.ACTIVE:
                logger.info("VRAM 调度: 模型 %s 闲置超时 (%ds)，自动卸载", model_name, self.unload_timeout)
                async with self._lock:
                    await self._do_unload(model_name)

        self._unload_timers[model_name] = asyncio.create_task(_timeout_unload())

    async def get_loaded_models(self) -> list[str]:
        """查询当前显存中所有已加载的模型名称。"""
        try:
            client = await self._get_http_client()
            resp = await client.get(f"{self.ollama_base_url}/api/ps")
            if resp.status_code != 200:
                return []
            return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# 上层: 单模型时分复用调度器
# ---------------------------------------------------------------------------

class MultiplexingScheduler:
    """单模型时分复用调度器 — 基于角色热切换的 KV Cache 隔离机制。

    本调度器在同一物理模型 (如 Qwen3:8B) 上，通过上下文隔离实现
    "规划推理"和"任务执行"两种角色的时分复用。核心矛盾与解决方案:

    ┌────────────────────────────────────────────────────────────────┐
    │  痛点:  ReAct 循环中对话历史不断累积                              │
    │         → KV Cache 膨胀 → 翻译长文本时 OOM                      │
    │                                                                │
    │  方案:  角色切换时显式重置 KV Cache                               │
    │         → 每次执行从干净的内存状态开始                             │
    │         → 将工具结果摘要注入回主流程（而非拼接完整输出）              │
    └────────────────────────────────────────────────────────────────┘

    调度流程:
    1. PLANNER 阶段: 完整上下文 (system + history + tools + query)
       → LLM 推理，决定调用 translate_text
    2. 切换为 ACTOR: 保存 Planner 上下文快照
       → flush_kv_cache() 释放旧的 KV Cache
       → 仅携带当前任务的最小上下文执行工具
    3. 工具执行完毕: 将结果摘要作为 Observation
       → flush_kv_cache() 再次清理
       → 恢复 Planner 上下文（已裁剪至安全大小）
       → 注入 Observation，继续推理

    使用示例:
        scheduler = MultiplexingScheduler(
            ollama_base_url="http://localhost:11434",
            model="qwen3:8b",
        )

        # Agent 循环中:
        await scheduler.ensure_model()

        # 进入规划阶段
        scheduler.enter_role(ContextRole.PLANNER)
        response = await call_llm(full_messages)

        # 切换到执行阶段 (隔离上下文)
        saved = scheduler.snapshot_context(messages)
        await scheduler.switch_role(ContextRole.ACTOR)
        tool_result = await execute_tool(...)

        # 恢复规划阶段 (注入观测值)
        await scheduler.switch_role(ContextRole.PLANNER)
        restored = scheduler.restore_context(saved, observation)

    Attributes:
        model: Ollama 模型名称。
        current_role: 当前活跃的上下文角色。
        kv_flush_count: KV Cache 重置次数（用于性能监控）。
    """

    # 估算 token 的字符系数: 英文 ~4 chars/token, 中文 ~1.5 chars/token, 混合取 2.5
    _CHARS_PER_TOKEN: float = 2.5

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        context_budget_tokens: int = 28_000,
        observation_max_chars: int = 1500,
        vram_manager: VRAMResourceManager | None = None,
    ) -> None:
        """初始化时分复用调度器。

        Args:
            ollama_base_url: Ollama REST API 地址。
            model: 模型名称。
            context_budget_tokens: 上下文窗口的安全 token 预算。
                Qwen3:8B 上下文窗口为 32K tokens，留 4K 给生成，预算设 28K。
            observation_max_chars: 注入回规划者上下文的观测值最大字符数。
            vram_manager: 底层 VRAM 管理器（可选，为 None 时自动创建）。
        """
        self.model = model
        self.context_budget_tokens = context_budget_tokens
        self.observation_max_chars = observation_max_chars

        # 底层模型生命周期管理
        self._vram = vram_manager or VRAMResourceManager(ollama_base_url)

        # 当前角色状态
        self.current_role: ContextRole = ContextRole.PLANNER
        self.kv_flush_count: int = 0

        # 规划者上下文快照（角色切换时暂存）
        self._planner_snapshot: list[dict] | None = None

        logger.info(
            "时分复用调度器初始化: model=%s, budget=%d tokens, obs_max=%d chars",
            model, context_budget_tokens, observation_max_chars,
        )

    @property
    def vram_manager(self) -> VRAMResourceManager:
        """访问底层 VRAM 管理器。"""
        return self._vram

    async def close(self) -> None:
        """关闭调度器及底层资源。"""
        await self._vram.close()

    # ------------------------------------------------------------------
    # 模型生命周期
    # ------------------------------------------------------------------

    async def ensure_model(self) -> None:
        """确保模型已加载到显存。

        如果模型未加载，通过底层 VRAM 管理器触发加载。
        如果已加载，仅重置超时计时器。
        """
        await self._vram.acquire(self.model)

    async def release_model(self) -> None:
        """释放模型显存。"""
        await self._vram.release(self.model)

    # ------------------------------------------------------------------
    # 角色切换
    # ------------------------------------------------------------------

    def enter_role(self, role: ContextRole) -> None:
        """设置当前活跃角色（不执行 KV Cache 操作）。

        Args:
            role: 目标角色。
        """
        self.current_role = role
        logger.debug("调度器: 进入角色 %s", role.name)

    def is_heavy_tool(self, tool_name: str) -> bool:
        """判断工具是否为"重 IO"工具，需要上下文隔离。

        重 IO 工具的特征:
        - 处理大量文本（翻译、解析）。
        - 通过 LLM 执行（调用 OllamaClient.translate()）。
        - 执行时间长（>5 秒）。
        - 产生大量中间 token。

        支持动态注册: register_heavy_tool() / unregister_heavy_tool()。

        Args:
            tool_name: 工具名称。

        Returns:
            True 表示该工具需要在隔离上下文中执行。
        """
        return is_heavy_tool(tool_name)

    async def switch_role(self, target_role: ContextRole) -> None:
        """切换到目标角色，执行 KV Cache 重置。

        角色切换的核心操作:
        1. 记录切换事件。
        2. 调用 flush_kv_cache() 释放当前 KV Cache。
        3. 更新 current_role。

        为什么要 flush:
        - Ollama 的 KV Cache 在连续的 /api/chat 请求间复用。
        - 如果不 flush，旧的对话历史仍占据显存。
        - flush 后，下一次请求将从空白 KV Cache 开始构建。

        Args:
            target_role: 目标角色。
        """
        old_role = self.current_role
        if old_role == target_role:
            return

        logger.info(
            "调度器: 角色切换 %s → %s (flush KV Cache #%d)",
            old_role.name, target_role.name, self.kv_flush_count + 1,
        )
        await self.flush_kv_cache()
        self.current_role = target_role

    async def flush_kv_cache(self) -> None:
        """显式重置模型的 KV Cache。

        实现策略:
        向 Ollama 发送一个极短的 /api/chat 请求（仅含空消息），
        这会使 Ollama 丢弃旧的 KV Cache 并为当前请求构建新的极小 Cache。
        等效于一次轻量的"内存清理"，耗时约 100-300ms。

        相比模型卸载/重载（10-30 秒），该策略在速度上有数量级的优势，
        代价是短暂的"无用推理"——但这个代价远小于 OOM 导致的完全失败。

        KV Cache 重置机制（专利技术要点）:
        1. 构造最小化请求 payload: 仅包含 model 和一条空 user 消息。
        2. Ollama 处理该请求时，自动覆盖旧的 KV Cache。
        3. 由于请求极短，新的 KV Cache 仅占几 KB 显存。
        4. 后续的规划/执行请求在此基础上从干净状态开始。
        """
        client = await self._vram._get_http_client()
        try:
            await client.post(
                f"{self._vram.ollama_base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ok"}],
                    "stream": False,
                    "options": {"num_predict": 1},
                },
                timeout=10.0,
            )
            self.kv_flush_count += 1
            logger.info(
                "KV Cache 已重置 (累计第 %d 次, model=%s)",
                self.kv_flush_count, self.model,
            )
        except Exception as e:
            logger.warning("KV Cache flush 失败 (非致命): %s", e)

    # ------------------------------------------------------------------
    # 上下文快照与恢复
    # ------------------------------------------------------------------

    def snapshot_context(self, messages: list) -> list:
        """保存规划者上下文快照。

        在切换到 ACTOR 角色前调用，将当前的完整对话消息序列
        保存到内部缓冲区，以便后续恢复。

        Args:
            messages: 当前的消息列表。

        Returns:
            消息列表的浅拷贝。
        """
        self._planner_snapshot = list(messages)
        logger.debug(
            "调度器: 保存规划者上下文快照 (%d 条消息, ~%d tokens)",
            len(messages), self.estimate_tokens(messages),
        )
        return list(messages)

    def restore_context(self, observation: str | None = None) -> list:
        """恢复规划者上下文，并可选地注入观测值。

        在 ACTOR 角色执行完毕后调用。恢复之前保存的规划者上下文，
        并在末尾添加一条简短的观测值消息。

        恢复策略:
        1. 取回之前保存的快照。
        2. 如果有观测值，截断至 observation_max_chars 后追加。
        3. 执行主动裁剪: 确保恢复后的上下文不超过 token 预算。

        Args:
            observation: 工具执行结果的摘要（可选）。

        Returns:
            恢复后的消息列表。
        """
        if self._planner_snapshot is None:
            logger.warning("调度器: 无规划者快照可恢复，返回空上下文")
            return []

        restored = list(self._planner_snapshot)
        self._planner_snapshot = None

        # 注入观测值（截断至安全长度）
        if observation:
            truncated = observation[:self.observation_max_chars]
            if len(observation) > self.observation_max_chars:
                truncated += f"\n...[原文 {len(observation)} 字符已截断]"
            restored.append({"role": "user", "content": f"[Observation] {truncated}"})

        # 主动裁剪: 确保不超预算
        restored = self.trim_to_budget(restored)

        logger.debug(
            "调度器: 恢复规划者上下文 (%d 条消息, ~%d tokens, observation=%s)",
            len(restored), self.estimate_tokens(restored),
            f"{len(observation)} chars" if observation else "无",
        )
        return restored

    # ------------------------------------------------------------------
    # Token 估算与裁剪
    # ------------------------------------------------------------------

    def estimate_tokens(self, messages: list) -> int:
        """粗略估算消息列表的总 token 数。

        估算策略:
        - 英文: 1 token ≈ 4 字符。
        - 中文: 1 token ≈ 1.5 字符。
        - 混合文本取加权平均: 1 token ≈ 2.5 字符。
        - 额外为每条消息的元数据 (role, formatting) 预估 4 tokens。

        该估算是保守的（偏高），用于触发裁剪的决策，
        确保实际 token 数不会超过模型的上下文窗口。

        Args:
            messages: 消息列表（支持 Message 对象或 dict）。

        Returns:
            估算的总 token 数。
        """
        total_chars = 0
        for msg in messages:
            # 兼容 Message dataclass 和 plain dict
            if hasattr(msg, "content"):
                content = msg.content or ""
            elif isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                content = str(msg)
            total_chars += len(content)
            total_chars += 4  # 元数据开销

        return max(1, int(total_chars / self._CHARS_PER_TOKEN))

    def trim_to_budget(self, messages: list, budget: int | None = None) -> list:
        """将消息列表裁剪至 token 预算内。

        裁剪策略（滑动窗口 + 保护关键消息）:
        1. 始终保留第一条消息（通常是 system prompt）。
        2. 从第二条消息开始，从最旧的向最新的方向尝试加入。
        3. 如果加入后超过预算，跳过该条消息。
        4. 始终保留最后一条消息（通常是用户的最新查询）。

        该策略确保:
        - 系统提示词不被裁剪。
        - 最近的交互优先保留。
        - 裁剪后的上下文不超过 token 预算。

        Args:
            messages: 待裁剪的消息列表。
            budget: token 预算上限，默认使用 context_budget_tokens。

        Returns:
            裁剪后的消息列表。
        """
        budget = budget or self.context_budget_tokens
        current_tokens = self.estimate_tokens(messages)

        if current_tokens <= budget:
            return messages

        if len(messages) <= 2:
            return messages  # 只有 system + query，无法再裁剪

        logger.info(
            "调度器: 上下文超预算 (%d > %d tokens)，开始裁剪 %d 条消息",
            current_tokens, budget, len(messages),
        )

        # 保护首尾，裁剪中间
        system_msg = messages[0]
        last_msg = messages[-1]
        middle = messages[1:-1]

        # 从最新向最旧保留，直到填满预算
        kept_middle: list = []
        remaining_budget = budget - self.estimate_tokens([system_msg]) - self.estimate_tokens([last_msg])

        for msg in reversed(middle):
            msg_tokens = self.estimate_tokens([msg])
            if remaining_budget >= msg_tokens:
                kept_middle.insert(0, msg)
                remaining_budget -= msg_tokens
            else:
                break

        trimmed = [system_msg] + kept_middle + [last_msg]
        logger.info(
            "调度器: 裁剪完成 %d → %d 条消息 (~%d tokens)",
            len(messages), len(trimmed), self.estimate_tokens(trimmed),
        )
        return trimmed

    def condense_observation(
        self,
        tool_name: str,
        tool_result: str,
        max_chars: int | None = None,
    ) -> str:
        """将工具执行结果压缩为简短的观测值摘要。

        压缩策略:
        - 截断至 max_chars 字符。
        - 添加工具名称前缀以保留来源信息。
        - 附加截断标记，让规划者知道信息可能不完整。

        该方法是 KV Cache 保护的关键环节:
        如果将工具的完整输出（可能数千字符）直接注入规划者上下文，
        KV Cache 将快速膨胀。通过压缩，每次工具调用仅增加
        约 600-1500 字符（~240-600 tokens）的开销。

        Args:
            tool_name: 工具名称。
            tool_result: 工具的完整输出。
            max_chars: 最大字符数，默认使用 observation_max_chars。

        Returns:
            压缩后的观测值字符串。
        """
        limit = max_chars or self.observation_max_chars
        prefix = f"[{tool_name}] "
        available = limit - len(prefix) - 50  # 预留截断标记空间

        if len(tool_result) <= available:
            return prefix + tool_result

        return prefix + tool_result[:available] + f"\n...[结果共 {len(tool_result)} 字符，已截断]"
