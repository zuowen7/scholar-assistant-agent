# Agent V2 核心代码架构 Review 报告

> Reviewer: Senior Developer（高级开发工程师）
> Review 日期: 2026-07-20
> Review 范围: `python/src/agent_v2/router.py`, `runtime/conversation.py`, `runtime/permissions.py`
> Review 方法: 抽样阅读 + grep 模式扫描 + 跨文件追踪

## 一、总体评价

Agent V2 的整体架构是**有想法的**——参考 claw-code 设计，模块边界清晰（runtime / tools / providers / skills / hooks / plugins / mcp），类型注解完整，docstring 规范。审批流程有 timeout 保护，429 重试用指数退避，session 持久化到 JSONL 可恢复。

但在**资源生命周期管理**和**错误处理**上有几个明确的问题，其中 1 个是 P0 必须修。

## 二、问题清单

> **修复状态更新（2026-07-20）**: P0 + 2×P1 + 2×P2 已全部修复，1796 个测试通过（618 原有 agent_v2 + 15 新增 + 1163 unit）。详见文末"修复记录"。

### 🔴 P0 — 内存泄漏：session 池永不清理 ✅ 已修复

**位置**: `python/src/agent_v2/router.py:442-449`

```python
async def _cleanup_pool():
    """Remove stale sessions."""
    now = time.monotonic()
    stale = []
    async with _SESSION_LOCK:
        for sid, rt in _SESSION_POOL.items():
            # Stale if older than 1 hour and not the only session
            pass  # Simple cleanup — don't auto-evict unless requested
```

**问题**:
- `_SESSION_POOL: dict[str, ConversationRuntime] = {}` 是模块级全局字典
- 每个新 session 通过 `POST /api/agent/v2/chat` 进来都会被加入池（router.py:476, 556）
- 但 `_cleanup_pool` 函数体是 `pass`，`_SESSION_TTL = 3600` 定义了却没用上
- 池只增不减，长时间运行（桌面应用场景常见）会持续累积内存
- 每个 `ConversationRuntime` 持有 `Session`（含完整消息历史）、`ToolRegistry`、`provider` 引用，单实例可能数 MB

**影响**: 桌面应用运行数天后内存可能涨到 GB 级别，且无回收机制。

**修复建议**:
```python
async def _cleanup_pool():
    """Remove stale sessions (TTL-based)."""
    now = time.monotonic()
    # 需要在 ConversationRuntime 创建时记录 last_active_monotonic
    stale_sids = [
        sid for sid, rt in _SESSION_POOL.items()
        if now - getattr(rt, '_last_active', now) > _SESSION_TTL
        and not getattr(rt, '_is_streaming', False)
    ]
    if stale_sids:
        async with _SESSION_LOCK:
            for sid in stale_sids:
                _SESSION_POOL.pop(sid, None)
        logger.info("Cleaned up %d stale sessions", len(stale_sids))

# 在 app 启动时注册后台任务
@app.on_event("startup")
async def _schedule_cleanup():
    async def _loop():
        while True:
            await asyncio.sleep(600)  # 每 10 分钟清理一次
            await _cleanup_pool()
    asyncio.create_task(_loop())
```

**验证**: 启动应用，连续发起 100 个 session，观察 `_SESSION_POOL` 大小是否稳定。

---

### 🟠 P1 — workflow cleanup / delete 是 stub ✅ 已修复

**位置**: `python/src/agent_v2/router.py:603-609`

```python
@app.post(f"{prefix}/workflows/cleanup")
async def v2_workflow_cleanup():
    return {"status": "ok"}

@app.delete(f"{prefix}/workflows/{{workflow_id}}")
async def v2_workflow_delete(workflow_id: str):
    return {"status": "ok", "deleted": workflow_id}
```

**问题**: 接口名是 cleanup/delete，但实际什么都不做。前端调用后会以为清理成功，但 session 还在内存池和磁盘 JSONL 文件里。这会**误导前端状态**，加剧 P0 的内存泄漏。

