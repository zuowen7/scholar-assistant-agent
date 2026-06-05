# V2 vs Claw-Code 差距分析

## 致命问题（会导致"PPT 演示"级别）

### 1. 无真流式 — 最致命
- **claw-code**: `stream_message()` → SSE 逐帧推送 `ContentBlockDelta`，用户实时看到 token
- **V2 现状**: 先等完整 response，再 yield 事件。token 事件是批发的，不是真正的流式
- **后果**: 用户等 10-30 秒看不到任何输出，以为卡死了

### 2. dispatch_tool 差距
- **claw-code**: `join_under_root` 规范化路径 + `assert_workspace_path` 安全检查 + 文件大小限制 + NUL 检测 + ignore-aware 目录遍历
- **V2 现状**: 简单的 path resolve + relative_to，没有 workspace 规范化，没有 ignore 支持
- **后果**: 路径穿越可能绕过、读超大文件 OOM

### 3. 无 PermissionEnforcer 层
- **claw-code**: PermissionPolicy(规则) + PermissionEnforcer(执行门控，含 check_file_write/check_bash)
- **V2 现状**: PermissionPolicy 一把抓，没有 ReadOnly 下允许只读 bash 的功能
- **后果**: ReadOnly 模式连 `cat` `ls` `git log` 都不能用

### 4. 无 per-turn 会话自动保存
- **claw-code**: 每轮结束时 `persist_conversation_sessions`
- **V2 现状**: Session 只在 message 追加时更新内存，不自动写盘
- **后果**: 进程崩溃丢失全部对话历史

### 5. 无系统提示词构建
- **claw-code**: `system_prompt(mode, workspace, preset, profile, lang, rag)` 动态构建
- **V2 现状**: 一个可选 `system_prompt` 字符串参数
- **后果**: 没告诉 LLM 权限模式、工作区路径、可用工具等关键上下文

## 次要问题

### 6. 无上下文压缩
- claw-code: `compact.rs` — token 超 100K 时压缩旧消息
- V2: 无

### 7. 无错误恢复
- claw-code: `recovery_recipes.rs` — 自动恢复策略
- V2: 只 yield error 事件

### 8. 无 Markdown 渲染
- claw-code: ANSI markdown 终端渲染
- V2: 纯文本

## 立即修复（1-2天）

### Fix 1: 真流式 Provider
- `OpenAiCompatProvider.chat()` → `chat_stream()` 返回 AsyncGenerator
- 每个 token → 立即 yield TextBlock
- ConversationRuntime 实时转发

### Fix 2: dispatch_tool 重构
- 添加 `join_under_root` 路径规范化
- 添加 `assert_workspace_path` 安全检查
- 添加文件大小限制 + NUL 检测
- ReadOnly 模式允许只读 bash 命令

### Fix 3: PermissionEnforcer 层
- 从 PermissionPolicy 拆出 PermissionEnforcer
- 添加 `check_file_write`
- 添加 `check_bash` (is_read_only_command 启发式)

### Fix 4: Per-turn 自动保存
- ConversationRuntime.turn() 结束后自动 save session

### Fix 5: 系统提示词
- 根据权限模式、工作区、工具列表动态构建 system prompt
