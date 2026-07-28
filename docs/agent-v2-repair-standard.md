# Agent V2 修复标准与验收清单

> 状态：生产安全配置的代码修复与自动化验收完成；桌面端人工验收待执行
> 基线：`main@b390ac9`
> 适用范围：`python/src/agent_v2`、Agent V2 前端 SSE/审批/执行摘要，以及直接相关测试
> 最后更新：2026-07-28

本文档是 Agent V2 安全与可靠性修复的单一事实源。代码存在、单元测试通过或
界面看似正常，都不能单独证明条目完成；只有满足条目中的全部不变量、负空间测试
和验收证据后，状态才能改为 `VERIFIED`。

## 1. 状态和完成规则

状态只允许使用：

- `TODO`：尚未开始。
- `IN_PROGRESS`：已有实现或测试，但验收证据不完整。
- `BLOCKED`：存在明确外部阻断，并记录阻断条件。
- `VERIFIED`：实现、协议、负空间测试和回归门槛全部通过。

每个条目必须同时满足：

1. 失败测试先证明旧行为确实违反不变量。
2. 修复覆盖生产调用链，而不是只修改未接入模块。
3. 后端事件、持久化数据和前端展示保持同一语义。
4. 对安全边界使用技术强制，不依赖提示词或模型自律。
5. 在本表记录测试命令和结果；缺少证据不得标记完成。

## 2. 发布判定

以下任一条未达到 `VERIFIED`，Agent V2 的**生产安全配置**均不得宣称满足
“privacy-first”或“workspace-scoped”。生产安全配置的前提是
`agent.enable_run_command=false` 且插件默认禁用；显式打开任意进程能力后，
必须另行提供 OS 级隔离，不能继承此发布结论：

- `SEC-01` 命令执行边界
- `SEC-02` 统一工具权限和插件审批
- `SEC-03` 网络访问与 SSRF 防护
- `RUN-01` 预算耗尽和持久终态
- `IO-02` 变更账本、原子写和 Undo

## 3. 修复清单

| ID | 优先级 | 条目 | 状态 |
|---|---|---|---|
| SEC-01 | P0 | 服务端权威 workspace 与命令执行边界 | VERIFIED |
| SEC-02 | P0 | 统一 capability policy、审批与 hooks | VERIFIED |
| SEC-03 | P0 | 网络默认受控与 SSRF 防护 | VERIFIED |
| RUN-01 | P0 | 预算状态机、强制收尾与持久 outcome | VERIFIED |
| IO-02 | P0 | 原子写、turn mutation journal 与安全 Undo | VERIFIED |
| RUN-02 | P1 | 结构化工具结果状态 | VERIFIED |
| IO-01 | P1 | 长工具结果截断语义 | VERIFIED |
| STR-01 | P1 | 流式 ToolUse 与最终 blocks 无损合并 | VERIFIED |
| ARCH-01 | P1 | 生产链路能力真实性与子代理核算 | VERIFIED |
| DOC-01 | P1 | 学术文档资源预检 | VERIFIED |
| UX-01 | P2 | skill 生命周期、统计值和用户可见语义 | VERIFIED |

### SEC-01：服务端权威 workspace 与命令执行边界

不变量：

- 客户端不能把任意目录声明为可信 workspace。
- `run_command` 及其所有子进程在技术上不能读写授权 workspace 外文件。
- 一次批准不能授权语义不同的后续命令。

实现要求：