**修复建议**: 至少实现最小可用版本：
```python
@app.post(f"{prefix}/workflows/cleanup")
async def v2_workflow_cleanup():
    """清理所有过期 session（内存 + 磁盘）。"""
    await _cleanup_pool()  # 复用 P0 修复
    # 可选：扫描 _SESSION_DIR，删除超过 N 天的 .jsonl
    return {"status": "ok", "cleaned": True}

@app.delete(f"{prefix}/workflows/{{workflow_id}}")
async def v2_workflow_delete(workflow_id: str):
    """删除指定 workflow 的内存 session 和磁盘文件。"""
    if not _SESSION_ID_RE.match(workflow_id):
        raise HTTPException(400, "Invalid workflow_id")
    async with _SESSION_LOCK:
        _SESSION_POOL.pop(workflow_id, None)
    session_path = _SESSION_DIR / f"{workflow_id}.jsonl"
    if session_path.is_file():
        session_path.unlink()
    return {"status": "ok", "deleted": workflow_id}
```

---

### 🟠 P1 — 配置加载静默吞异常 ✅ 已修复

**位置**: `python/src/agent_v2/router.py:184, 194, 223`

```python
def _load_cloud_config() -> dict:
    ...
    try:
        with open(default_path, encoding="utf-8") as f:
            merged = yaml.safe_load(f) or {}
    except Exception:
        pass    # ← YAML 语法错误、文件权限问题全部被吞掉
```

**问题**: 三处配置加载都用 `except Exception: pass`，YAML 语法错误、文件权限问题、编码问题全部静默。用户改坏配置文件后，应用表现为"配置不生效"但无任何提示，调试极困难。

**修复建议**:
```python
except Exception as e:
    logger.warning("Failed to load %s: %s", default_path, e)
```
至少要记录日志，便于用户在 `logs/` 里排查。

---

### 🟡 P2 — 直接访问私有属性注入依赖 ✅ 已修复

**位置**: `python/src/agent_v2/router.py:398`

```python
registry._provider = provider  # 直接给 registry 设私有属性
```

**问题**: 绕过封装，直接给 `ToolRegistry` 实例塞私有属性。未来 `ToolRegistry` 内部重构（比如改成 `__slots__`）会立即破坏。

**修复建议**: 在 `ToolRegistry` 上加显式方法：
```python
class ToolRegistry:
    def set_provider(self, provider) -> None:
        """Inject the LLM provider for tools that need it (e.g., sub_agent)."""
        self._provider = provider
```

---

### 🟡 P2 — `_approval_events` 在异常路径可能泄漏 ✅ 已修复

**位置**: `python/src/agent_v2/runtime/conversation.py:285-291`

```python
self._approval_events[tb.id] = evt
try:
    await asyncio.wait_for(evt.wait(), timeout=_APPROVAL_TIMEOUT)
except asyncio.TimeoutError:
    self._approval_decisions[tb.id] = "deny"
finally:
    self._approval_events.pop(tb.id, None)
```

**现状**: finally 里有 pop，正常路径 OK。但如果在 `await asyncio.wait_for` **之前**发生异常（比如 yield 给上层时上层提前关闭 generator），事件可能未被清理。

**修复建议**: 在 `turn()` 方法结束（return 前）统一清理：
```python
async def turn(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
    try:
        # ... existing logic ...
    finally:
        # 兜底清理：确保任何退出路径都不泄漏
        self._approval_events.clear()
```

---

### 🟡 P2 — `_SESSION_POOL` 是模块级全局可变状态

**位置**: `python/src/agent_v2/router.py:65`

```python
_SESSION_POOL: dict[str, ConversationRuntime] = {}
```

**问题**: 模块级全局可变状态在测试隔离、多 worker 部署时都会有问题。当前 FastAPI 默认单 worker 可以工作，但未来扩展受限。

**长期改进建议**: 改为 `app.state.session_pool`，通过 FastAPI 依赖注入访问。这样测试时可以轻松 mock，多 worker 时每个 worker 独立。

**短期**: 保持现状，但在 AGENTS.md 里标注"当前架构假设单 worker"。

---

## 三、优点（继续保持）

| 优点 | 体现 |
|------|------|
| 模块边界清晰 | runtime / tools / providers / skills / hooks / plugins / mcp 各司其职 |
| 类型注解完整 | PEP 604 风格（`str \| None`），pydantic Field 约束输入 |
| 审批流程有 timeout | `_APPROVAL_TIMEOUT = 120.0`，避免无限等待 |
| 429 重试正确 | 指数退避（`2 ** retry`），尊重 `retry_after` |
| Session 持久化 | JSONL 格式，可恢复，支持 fork |
| 工具结果截断 | `_TOOL_RESULT_MAX_CHARS = 4000`，防止单工具结果撑爆 context |
| 历史去重 | `_append_history` 检测并去掉重复的当前消息 |
| 前端上下文标记 | `<task_constraints>` / `<active_file>` / `<editor_context>` 边界清晰 |
| 工具描述给 LLM 的指引明确 | "PREFER write_file... ONLY use str_replace for trivial single-line edits" |

