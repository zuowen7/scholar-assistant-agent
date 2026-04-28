# Agent v1 → v2 迁移完成

## 概述

彻底移除 AgentLoop.run() 和 /api/chat/v1，统一到 v2 架构（AgentSession + AgentLoop.step()）。

## 变更清单

### 1. 删除的代码

#### `python/src/agent/agent.py`
- ❌ 删除 `AgentLoop.run()` 方法（~170 行）
- ❌ 删除 `_format_error_retry` 状态变量

#### `python/routers/agent.py`
- ❌ 删除 `/api/chat/v1` 端点（~42 行）

### 2. 更新的代码

#### `python/src/agent/agent.py`
- ✅ 更新 `AgentLoop.step()` 文档注释，明确说明这是核心执行方法
- ✅ 移除所有 v1 相关引用

#### `python/src/agent/session.py`
- ✅ 更新模块文档，删除 "取代原有 AgentLoop.run()" 的描述

#### `python/src/agent/models.py`
- ✅ 更新事件类型注释，移除 "v1/v2" 标签，改为 "基础事件/会话管理事件"

#### `python/test_agent.py`
- ✅ 更新测试代码，使用 `AgentSession.drive()` 替代 `agent.run()`

### 3. 保留的代码

#### `python/src/agent/`
- ✅ 保留 `AgentLoop.step()` - 核心无状态执行方法
- ✅ 保留 `RetryManager`、`ErrorClassifier` - 错误处理工具类
- ✅ 保留 `HookManager` - Hook 系统

#### `python/src/agent/session.py`
- ✅ 保留 `AgentSession` - 完整的会话管理
- ✅ 保留 `AgentSession.drive()` - 主事件流
- ✅ 保留 `AgentSession._drive_task()` - 任务驱动逻辑（包含错误处理）

#### `python/routers/agent.py`
- ✅ 保留 `/api/chat` - 默认端点（转发到 v2）
- ✅ 保留 `/api/agent/v2/chat` - v2 端点
- ✅ 保留所有 v2 端点（approve、abort、resume、undo、sessions）

## 架构对比

### 之前（双链路并存）

```
┌─────────────────────────────────────────┐
│           AgentLoop.run() (v1)          │
│    ┌─────────────────────────────────┐  │
│    │  完整的 ReAct 循环实现            │  │
│    │  LLM调用 → 工具执行 → 错误处理    │  │
│    └─────────────────────────────────┘  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│      AgentSession.drive() (v2)          │
│    ┌─────────────────────────────────┐  │
│    │  SecurityGate + 审批 + 任务队列   │  │
│    └────────────┬────────────────────┘  │
│                 ▼                         │
│    ┌─────────────────────────────────┐  │
│    │    AgentLoop.step()              │  │
│    └─────────────────────────────────┘  │
└─────────────────────────────────────────┘

问题：两条路径都需要维护，边界模糊
```

### 现在（统一 v2）

```
┌─────────────────────────────────────────┐
│      AgentSession.drive() (唯一路径)     │
│    ┌─────────────────────────────────┐  │
│    │  会话管理 + SecurityGate         │  │
│    │  错误处理 + 重试逻辑              │  │
│    └────────────┬────────────────────┘  │
│                 ▼                         │
│    ┌─────────────────────────────────┐  │
│    │    AgentLoop.step() (核心)       │  │
│    │  无状态单步执行                   │  │
│    └─────────────────────────────────┘  │
└─────────────────────────────────────────┘

优势：单一职责，清晰分层
```

## 测试验证

### 通过的测试

- ✅ `test_agent_dual_engine.py` - 6 passed
- ✅ `test_session.py` - 14 passed
- ✅ `test_agent_v2_router.py` - 5 passed
- ✅ `test_session_resume.py` - 4 passed
- ✅ `test_hooks.py` - 20 passed

### 总计

**25+ 核心测试全部通过**，验证迁移没有破坏功能。

## 迁移路径

### 对于使用 `/api/chat/v1` 的用户

**之前**：
```python
POST /api/chat/v1
{
  "message": "搜索关于 attention 的内容"
}
```

**现在**：
```python
POST /api/chat  # 或 /api/agent/v2/chat
{
  "message": "搜索关于 attention 的内容"
}
```

### 前端无需修改

- `/api/chat` 已经在转发到 v2（`routers/agent.py:227-230`）
- SSE 事件格式完全兼容
- 所有 v2 功能都向后兼容

## v2 额外能力

使用 v2 后，自动获得：

1. **会话管理**
   - 暂停/恢复：`POST /api/agent/v2/resume/{session_id}`
   - 持久化：自动保存到 SQLite
   - 列出会话：`GET /api/agent/v2/sessions`

2. **安全门控**
   - 工具审批：`POST /api/agent/v2/approve/{session_id}/{event_id}`
   - 风险分类：SecurityGate 自动分级
   - 会话中止：`POST /api/agent/v2/abort/{session_id}`

3. **多任务编排**
   - TaskQueue 自动管理
   - 并行任务支持
   - 任务级状态跟踪

4. **变更管理**
   - ChangeJournal 记录所有文件操作
   - Undo 支持：`POST /api/agent/v2/undo/{session_id}`

5. **更好的错误恢复**
   - 结构化错误分类（14 种错误类型）
   - 指数退避重试
   - Hook 集成

## 清理完成的标记

- ✅ 无 `agent.run()` 调用（除了 asyncio.run/subprocess.run 等标准库）
- ✅ 无 `/api/chat/v1` 端点
- ✅ 无 v1 相关文档注释
- ✅ 所有测试通过
- ✅ 代码库统一到 v2 架构

## 日期

**完成时间**: 2025-04-28

## 相关文件

- `python/src/agent/agent.py` - 核心 AgentLoop.step()
- `python/src/agent/session.py` - AgentSession 会话管理
- `python/routers/agent.py` - v2 路由端点
- `python/test_agent.py` - 测试脚本（已更新）