- workspace 必须来自已打开项目或服务端签发的可信 grant。
- 命令权限按规范化命令、cwd、路径和网络能力授权，不能只按工具名缓存。
- Windows `..\`、绝对路径、重定向、PowerShell、`cmd /c`、脚本解释器和
  子进程均纳入边界。
- 无法可靠解析或隔离的命令必须拒绝或逐次审批；警告不得自动继续执行。

必测：

- `..\`、绝对盘符、UNC、重定向和脚本间接访问 workspace 外路径。
- 先批准安全命令，再提交不同命令，必须再次审批。
- workspace 外 `cwd` 和命令参数访问均失败。

### SEC-02：统一 capability policy、审批与 hooks

不变量：

- 内置、学术、插件、MCP 和子代理工具必须经过同一个执行中介。
- 工具名称不能决定是否审批；工具声明的实际 effect 才能决定。
- `PreToolUse` 的 deny/ask 在生产 Runtime 中真实生效。

实现要求：

- `ToolSpec` 至少声明 `effects`、`approval_scope`、`network_scope` 和
  `rollback_capability`。
- 移除 Runtime 中四个工具名的硬编码审批。
- 插件默认不启用；插件进程受 workspace/网络边界约束，超时必须终止进程树。
- hooks 必须在授权前执行，deny 优先于 ask，ask 优先于 allow。

必测：

- 任意名称的 `workspace-write`/`process` 插件工具都会审批。
- hook deny 阻止工具执行；hook ask 触发审批。
- 插件超时后不存在遗留进程。

### SEC-03：网络默认受控与 SSRF 防护

不变量：

- “read-only”不等于“允许联网”。
- 模型不能通过 URL、DNS 或重定向访问 localhost、私网、link-local 或云 metadata。
- 网络目标必须由显式域名策略或用户逐次批准。

实现要求：

- 网络 effect 独立于文件权限。
- 解析并验证每一跳的 scheme、hostname、解析后 IP 和 redirect 目标。
- 拒绝非全局可路由 IP、URL 凭据、异常端口策略和 DNS rebinding。
- `web_search`、`web_fetch`、翻译 API 与子代理成本分别核算。

必测：

- `127.0.0.1`、`::1`、RFC1918、`169.254.169.254`、IPv4-mapped IPv6。
- 公网 URL 重定向到私网。
- 域名初次解析公网、后续解析私网。

### RUN-01：预算状态机、强制收尾与持久 outcome

不变量：

- 预算耗尽不是“失控循环”。
- 已发生写入后，所有退出路径都必须产生可恢复的持久终态。
- 模型无法总结时，Runtime 仍能确定性说明已执行、失败和未执行内容。

实现要求：

```text
RUNNING -> DRAINING -> FINALIZING -> COMPLETE | PARTIAL | FAILED | ABORTED
```

- 软阈值后停止启动新写入，保留验证与 finalization 预算。
- 硬阈值后补齐同批 ToolResult，再执行一次 `tools=[]` 收尾。
- 持久化 outcome、stop reason、changed files、未执行验证和计数。
- `max_steps`、tool call、model call、mutation、error 和 active wall time 分开计量。
- token/cost 单独观测；由于部分 provider 不返回可信 usage 且价格表会漂移，
  不能把估算成本伪装成强安全边界，硬停止由 model call 与 active time 保证。

必测：

- 第 33 个调用位于三调用批次时得到 `PARTIAL`，其余两个为 `skipped`。
- 已有写入后达到 `max_steps`，仍产生持久 partial summary。
- finalizer 失败时由 Runtime 生成确定性 summary。
- 继续执行只处理未完成验证，不重复已完成写入。

### IO-02：原子写、turn mutation journal 与安全 Undo

不变量：

- 单个写入不能因进程中断留下半文件。
- 每个 turn 的写入可以在 Runtime 退出和服务重启后撤销。
- Undo 不能覆盖用户在 Agent 之后产生的新修改。

实现要求：

- 使用同目录临时文件、flush/fsync 和原子 replace。
- 持久记录 `turn_id`、tool-use id、path、before/after hash、反向内容或补丁。
- Undo 前验证当前 hash 等于 journal 的 after hash。
- Undo 本身也原子执行并记录 outcome。

必测：

- 写入中途故障后原文件完整。
- 多文件 turn 可整组撤销。
- 重启后仍可撤销。
- 文件被外部修改后 Undo 拒绝盲目覆盖。

### RUN-02：结构化工具结果状态

不变量：

- `failed`、`denied`、`skipped`、`no_change` 不能压缩成同一个布尔值。
- no-op 不算成功修改、不发 mutation checkpoint，但仍计工具尝试。

协议：

```text
pending | awaiting_approval | success | error | denied | skipped | no_change
```

必测：

- 后端 JSONL、SSE、前端执行摘要和统计使用相同状态。
- `old_string == new_string` 和 before/after hash 相同均返回 `no_change`。
- skipped 以中性状态显示，不增加失败计数。

### IO-01：长工具结果截断语义

不变量：

- 每次截断必须保留机器可读元数据和用户/模型可见标记。
- Runtime、Session 和 SSE 不得再次静默截断掉标记。

实现要求：

- `ToolResult` 携带 `truncated`、`original_chars` 和 `returned_chars`。
- 文件读取支持显式 offset/limit 或行范围，便于继续读取。

必测：

- 超长文件经过 registry、Session、provider history 和 SSE 后仍明确标记截断。
- 分页读取可以无重叠、无遗漏地覆盖整个文件。

### STR-01：流式 ToolUse 无损合并

不变量：

- 流式块和最终响应中相同 ID 只执行一次。
- 最终响应新增的 ToolUse 不得丢失。
- ToolUse/ToolResult 始终一一配对。

必测：

- 先流出 `t1`，最终 blocks 包含 `t1,t2`，最终执行顺序为 `t1,t2`。
- 重复 ID 不二次执行；冲突 ID/内容明确报协议错误。

### ARCH-01：生产链路能力真实性与子代理核算

不变量：

- 未接入生产调用链的模块不得在成熟度文档中宣称为已交付。
- 子代理必须有独立 run/session、预算、usage、取消和父子关系。

必测：

- compaction/recovery/session control 的生产入口集成测试。
- 子代理 usage、超时、取消、错误和 trace 汇总到父 run。

### DOC-01：学术文档资源预检

不变量：

- 工具字符串替换成功不等于文档交付成功。
- 缺失图片、BibTeX key 或导出依赖必须影响最终 outcome。

必测：

- 缺失 `\includegraphics`、引用 key 和模板资源时预检失败。
- 只有用户明确允许时才能用占位内容降级。

### UX-01：skill 生命周期、统计值和用户可见语义

要求：

- skill 默认单轮生效；跨轮使用必须显式 pin。
- 预算耗尽、重复调用和累计工具错误使用不同文案。
- `/api/agent/stats` 与实际 Runtime 使用同一配置源。

## 4. 已实施修复与未闭合边界

| ID | 已实施并通过自动化验证 | 未闭合边界 |
|---|---|---|
| SEC-01 | 项目打开时签发服务端 grant；chat、审批、恢复、会话读取/删除、成本与 Undo 都校验同一根目录；生产配置不注册 `run_command`；显式启用后仍使用 `create_subprocess_exec`、拒绝 shell 元字符/路径逃逸/UNC/解释器并按规范化输入审批 | `VERIFIED` 仅适用于生产安全配置。显式启用通用命令后，受信可执行文件仍可能在进程内部访问 workspace 外资源；该能力必须配 OS 级隔离并重新验收 |
| SEC-02 | `ToolSpec` 以 effect、审批范围、网络范围和回滚能力描述工具；Runtime 的 Pre/Post hooks、deny/ask、插件默认禁用、插件超时进程树终止均已接入生产链路 | MCP manager 当前未接入生产 registry，因此不作为已交付能力；接入时必须复用同一中介 |
| SEC-03 | URL scheme、凭据、端口、每跳重定向和全部 DNS 结果均拒绝非公网地址；实际请求固定到已验证 IP，同时保留原始 Host/SNI；禁用环境代理；响应上限 2 MiB；network effect 与文件权限分离 | 当前允许的学术域名由代码白名单维护，新增域名必须带同级负空间测试 |
| RUN-01 | 实现软/硬 tool call 阈值、独立 model call/mutation/active-time 上限、`DRAINING`/`FINALIZING`、确定性本地收尾、持久 outcome、重复写入幂等和中断状态归一；审批等待不消耗 active time | token 与 monetary cost 是 provider 上报后的观测值，不作为可信硬边界；若将来提供付费额度承诺，必须接入 provider 账单或可信计量源 |
| IO-02 | `write_file`、`str_replace` 和导出使用同目录临时文件、fsync、原子 replace；JSONL 记录文本/二进制 before/after hash；Undo 支持整 turn、跨重启并拒绝覆盖后续用户修改 | `VERIFIED` 仅适用于不注册进程/插件写能力的生产安全配置；未来进程产生的文件修改必须接入文件系统隔离或完整 journal |
| RUN-02 | `success/error/denied/skipped/no_change` 已贯通 registry、Session、SSE 和前端执行摘要；no-op 不产生 checkpoint | 无 |
| IO-01 | `ToolResult` 保留截断元数据和可见标记；`read_file` 支持 offset/limit 连续分页 | 单文件 8 MiB 以上明确拒绝，而不是自动流式读取；这是显式产品上限，不是静默截断 |
| STR-01 | 流式与最终 ToolUse 按 ID 并集合并；重复只执行一次，冲突成为协议错误，最终新增块不丢失 | 无 |
| ARCH-01 | 子代理明确定位为 one-shot specialist，拥有独立 Session、父子关系、预算、usage、超时/错误/取消终态；父级取消会取消并持久化子会话；usage 汇总到父 run；compaction/recovery/session control 均有生产入口测试 | 它不是递归的完整 ConversationRuntime，产品文案和 tool description 不得宣称多步自治；MCP manager 未接入生产 registry，不计入已交付能力 |
| DOC-01 | 导出前检查 Markdown/LaTeX 图片、BibTeX 文件/引用 key 和 YAML 模板引用；所有本地资源必须位于 workspace；只有显式 `allow_missing_resources` 才降级 | 无 |
| UX-01 | skill 仅由当前请求激活、不隐式跨轮；预算/重复/错误文案分离；stats 与 Runtime 读取同一预算配置 | 当前不提供跨轮 pin；因此不存在隐式持久化，但后续若增加 pin 必须显式授权和可见 |

由上表可得：生产安全配置已满足代码级发布条件；它通过“不注册任意进程/插件
能力”闭合 workspace 与 Undo 边界，并通过固定解析地址闭合 DNS-rebinding 窗口。
这不等于拥有 OS/container sandbox。任何显式启用 `run_command`、插件或未来 MCP
进程的配置都属于 power profile，不能宣称已通过本验收。

## 5. 与主流编码 Agent 的边界比较

| 系统 | 默认信任与执行隔离 | 本项目的相对结论 |
|---|---|---|
| Claude Code | 项目读写权限模式、逐次审批和 turn 上限；安全文档仍要求外部 sandbox 承担 OS 隔离 | 本项目在工作区 grant、文件 mutation journal、跨重启 Undo 和学术资源预检上更具体；同样不能把静态命令校验冒充 OS sandbox |
| Gemini CLI | trusted folders、allow/exclude tools、审批模式，并可使用 Seatbelt 或 Docker sandbox | 本项目生产安全配置通过直接移除命令能力达到更小攻击面；若启用命令，隔离能力弱于 Gemini 的 sandbox 模式 |
| OpenHands | 推荐 Docker runtime；process runtime 明确没有隔离 | 本项目默认桌面内嵌运行，文件协议和恢复能力更强，但不提供容器级任意命令隔离 |
| 本项目 | 服务端 workspace grant、effect policy、审批、可恢复 journal、独立预算、固定 IP/SNI 网络预检；默认无命令和插件进程 | 适合 privacy-first 学术文件工作；不应包装为通用 autonomous coding sandbox，子代理也是 one-shot specialist |

## 6. 验收证据

| 日期 | 条目 | 证据 | 结果 |
|---|---|---|---|
| 2026-07-28 | 基线 | `python -m pytest tests/agent_v2/ -q`（审查时） | 662 passed，但未覆盖本清单负空间 |
| 2026-07-28 | 前端基线 | `npm test -- --run src/__tests__/agentExecution.test.ts src/__tests__/useAgentChat.test.ts` | 33 passed，但未覆盖结构化状态 |
| 2026-07-28 | 会话/终态聚焦 | `python -m pytest tests/agent_v2/test_session.py tests/agent_v2/test_conversation_runtime.py -q` | 67 passed |
| 2026-07-28 | Agent V2 全量 | `python -m pytest tests/agent_v2/ -q` | 715 passed |
| 2026-07-28 | 工作区授权旁路复核 | `python -m pytest tests/agent_v2/test_router_prompt.py -q` | 11 passed |
| 2026-07-28 | 前端授权链聚焦 | `npx vitest run src/__tests__/useAgentChat.test.ts src/__tests__/useProject.test.ts` | 44 passed |
| 2026-07-28 | 前端全量 | `npx vitest run` | 73 files，821 passed |
| 2026-07-28 | Python 3.12 隔离安装 | `pip install -r requirements-lock.txt -r requirements-dev.txt && pip check` | 安装成功，无依赖冲突 |
| 2026-07-28 | Python 全量（隔离环境） | `python -m pytest tests/ -q` | 2235 passed，7 skipped，0 failed |
| 2026-07-28 | Python 静态与格式 | `ruff check . && ruff format --check .` | 0 issue，223 files formatted |
| 2026-07-28 | 前端静态门禁 | `npm run typecheck && npm run typecheck:test && npm run lint && npm run format:check` | 全部通过；lint 0 error、167 existing warnings |
| 2026-07-28 | 生产构建 | `npm run build` | 成功，3561 modules transformed |
| 2026-07-28 | 桌面端编译 | `cargo check --manifest-path src-tauri/Cargo.toml` | 成功 |
| 2026-07-28 | 内嵌后端打包冒烟 | 启动 `src-tauri/python-dist/api/api.exe --port 18089` 并请求 `/api/health` | `status=ok`，`version=0.5.0`；同时修复 Anaconda venv 未收集 OpenSSL/SQLite DLL 的发布缺陷 |
| 2026-07-28 | Tauri/NSIS 发布构建 | `npx tauri build` | 成功；最终安装包 436170651 bytes，SHA-256 `CAEB243B36070C392B5E6ED60D3FA98861F47950C466F6C5EB2DEDB585315AA7` |
| 2026-07-28 | JavaScript 依赖审计 | `npm audit` | 0 known vulnerabilities |
| 2026-07-28 | Python 依赖审计 | `pip-audit -r requirements-lock.txt` | 仅 `PYSEC-2026-311`；当前仅用本地嵌入式 `PersistentClient`，未运行受影响的多租户 Chroma server；记录为范围不适用例外 |
| 2026-07-28 | Python 依赖审计（已登记例外） | `pip-audit ... --ignore-vuln PYSEC-2026-311` | 0 known vulnerabilities，1 ignored |
| 2026-07-28 | 差异卫生 | `git diff --check` | 通过；仅有既有行尾转换警告 |

## 7. 最终发布门槛

完成全部 P0/P1 条目后，至少执行：

```bash
cd python
pytest tests/agent_v2/ -q
pytest tests/ -v

cd ..
npx vitest
npm run build
```

还必须在桌面端手工验证：

1. 长文多文件修改在软预算后进入收尾，并显示 `PARTIAL` 或 `COMPLETE`。
2. “本次会话允许”不会放行不同命令或不同路径能力。
3. 部分完成卡片可查看修改、继续验证和跨重启安全撤销。
4. 长文件读取明确显示截断并可继续读取。
5. 缺失学术资源时导出被预检阻止，而不是产生假完成。