## 四、修复优先级建议

| 优先级 | 问题 | 预计工时 | 建议时机 |
|--------|------|---------|---------|
| P0 | session 池清理 | 2-3 小时 | 本周内 |
| P1 | workflow cleanup/delete stub | 1 小时 | 与 P0 一起 |
| P1 | 配置加载吞异常 | 30 分钟 | 顺手修 |
| P2 | 私有属性注入 | 30 分钟 | 下次重构 registry 时 |
| P2 | approval_events 异常路径 | 30 分钟 | 加 finally 兜底 |
| P2 | 全局状态改 app.state | 半天 | 长期规划，不急 |

## 五、Review 方法论说明（给团队参考）

这次 review 用了以下方法，团队后续可以复用：

1. **入口追踪**: 从 router 入口（`/api/agent/v2/chat`）顺着调用链读
2. **资源生命周期扫描**: grep `dict\[\]` / `Map` / `pool` / `cache` / `set` 等容器，检查是否有清理逻辑
3. **异常处理扫描**: grep `except.*pass` / `except Exception:` 找静默吞异常
4. **私有属性访问**: grep `\._\w+ =` 找绕过封装的注入
5. **跨文件契约**: 确认前端监听的事件名后端一定 emit（这次 ci.yml 的 contract job 就是这个思路的固化）

**核心原则**: code review 不只是"读代码找 bug"，更是**把发现固化成自动化检查**（CI / lint rule / 测试），让问题不再复发。

---

## 六、修复记录（2026-07-20）

所有 P0/P1/P2 问题已修复并通过测试验证。

### 修改的文件

| 文件 | 修改内容 |
|------|---------|
| `python/src/agent_v2/runtime/conversation.py` | 加 `last_active_monotonic` / `_is_streaming` 属性；`turn()` 包 try/finally 兜底清理 `_approval_events`；每步更新 `last_active_monotonic` |
| `python/src/agent_v2/router.py` | 实现 `_cleanup_pool` 真实 TTL 清理；新增 `_background_cleanup_loop` 后台任务；通过 `app.state._state_agent` 集成到 lifespan（避免废弃的 `on_event`）；实现 `workflow cleanup/delete` 真实逻辑含路径穿越防护；3 处配置加载吞异常改为 `logger.warning` |
| `python/src/agent_v2/tools/registry.py` | 新增 `set_provider()` / `get_provider()` 方法，封装私有属性访问 |
| `python/src/agent_v2/tools/sub_agent.py` | 改用 `registry.get_provider()` 替代 `getattr(registry, '_provider')` |
| `python/api_factory.py` | `_lifespan` startup 阶段调用 `state_agent["startup"]`（之前只调 shutdown） |
| `python/tests/agent_v2/test_session_cleanup.py` | 新增 15 个测试覆盖所有修复 |

### 修复要点

**P0 session 池清理**:
- 清理条件：`now - last_active_monotonic > TTL` AND `not _is_streaming`
- 后台任务每 600 秒跑一次 `_cleanup_pool`
- 通过 `app.state._state_agent` 挂载到 api_factory 的 lifespan，避免废弃的 `@app.on_event`
- `_background_cleanup_loop` 自带 try/except，单次失败不杀循环

**P1 workflow cleanup/delete**:
- cleanup：清内存池 + 删过期磁盘 `.jsonl`（保护内存中 session 的文件）
- delete：删内存 + 磁盘 + 路径穿越防护（regex + defense-in-depth）+ streaming session 保护（409）

**P2 approval_events 兜底**:
- `turn()` 的 try/finally 在任何退出路径（正常 return / 异常 / generator close / 客户端断连）都清理 `_approval_events`

### 测试验证

```
tests/agent_v2/  — 633 passed (618 原有 + 15 新增)
tests/unit/      — 1163 passed, 5 skipped
总计             — 1796 passed, 0 failed, 0 regressions
```

新测试覆盖：
- `_cleanup_pool`：清 stale 非流式、保护流式、保护 fresh、空池、混合池
- `_background_cleanup_loop`：正常循环 + cancel 退出 + 错误容忍
- `workflow cleanup`：内存+磁盘清理、保护流式 session 文件
- `workflow delete`：内存+磁盘删除、regex 校验、路径穿越防护、流式 session 保护、幂等
- `ToolRegistry.set_provider/get_provider`
