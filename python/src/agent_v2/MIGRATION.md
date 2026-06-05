# 旧 Agent 架构清理计划

## 依赖全景

```
api_factory.py ──注册──▶ routers/agent.py ──导入18+模块──▶ src/agent/ (50+文件)
     │                        │
     │                        ├── 14 个端点 (v2/chat, v2/approve, v2/sessions, ...)
     │                        ├── SessionPool, WorkflowStore, TrajectoryRecorder
     │                        └── ReviewAgent, RAGStore, MemoryManager
     │
     ├── src/features.py ──▶ agent feature flag
     ├── src/plugin/builtin.py ──▶ special_elements (7个函数)
     ├── scripts/run_mcp_server.* ──▶ mcp_server.py
     │
     └── tests/ (40+ 文件 import src.agent)
```

## 迁移策略：Feature Flag 双跑

**不直接删**，而是用环境变量 `SCHOLAR_AGENT_V2=1` 切换新旧，便于渐进迁移和回退。

### Phase A: Feature Flag（0.5 天）

1. 在 `api_factory.py` 中根据 `SCHOLAR_AGENT_V2` 切换注册：
   - `V2=1` → 注册 `register_agent_v2_routes(app)` （V2 Runtime，Mock 占位）
   - 否则 → 注册 `register_agent(app, ...)` （旧代码，不变）

2. `src/features.py` 添加 `agent_v2: bool = _probe("agent_v2", "src.agent_v2")`

3. 验证：`SCHOLAR_AGENT_V2=1` 时不破坏翻译/编辑器/论证/脑图功能

### Phase B: 替换 Provider（0.5 天）

4. 把 V2 `router.py` 中的 `MockProvider` 替换为真实 LLM Provider
5. 复用现有 `PROVIDER_PRESETS` 和多 provider 支持

### Phase C: 迁移子功能（1-2 天）

6. **special_elements**: 从 `src/agent/special_elements.py` 复制到 `src/agent_v2/special_elements.py`，不依赖旧 agent
7. **plugin/builtin.py**: 改为 `from src.agent_v2.special_elements import ...`
8. **scripts/run_mcp_server.***: 指向新的 MCP server

### Phase D: 删除旧代码（0.5 天）

9. 删除 `python/src/agent/` 整个目录（先 git archive 备份）
10. 删除旧的 agent tests（40+ 文件）
11. 删除 `scripts/run_mcp_server.*` 旧版

### Phase E: 默认 V2（0.5 天）

12. 移除 feature flag，V2 成为唯一 agent
13. 清理 `api_factory.py` 中的旧配置读取和旧路由注册

---

## 不做的事

- **不迁移 RAG/Memory/Skill/ReviewAgent**：这些是旧 agent 的子功能，V2 架构用 MCP server 替代
- **不保留兼容层**：旧 agent 代码直接删，前端 SSE 格式已通过 `sse_adapter.py` 兼容
- **不迁移旧的 agent tests**：旧 tests 依赖 mock AgentLoop，新 tests 用 MockProvider，完全不同

## 时间估算

| Phase | 内容 | 时间 |
|-------|------|------|
| A | Feature flag + 双跑 | 0.5 天 |
| B | 替换真实 Provider | 0.5 天 |
| C | 迁移子功能 | 1-2 天 |
| D | 删除旧代码 | 0.5 天 |
| E | 默认 V2 | 0.5 天 |
| **总计** | | **3-4 天** |
