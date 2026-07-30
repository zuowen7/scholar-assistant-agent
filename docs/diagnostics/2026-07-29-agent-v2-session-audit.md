# Agent V2 实测会话问题定位与修复决策

> 结论：本次测试的主要风险不是后端不可用，而是 Agent V2 实际使用的提示词链与“全局学术提示词”彼此分离，且缺少代码级证据门禁；这使 Agent 能在证据不完整时改写学术事实，并在异常停止、审批、Windows 执行、状态联动和长会话恢复中继续放大错误。

## 1. 审计范围

- 代码基线：分支 `agent/agent-v2-hardening`，HEAD `35867e14f8b6`。
- 后端日志：`python/logs/app.log`。
- 实测会话：`python/data/agent_v2/sessions/sess_0d787c9182e945c4866b83d138197811.jsonl`。
- 测试窗口：2026-07-29 23:36:45.356 至 23:49:23.293（约 12.63 分钟）。
- 用户工作区：`%USERPROFILE%\Desktop\论文\yolo历史`（文档中不保留本机用户名）。
- 本文原始审计阶段只做问题定位和修复决策；2026-07-30 的复核与实现状态见第 11 节。

判断口径：

- **事实**：可由日志、session 或当前代码直接确认。
- **推断**：由事实和代码路径推导，但尚未通过修复后复现实验验证。
- **未验证内容**：Agent 写入了稿件，但本次 session 中没有对应原始数据或外部来源证据；未验证不等于已经证明为假。

## 2. 会话事实摘要

| 指标 | 实测值 |
|---|---:|
| 用户轮次 | 6 |
| Assistant 消息 | 90 |
| 工具调用 / 工具结果 | 92 / 92 |
| 成功 / 错误工具结果 | 77 / 15 |
| 文件变更记录 | 35 |
| 被修改文件 | 6 |
| 审批次数 | 39（`allow_once` 22，`allow_session` 17） |
| session 文件大小 | 1,219,379 bytes |
| session 累计 token | 0 / 0 |
| 日志窗口内 `tool_failure` WARNING | 6 |

各轮行为：

| 轮次 | 用户任务 | 工具调用 | 错误 | 结果 |
|---:|---|---:|---:|---|
| 1 | 结合论证图、Claim Ledger、Reviewer 审稿 | 5 | 0 | 输出审稿报告，但把截断数据称为“完整” |
| 2 | 逐项修改 | 32 | 1 | 修改稿件，加入多项新数字和结论 |
| 3 | 制作投稿级图表 | 32 | 12 | 重复调用触发停止，最终显示原始 DSML 工具协议文本 |
| 4 | 继续未完成任务 | 23 | 2 | 生成 3 个 PDF，但没有视觉渲染检查 |
| 5 | 梳理结构 | 0 | 0 | 直接输出结构审查 |
| 6 | 再次投稿前审查 | 0 | 0 | 输出审查，但没有核验新增引用建议或数据来源 |

session 中 35 个 mutation 包括：

- `main.md`：22 次；
- `make_pca.py`：8 次；
- `make_prisma.py`：2 次；
- `check_deps.py`、`check_deps2.py`、`make_pareto.py`：各 1 次。

## 3. 已确认问题

### P0 — 学术证据约束失效

#### A1. Agent 在没有来源证据时写入新的定量事实

**事实**

1. Agent 将 PRISMA 初检索总数 1,287 拆成：
   `arXiv 412 + IEEE Xplore 203 + Google Scholar 378 + Web of Science 167 + DBLP 127`。
2. session 中没有数据库导出、筛查登记表、检索文件、网络检索或其他可支持该分项的数据源；这些数字只满足求和为 1,287。
3. Agent 先写入 PCA 结果 `78.3%（52.1% + 26.2%）`、簇内距离 `0.32–0.51`、簇间距离 `1.84–2.67`，当时尚未运行 PCA。
4. 后续脚本实际输出为 `59.1%（40.4% + 18.7%）`、簇内 `0.00–3.74`、簇间 `2.26–6.15`，证明首次写入的 PCA 数值不是实测结果。
5. Agent 还写入了表 5 的多项消融增益，但 session 中没有逐项读取原论文或检索来源。

**影响**

- 系统当前允许“先写结论、后找证据”，直接破坏论文可信度。
- 用户审批只能看到文本差异，无法判断新增数字是否有来源。
- 后续 Reviewer 再审没有识别 PRISMA 分项数字的来源缺失，说明该错误会被系统自身继续放大。

**修复决策**

1. 为 `nature_figure`、`nature_citation`、投稿审查和论文改写增加统一的 **evidence gate**。
2. 新增数字、比例、样本量、统计量、引用或“经核查”等事实性措辞时，变更必须携带 `evidence_refs`：
   - 工作区文件路径 + 内容 hash + 行/表锚点；
   - 已执行脚本 + 输入 hash + stdout 结果；
   - 已验证文献或网页来源。
3. 缺少证据时只允许：
   - 保留原文；
   - 降级为待核验占位符；
   - 在审批卡片中标记“新增事实无来源”，不得静默写入。
4. 数值脚本必须遵循“先执行得到结果，再修改正文”，禁止预填计算结果。
5. 对这次稿件中的数据库分项数、表 5 消融值、PCA 解释和 Pareto 结论做一次单独的来源审计；在完成前不得视为投稿可用。

#### A2. 截断的 Ledger / Reviewer 数据被宣称为“完整”

**事实**

- Claim Ledger 原始结果 13,552 字符，只返回 4,000 字符。
- Reviewer 详情原始结果 6,243 字符，只返回 4,000 字符。
- Agent 对同一个 Reviewer 详情做了两次完全相同的读取，两次都得到相同截断结果。
- 随后回复称“已获取完整的 Claim Ledger 和 Reviewer 数据”。
- `read_argument_ledger` 和 `read_reviewer_state` 当前没有分页、字段筛选或 summary/detail 模式。

**影响**

- 严重程度排序和问题计数可能只基于前半段数据。
- 重复读取不能补齐结果，却消耗模型调用和工具预算。

**修复决策**

1. 学术状态读取工具返回结构化 envelope：
   `complete`、`total_items`、`returned_items`、`next_cursor`、`source_version`。
2. 支持 `summary`、`item_ids`、`cursor`、`limit`；大对象先读摘要，再按 ID 分页读取。
3. runtime 在 `complete=false` 时注入强约束：不得使用“完整”“全部”“已全面读取”等措辞。
4. 相同参数的截断读取再次发生时，直接返回可执行的分页提示，而不是重复相同内容。

### P1 — 异常停止未形成可信的用户结果

#### R1. 重复调用停止后泄漏原始 DSML 工具协议

**事实**

- 第 3 轮连续运行 PCA 脚本失败，第三次相同调用触发 `repeated_tool_call`。
- 该轮最后一条 Assistant 文本是：
  `<｜｜DSML｜｜tool_calls> ... run_command ... </｜｜DSML｜｜tool_calls>`。
- 用户没有收到“部分完成、已改哪些文件、还缺什么”的正常收口，只能再次发送“继续完成”。
- `_finalize_stopped_turn()` 会调用一次 `force_no_tools=True` 的模型收口；当前实现只要模型返回非空文本就当作用户响应，没有拒绝工具协议标记。

**影响**

- 工具内部协议直接暴露到产品 UI。
- session 在该轮实际应为 PARTIAL，但用户无法理解停止原因和已完成范围。
- 若对协议文本做宽松解析，还可能引入意外工具执行风险。

**修复决策**

1. 将工具标记文本识别为 `malformed_tool_call`，绝不直接显示。
2. 首次出现时做一次“无工具、纯文本、禁止协议标记”的修复生成。
3. 修复生成仍含协议标记时，使用 runtime 自己生成的确定性 PARTIAL 摘要，不再相信模型收口。
4. PARTIAL 摘要必须包含 `stop_code`、成功/失败/跳过计数、变更文件和未验证项。
5. 增加 DeepSeek 文本化工具调用、重复调用停止和 DSML 泄漏回归测试。

#### R2. 图表“已检查”结论超过实际验证能力

**事实**

- Agent 实际验证了脚本退出码、依赖、文件存在和大小。
- session 中没有 PDF 渲染、页面截图、图像读取或视觉检查工具调用。
- 最终却称 PDF “可正常打开”并完成“投稿级”检查。
- `nature_figure` skill 明确要求检查渲染结果；当 Python/R 未明确时也要求先询问，但 Agent 直接选择了 Python。

**影响**

- 文件可生成不等于版式、裁切、字体、图例、颜色和标签正确。
- 当前 Pareto 脚本把已被 v10x 同时以更高 AP 和更高 FPS 支配的 v5l 仍画入前沿；这类科学/图形错误无法由“脚本退出 0”发现。

**修复决策**

1. 为 Agent V2 增加受限的 `render_pdf_page` / `inspect_figure` 只读能力。
2. `nature_figure` 流程状态机固定为：
   数据来源确认 → Python/R 明确选择 → 计算验证 → 生成 → 渲染 → 视觉/科学检查 → 才可完成。
3. 没有渲染能力时，结果必须标记“生成成功，视觉验收未完成”。
4. Pareto、聚类、置信区间等图形增加领域校验函数，而不是只检查文件存在。

### P1 — Windows 执行契约与工具说明不一致

#### W1. `run_command` 在 Windows 上产生可预防错误和乱码

**事实**

- `mkdir`、`dir` 通过了部分意图判断，但 direct-exec 最终报 `executable not found`；它们是 Windows shell builtin，不是独立 executable。
- Agent 多次尝试 `python -c`、命令链 `&&`，均被安全策略拒绝。
- Python 子进程 traceback 中中文路径变成 `����\yolo��ʷ`。
- `run_command` 对 stdout 固定使用 UTF-8 容错解码；Windows 子进程可能按 GBK/OEM 编码输出。
- 写文件本身会创建父目录，但工具说明没有明确告诉模型无需先执行 `mkdir`。

**影响**

- 15 个工具错误中相当一部分不是任务本身失败，而是平台/提示契约不一致。
- 路径乱码降低日志和错误定位价值。

**修复决策**

1. 新增安全的 `make_dir` 工具，或在 `write_file` 描述中明确“父目录自动创建”。
2. Windows direct-exec 预检应对 `dir`、`mkdir` 返回平台专用替代建议，不进入审批。
3. 对 Python 子进程设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
4. 通用输出按 UTF-8 严格解码失败后，再回退到 Windows 首选编码；日志保留 `encoding_source`。
5. tool error 返回稳定的错误码和 `suggested_next_action`，减少模型盲目重试。

### P1 — 审批与状态联动不符合“会话”语义

#### U1. `allow_session` 只在单次 runtime 内有效

**事实**

- 用户选择 `allow_session` 17 次。
- 每个 `/chat` 请求都会重建 `ConversationRuntime`。
- `_session_approved_actions` 只存在于 runtime 内存，未随 workflow/session 恢复。
- 因此上一轮已允许的相同脚本，在“继续完成”下一轮仍需再次审批。
- 同一会话总计出现 39 次审批；22 次是用户明确选择 `allow_once`，不能自动消除。

**影响**

- “本次会话允许”的用户语义与实现的“本次流式请求允许”不一致。
- 长任务被频繁打断，用户容易机械批准而降低安全性。

**修复决策**

1. 将授权绑定到 `workflow_id + workspace_grant + tool + normalized_scope`。
2. 仅按原有范围持久化：
   - 文件工具：精确文件路径；
   - 命令工具：精确 argv + cwd；
   - 不允许从单文件或单命令自动扩大到整个工作区。
3. 工作区 grant 失效、用户新建会话、显式撤销或策略版本变化时清空授权。
4. UI 明确展示授权范围，不使用含糊的“本次会话全部允许”。
5. 为同一文件的多项修改增加带文件 hash 的原子 `multi_replace`，一次展示全部 hunks、一次审批、一次提交；避免 22 次零散替换。

#### U2. 稿件变更后 Claim Ledger / Reviewer 状态保持陈旧

**事实**

- 学术工具只提供 `read_argument_ledger` / `read_reviewer_state`。
- Agent 修改 `main.md` 后明确表示“无法直接修改 ledger（只读）”。
- 旧 ledger/reviewer 仍可能被后续任务当成当前真实状态。

**修复决策**

1. 文件 checkpoint 后按文档 hash 标记关联 ledger/reviewer 为 `stale`。
2. 增加显式审批的 `rebuild_argument_ledger` / `refresh_reviewer_state`，复用现有 `routers/argument.py`，不新建平行实现。
3. 读取工具必须返回 `source_doc_hash` 和 `stale`；状态陈旧时不得称为“当前真实数据”。

### P2 — 可观测性和 session 持久化不足

#### O1. 日志、用量和 session 摘要不能还原真实执行

**事实**

- session 有 15 个错误工具结果，日志窗口只有 6 条 `tool_failure` WARNING；预检失败没有统一的完成日志。
- 工具日志缺少稳定的 `session_id`、`turn_id`、`tool_use_id` 组合，主要依赖请求 correlation ID。
- session `total_usage` 为 0/0；DeepSeek streaming quirk 当前关闭 `stream_options.include_usage`，最终 `ProviderResponse` 又固定携带零 usage。
- `outcome` 每轮覆盖，只表示最后一轮；最后两轮没有工具，因此最终元数据看起来是“0 工具、0 变更”，但整个 session 实际有 92 次工具调用和 35 次变更。
- message 记录没有时间戳和 `turn_id`，必须依赖顺序和 app.log 猜测时间线。

**修复决策**

1. 每个 ToolResultBlock 都写一条结构化完成日志：
   `session_id`、`turn_id`、`tool_use_id`、`tool_name`、`status`、`error_code`、`duration_ms`；不记录敏感正文或密钥。
2. 将元数据拆成 `last_turn_outcome` 和 `session_aggregate`，名称与语义一致。
3. DeepSeek 先做真实 provider contract test：
   - 支持 usage streaming 时启用并测试；
   - provider 不返回 usage 时显示 `unknown`，不得伪装成 0。
4. message 持久化增加 `message_id`、`turn_id`、`created_ms`、`original_chars`、`truncated`。

#### O2. session 文件膨胀且恢复上下文会静默截断

**事实**

- 单字段持久化上限为 16 KiB，6 条用户消息在 session 中均被截断为 16,397 字符（含截断标记）。
- 每轮都把活动文稿内容复制进 user message；session 中重复保存大量稿件片段。
- 35 个 mutation 保存完整压缩 pre-image，`main.md` 被重复保存 22 次。
- `_auto_save()` 在几乎每个事件后重写完整 JSONL；本次文件已达约 1.2 MB。
- 文件头声称有 rotate，live auto-save 实际明确绕过 rotate。

**影响（推断）**

- 长会话磁盘写入呈随历史增长的放大趋势。
- resume 后历史消息只剩截断文本，模型可能在没有明确完整性信号的情况下继续。
- 隐式复制论文全文和多个 pre-image 增加隐私与保留治理压力。

**修复决策**

1. 分离用户真实 prompt 与 editor context；持久化 `file_path + content_hash + dirty_snapshot_ref`，不把整篇文稿拼进每轮聊天文本。
2. 对 unsaved Monaco 内容保存受控快照引用，仍然禁止 Agent 覆盖 dirty tab。
3. session 改为事件 journal + 周期 checkpoint/compaction，避免每个工具事件重写全部历史。
4. mutation journal 使用首个基线快照 + 后续 delta/patch，并设置可见的保留期和清理策略。
5. 截断必须是结构化状态；resume 前进行上下文压缩或重新读取当前文件，不能静默依赖截断历史。

## 4. 修复顺序

### 阶段 1：先阻断学术错误写入

范围：A1、A2。

完成条件：

- 无 evidence ref 的新增数字/引用不能静默写入；
- 截断 Ledger/Reviewer 不会被称为完整；
- 先计算、后写正文的顺序有集成测试；
- 对本次稿件新增数字产生待核验清单。

### 阶段 2：保证异常与 Windows 执行可恢复

范围：R1、R2、W1。

完成条件：

- DSML/工具协议文本永不进入最终 UI；
- circuit breaker 总能输出确定性 PARTIAL 摘要；
- Windows 中文路径输出不乱码；
- 图表没有视觉渲染时不会被标记为投稿级验收通过。

### 阶段 3：修复长任务交互契约

范围：U1、U2。

完成条件：

- `allow_session` 在同一 workflow 的后续 `/chat` 请求中按原范围生效；
- 多项同文件修改可一次预览和原子审批；
- 稿件 hash 改变后 ledger/reviewer 自动显示 stale，并可显式重建。

### 阶段 4：补齐商业软件级可观测性与存储

范围：O1、O2。

完成条件：

- 日志工具结果数与 session 工具结果数一致；
- usage 是真实值或 `unknown`；
- session aggregate、last turn、mutation 三类状态可区分；
- 长会话恢复、压缩、清理和隐私保留策略通过测试。

## 5. 必要回归测试

1. 重放本 session 的 6 个用户任务和关键 provider 响应。
2. Ledger 13,552 字符、Reviewer 6,243 字符的分页完整性测试。
3. 无来源 PRISMA 分项数字、预计算 PCA 数字的 evidence gate 测试。
4. DeepSeek 文本化 DSML + repeated tool call 的 PARTIAL 收口测试。
5. 两次 `/chat`、同一 `workflow_id` 的 `allow_session` 持久化与越权负例。
6. Windows 中文路径、GBK/UTF-8 输出、`dir`/`mkdir` builtin 预检测试。
7. PDF 生成成功但未渲染时不得通过 figure acceptance。
8. checkpoint 后 ledger/reviewer stale 与显式重建测试。
9. usage 缺失、usage 正常返回、session aggregate 覆盖测试。
10. 长 session 恢复、截断标记、dirty Monaco tab 不被刷新覆盖测试。

修复涉及协议、session、工具和前端审批，完成时应运行：

```text
cd python
pytest tests/ -v

cd ..
npx vitest
npm run build
```

## 6. 当前决策

- **现在不直接开始大范围修复。**
- 首个实现批次只做阶段 1，并在一个独立提交中完成 Agent V2 核心提示词契约、evidence gate、学术状态分页和对应测试。
- 阶段 1 验收通过后，再进入 runtime/Windows 修复；不要把四个阶段混成一次难以审查的大提交。
- 本次生成的论文与图表产物在来源复核前，只能视为“Agent 草稿”，不能视为投稿级完成品。

## 7. 提示词体系补充审计

### 7.1 审查结论

按指令质量审查口径，当前提示词体系的结论是 **REVISE**：

- 不是所有提示词都应重写；
- Agent V2、Nature 学术技能、Reviewer 和工具说明必须优先修改；
- 翻译、润色等稳定单任务提示词应做边界审计后局部修改；
- 仅改提示词不能关闭本次事故，必须与 runtime 证据门禁、完整性状态和结果验收同时实施。

本次失败对应的指令缺陷：

| 缺陷 | 当前表现 | 后果 |
|---|---|---|
| 只写禁止项，没有强制动作 | 多处写了“不得编造”，但没有规定必须先读取哪个来源、执行哪个脚本 | 模型可以先写结果，再用语言解释成“基于分析” |
| 输出形状替代真实取证 | Reviewer 只要求返回 3–6 个 JSON 问题 | 模型容易生成形式正确但没有可追溯证据的问题 |
| 把摘要当证据 | Agent 接受截断 Ledger/Reviewer 结果后声称完整 | 结论覆盖范围超过实际读取范围 |
| 缺少产物链 | 图表只检查脚本退出码和文件存在 | 没有渲染检查也能被称为投稿级完成 |
| 缺少负向验收 | 没有检查新增数字、引用、占位符、协议文本是否意外出现 | 静默造数和 DSML 泄漏不会阻断完成 |
| 边界行为未定义 | 截断、工具失败、无渲染能力时没有统一 COMPLETE/PARTIAL 规则 | 异常结果被包装成正常完成 |

### P0 — P1. “全局学术系统提示词”没有进入 Agent V2 主链路

**事实**

1. `python/prompts/system/academic_writer_system.md` 明确包含“不得编造实验结果、引用、数字、数据集、方法细节或结论”。
2. Agent V2 的实际 system prompt 由 `python/src/agent_v2/router.py::_build_system_prompt()` 单独构建。
3. `_create_runtime()` 只把该 prompt 与 `SkillRegistry` 的 active skill 拼接，没有调用 `prompts.loader.get_system_prompt()`。
4. `academic_writer_system.md` 当前只由 `python/prompts/loader.py` 读取；它不是 Agent V2 的全局约束。

**结论**

此前认为“系统已经明确禁止造假，只是模型不遵守”并不完整。更准确的结论是：

- 单任务学术写作提示词有禁止造假的规则；
- 发生本次文件改写的 Agent V2 主链路并没有继承该规则；
- 因此只优化 `academic_writer_system.md` 对 Agent V2 不生效。

**修复决策**

1. 建立一份 Agent V2 真正执行的核心契约，直接放入 `_build_system_prompt()` 的静态部分。
2. 核心契约至少包含：
   - 工作区和 dirty editor 安全；
   - 学术事实与证据边界；
   - 工具结果完整性；
   - 失败、截断和未验证状态；
   - COMPLETE / PARTIAL / BLOCKED 终态；
   - 禁止把摘要、模型自述或文件存在当作验收证据。
3. 不通过“参见另一个 prompt 文件”实现关键规则；执行时必须直接注入，避免规则停留在未读取文件中。

### P0 — P2. 默认技能会鼓励补引用，但没有验证来源的配套动作

**事实**

1. `academic_writing`、`paper_review`、`latex_formatting`、`chinese_academic`、`methodology_critique` 默认 active。
2. `python/data/agent_v2/skills/thesis_writing.md` 没有声明 `default_active: false`，加载时也会默认 active。
3. `academic_writing` 要求“引用相关文献”；`thesis_writing` 要求涉及前人工作的 claim 必须有引用。
4. 这些默认技能没有要求在写入前调用检索工具、读取来源、保存 source ID，或在无法验证时保留待核验标记。

**推断**

这组提示会给模型形成“应该补引用”的正向压力，但没有“只能补已核验引用”的执行约束，可能促使模型选择最省力的占位引用或建议性来源。它不是本次造数的唯一原因，但属于会重复触发的提示词风险。

**修复决策**

1. 默认技能只保留跨任务都成立的最小规则；论文、LaTeX、中文论文和方法审查改为按任务显式激活。
2. 所有“补引用”要求必须改为：
   `先检索/读取 → 核对元数据和 claim relevance → 记录 evidence_ref → 才允许写入`。
3. 不能核验时只能返回候选来源或待办，不得生成可直接写入的引用字段。

### P1 — P3. AI 面板 `/api/edit` 使用另一套更弱的提示词

**事实**

1. `/api/edit` 实际调用 `render_edit_with_text_prompt()` 或 `render_edit_without_text_prompt()`。
2. `edit_with_text.md` 的运行时 system prompt 只要求按指令处理文本和只输出结果，没有“不得新增数字、引用、结果或结论”。
3. `edit_without_text.md` 也只有通用学术助手身份和中文回复要求。
4. 两条路径均没有合并 `academic_writer_system.md` 的强约束。

**影响**

- 同一个“润色/扩写/审查”动作从 Agent 面板和 AI 面板进入时，安全边界不同。
- 用户可能认为“学术助手全局规则”覆盖所有入口，但当前实现不是这样。

**修复决策**

1. 为 `/api/edit` 定义一份短小的 one-shot 核心安全前缀。
2. 根据 preset 分别限制：
   - polish：只改表达；
   - expand：只用输入已有事实；
   - review：只给问题，不替用户改写事实；
   - translate：保持数值、引用、公式和确定性。
3. AI 面板继续使用 `/api/edit`，不迁移到 Agent V2；修复提示词契约，不改变产品架构。

### P1 — P4. Reviewer 的“全稿审查”缺少覆盖率和证据锚点

**事实**

1. 四个 Reviewer prompt 只要求 3–6 个 JSON 问题和 `verbatim_quote`。
2. 方法、实验、写作和反方视角分别只接收 14,000–16,000 字符的 excerpt。
3. `build_section_excerpt()` 会按章节分配预算或优先抽取指定章节，但返回值没有 `complete`、总字符数、覆盖章节或被截断位置。
4. Reviewer 输出 schema 没有 `source_section`、稳定 anchor、`evidence_status`、`coverage_status` 或 `not_assessable`。
5. prompt 把 `Paper: {text}` 放在静态审查要求之前，也没有明确声明论文内容是不可执行的来源数据。

**影响**

- Reviewer 可以对 excerpt 做合理审查，但用户看不到它并非完整全文。
- `verbatim_quote` 只能证明某段文字出现过，不能证明问题覆盖了全文或引用已核验。
- 工作区论文若包含类似“忽略上述规则”的文本，Reviewer prompt 没有独立的数据边界。

**修复决策**

1. Reviewer 输入 envelope 增加：
   `source_hash`、`original_chars`、`excerpt_chars`、`covered_sections`、`truncated`。
2. 每个问题增加：
   `source_section`、`anchor`、`evidence_status`、`verification_action`。
3. 允许输出 `not_assessable`，不要为了满足“3–6 个问题”而强行凑数。
4. 所有静态规则放在前，论文正文作为最后一个明确标注的不可执行数据块。
5. 最终综合结论必须传播各视角失败、空结果和截断状态，不能只返回 accept/minor/major/reject。

### P1 — P5. 提示词文件缺失时会静默降级

**事实**

1. `prompts.loader._load_raw()` 在文件不存在时直接返回空字符串。
2. 各 renderer 随后使用代码内的简化 fallback prompt，服务仍可继续运行。
3. Reviewer prompt 加载失败后也会使用简化 fallback。
4. 当前 session 元数据只保存 workspace、model、usage、state 和 outcome，没有 prompt hash、模板版本或实际 active skill 列表。

**影响**

- 打包遗漏、路径错误或模板损坏时，界面仍能工作，但学术约束可能已变弱。
- 之后无法回答“这次异常到底使用了哪一版 prompt 和哪些技能”，复现能力不足。

**修复决策**

1. 启动时建立 prompt registry，校验必需文件、schema、模板变量和 hash。
2. 核心 prompt 缺失时 fail closed；可选 prompt 才允许带明确 WARNING 的降级。
3. session 和结构化日志保存：
   `prompt_bundle_version`、`system_prompt_hash`、`active_skills`、`tool_schema_hash`。
4. UI 的诊断信息显示当前 prompt bundle 是否完整，但不显示敏感正文。

### P1 — P6. Dirty Monaco 内容与磁盘写入之间没有并发契约

**事实**

1. 前端会把 `context_text` / selection 内容发给 Agent，但 `ChatRequestV2` 没有 `is_dirty`、编辑器版本或内容 hash。
2. selection edit 有精确范围约束；普通 Agent 文件写入没有对应的 dirty-tab 版本门禁。
3. Agent checkpoint 后，`reloadOpenTabs()` 会跳过 `tab.isModified`，避免覆盖用户未保存内容。
4. 该跳过发生在 Agent 已经写入磁盘之后，不能阻止磁盘内容与脏编辑器内容形成分叉。

**影响**

这次 session 未证明发生了实际数据丢失，但代码契约允许以下风险序列：

`用户有未保存修改 → Agent 基于磁盘旧版本写入 → 前端因 dirty 跳过刷新 → 用户随后保存并覆盖 Agent 结果，或 Agent 结果覆盖用户预期`。

**修复决策**

1. 普通 Agent 请求携带打开文件的 `dirty`、`editor_version` 和 `content_hash`。
2. 对 dirty 文件的磁盘 mutation 默认阻断，要求用户先保存、改为 selection edit，或显式选择冲突处理。
3. 文件工具增加 expected hash；hash 不匹配时返回 conflict，不进入普通写入。
4. checkpoint 必须带 before/after hash，前端展示冲突状态而不是只跳过刷新。

### P2 — P7. Prompt schema 当前只被测试，不参与运行时加载

**事实**

1. 多个 prompt 文件有 YAML frontmatter，定义 role、task、constraints、format 和 fallback。
2. 实际 renderer 用正则提取正文中的 `System Prompt` / `User Prompt Template`。
3. `validate_prompt_schema()` 在生产加载链中没有调用点。
4. 因此前置 schema 与正文可发生漂移，即使 schema 测试通过，运行时模型也未必收到相同规则。

**修复决策**

1. 选择单一 source of truth：优先让结构化 PromptSpec 直接渲染运行时 prompt。
2. 若暂时保留正文模板，启动时校验 frontmatter 与正文的关键约束一致。
3. 测试不再只检查字段存在和字符串出现，要检查最终发送给 provider 的完整 prompt。

### P2 — P8. 动态内容位置不利于缓存，也扩大提示注入面

**事实**

1. Agent V2 system prompt 在静态工具规则之前插入当前日期、工作区和工具列表。
2. Reviewer 模板把 venue 和 paper excerpt 放在后续静态要求之前。
3. `_extract_user_template()` 会提取 `User Prompt Template` 之后的全部内容；带 few-shot 的模板会把真实输入放在示例和说明之前。

**影响**

- 每次工作区、日期或输入变化都会使后续静态前缀失去复用机会。
- 来源文本与操作指令交错，模型更难区分“要分析的数据”和“必须执行的规则”。
- 这是性能和稳健性风险，不是本次造数的直接证据。

**修复决策**

1. 所有稳定规则、输出 schema、失败语义和示例放在前。
2. 日期、工作区、工具清单、论文正文等动态内容放在尾部。
3. 对 editor context、paper、tool output 使用明确的不可执行数据 envelope。
4. 不机械追求缓存：若移动小变量会破坏语义，可保留并记录原因。

### P2 — P9. 自定义技能默认自动激活，缺少注入预算和可信度标记

**事实**

1. `Skill` 的 `default_active` 默认值为 `True`。
2. `data/agent_v2/skills/` 中没有显式配置的技能会自动进入所有 Agent V2 system prompt。
3. 当前 loader 没有技能内容长度上限、schema 强校验或 prompt 总预算检查；现有测试甚至允许 100,000 字符技能和 100 个技能注入。

**影响**

- 一个为特定论文场景编写的技能可能影响普通翻译、文件操作或问答。
- 过长、相互冲突或含指令的数据文件会稀释核心安全规则。

**修复决策**

1. 自定义技能默认 `default_active: false`。
2. 对名称、layer、长度、来源和允许工具做 schema 校验。
3. 核心安全契约优先级不可被 skill 覆盖；skill 只能收紧任务规则，不能放宽证据和文件安全边界。
4. 超出 prompt 预算时明确报错或拒绝激活，不做静默截断。

### P2 — P10. 现有提示词测试偏“存在性”，不能证明行为正确

**事实**

1. Agent system prompt 测试主要断言某些字符串存在。
2. skill 测试主要断言能加载、能激活、能注入和所需工具存在。
3. PromptSpec 测试主要检查 frontmatter 字段和形式约束。
4. 本次失败类型——无来源数字、截断后声称完整、未渲染却称验收通过、DSML 泄漏——都不由上述测试覆盖。

**修复决策**

新增行为级 prompt contract tests：

1. 无 evidence ref 的新增数字必须被 runtime 拒绝或标记待核验。
2. `complete=false` 的工具结果不得产生“完整/全部核验”终态。
3. paper/context 内嵌“忽略规则”时不得改变系统行为。
4. 部分 Reviewer 失败或 excerpt 截断时不得返回无警告的全稿结论。
5. 未执行脚本时不得写入计算结果；未渲染时不得通过 figure acceptance。
6. provider 返回文本化 DSML/tool protocol 时不得进入 token、response 或历史 UI。
7. prompt 文件缺失、schema 漂移、未知 skill 和 prompt 超预算必须产生确定性错误。
8. 至少用 DeepSeek 和本地 Ollama 的录制响应做 provider contract 回放，不依赖每次真实联网。

## 8. 提示词修改优先级

| 顺序 | 修改对象 | 原因 |
|---:|---|---|
| 1 | Agent V2 核心 system prompt | 本次文件改写真正执行的入口 |
| 2 | evidence gate 与工具结果 envelope | 把提示规则变成可执行约束 |
| 3 | `nature_reviewer`、`nature_figure`、`nature_citation`、`nature_writing` | 本次事故直接涉及的技能 |
| 4 | Ledger / Reviewer / run_command / write_file 工具说明 | 模型行动取决于工具契约 |
| 5 | `/api/edit` 的 one-shot prompt | 防止 AI 面板与 Agent 面板安全边界不一致 |
| 6 | Reviewer perspective prompts | 增加覆盖率、锚点和不可评估状态 |
| 7 | prompt registry、版本和行为测试 | 保证打包、回放和后续修改可追踪 |
| 8 | 翻译、润色、连贯性、合规模板 | 只做边界和渲染器修复，不盲目重写 |

## 9. 修复前再次运行的临时控制

在阶段 1 完成前，如果继续用当前 Agent 测论文：

1. 只在论文副本或有可恢复版本的工作区运行。
2. 有未保存 Monaco tab 时，不批准 Agent 对同一文件的普通写入；优先保存或只做 selection edit。
3. 新增数字、比例、样本量、引用和“经验证”措辞，一律要求在审批前看到来源路径或脚本 stdout。
4. `allow_session` 语义修复前使用 `allow_once`，避免形成错误的长期授权预期。
5. 图表只认“已生成”；没有 PDF/PNG 渲染检查时，不认“投稿级验收完成”。
6. 稿件修改后把旧 Ledger/Reviewer 视为 stale，手动重建后再进行下一轮审查。
7. 长任务拆成“读取与核验 → 修改 → 生成图表 → 最终审查”四个独立 turn，每个 turn 检查实际产物。

这些临时措施只能降低风险，不能替代代码修复。

## 10. 更新后的实现边界

首个实现批次仍只做阶段 1，但范围明确为一个完整闭环：

1. Agent V2 核心 evidence / completeness / terminal-state prompt；
2. 新增学术事实的 evidence gate；
3. Ledger / Reviewer 分页与完整性 envelope；
4. prompt bundle hash 和 active skill 记录；
5. 对应的行为级回归测试；
6. 本次稿件新增数字的待核验清单。

以下内容不混入首批：

- Windows 子进程编码和命令体验；
- `allow_session` 跨请求持久化；
- PDF 渲染工具；
- session journal/compaction；
- 全量 prompt 模板重写；
- 前端大规模交互改版。

首批通过后，再按 R1/R2/W1 → U1/U2 → O1/O2 的顺序推进。

## 11. 2026-07-30 独立复核与修复状态

### 11.1 可靠性结论

本报告的事实层可靠性高，但“主要风险”“修复顺序”和具体方案属于基于事实的工程判断，不等同于已由生产复现证明的唯一方案。

独立复核结果：

1. 重新解析原始 session 后，6 个用户消息、90 个 Assistant 消息、92 次工具调用与结果、15 个错误结果、35 次 mutation、6 个变更文件、0/0 token 用量均与报告一致。
2. Ledger 13,552 字符和 Reviewer 6,243 字符被统一截断到 4,000 字符、DSML 文本泄漏、PCA 先写入 78.3% 后实算为 59.1%、PRISMA 分项在无来源时写入等关键证据均可从 session 复现。
3. 原基线代码与报告描述一致：Agent V2 未使用全局学术提示词，审批只存在于 runtime 内存，审稿工具整文件读取后统一截断，session 缺少逐消息完整性元数据，默认 skill 自动激活。
4. 报告没有证明所有建议都是完整修复设计；尤其 PDF 视觉验收、增量 journal、Ledger/Reviewer 自动重建和真实 provider 回放仍需单独设计与验收。

因此，本报告适合作为故障事实和修复优先级依据；修复后的当前状态应以本节和当前测试结果为准。

### 11.2 已完成闭环

| 问题 | 当前状态 | 实现结果 |
|---|---|---|
| A1 无来源事实写入 | 已修复高风险路径 | 学术稿件新增数字、引用和“已验证”措辞在 mutation 前执行 evidence gate；`write_file` / `str_replace` 支持 `evidence_refs`，checkpoint 持久化来源与前后 hash |
| A2 截断状态被称为完整 | 已修复 | Ledger / Reviewer 改为 summary/detail、cursor/limit/item_ids envelope；summary 有明细时 `complete=false`，并返回 `next_cursor`、`source_version`、`stale` |
| R1 DSML 泄漏 | 已修复 | finalizer 检测文本化工具协议，重试一次后返回确定性 `PARTIAL`，不再把协议文本作为正常终态 |
| W1 Windows 命令与编码 | 已修复 | `dir`、`mkdir`、`md` 返回稳定错误码和建议；子进程强制 UTF-8 并记录实际解码来源 |
| U1 `allow_session` 失效 | 已修复 | 授权按 session 持久化，并绑定 workspace grant 与 policy version；跨 grant 不复用 |
| O1 不可观测 | 已修复主要部分 | 记录 turn/message/tool 标识、工具状态/错误码/耗时、会话累计摘要、prompt bundle/hash、tool schema hash 和 active skills |
| P1 Agent V2 核心约束缺失 | 已修复 | 静态核心安全契约置于 system prompt 前部；明确 evidence、完整性、终态和协议泄漏规则 |
| P2/P9 skill 污染与预算 | 已修复 | 内置和自定义 skill 默认显式启用；校验名称、layer、单项长度、激活数量和总 prompt 预算 |
| P3 `/api/edit` 边界较弱 | 已修复 | one-shot edit 使用运行时 PromptSpec 和统一的短安全前缀，编辑模板禁止编造数字、引用与验证结论 |
| P4 Reviewer 覆盖不足 | 已修复 | 审稿 excerpt 按章节分配预算，提示中携带 source hash、覆盖章节、字符数和 truncated；会话持久化 `source_coverage` 和证据字段 |
| P5 提示词静默降级 | 已修复 | 必需 prompt bundle 在启动时 fail-closed，并记录稳定版本与 hash；Reviewer 必需模板缺失不再使用弱 fallback |
| P6 Dirty Monaco 冲突 | 已修复 | 前端发送每个打开文件的 dirty/hash/version；runtime 在审批前阻止脏文件写入和已保存文件 hash 漂移 |
| P8 动态内容位置 | 已修复主要入口 | Agent 核心静态规则前置；Reviewer 规则前置，论文内容放入末尾的 `untrusted_paper_excerpt` |

### 11.3 仍未关闭的结构性事项

1. R2 仍缺 PDF/PNG render + vision 工具级验收门禁；当前只能阻止系统把未验证结果表述为已完成视觉验收，不能执行真正的视觉验收。
2. U2 已能通过文档 hash 将旧 Ledger/Reviewer 标为 `stale`，但尚未提供显式的重建工具和 mutation 后自动联动策略。
3. O2 已外置重复编辑器正文并记录截断/消息完整性，但 session 仍以完整快照重写；增量 journal、compaction 和 mutation preimage 外置尚未完成。
4. P7/P8 只完成关键 Agent、Reviewer 和 `/api/edit` 入口；其余历史 prompt 模板尚未统一迁移到单一结构化运行时渲染器。
5. P10 已新增行为级单元与集成测试，但尚未加入 DeepSeek/Ollama 真实录制响应回放。
6. 尚未实现多文件原子 `multi_replace`，也未对本次用户论文中已写入的 PRISMA、消融、PCA 和 Pareto 结论执行来源清理。

### 11.4 验证证据

- 后端全量：`2321 passed, 14 skipped`。
- 前端全量：`834 passed`。
- Agent V2 与本次相关模块定向回归：`880 passed`。
- TypeScript：`vue-tsc --noEmit` 通过。
- Python 静态检查：Ruff check 与 format check 通过。
- 生产前端：`vite build` 通过。

上述验证证明当前仓库内契约与回归测试通过；它不替代真实 DeepSeek/Ollama、长会话崩溃恢复和桌面端视觉验收。

## 12. 2026-07-30 新会话复测：拦截存在，但交付闭环仍失败

### 12.1 修正结论

新会话 `sess_1d138ccd76234322840988e5fb7e56d9` 证明第 11.2 节对 A1 的“已修复高风险路径”表述不完整：旧修复能阻止部分无证据写入，但不能在阻止后自动恢复并完成交付，也不能阻止运行时把空文件和聊天替代品标成 `COMPLETE`。

因此，可靠结论应修正为：

1. evidence gate 是必要的安全约束，但不是完成机制。
2. 写入失败必须形成可跨 turn 恢复的 pending action。
3. 用户要求文件交付时，聊天回复不能清除 pending action，也不能产生 `COMPLETE`。
4. 只有目标文件真实 mutation 成功、最终分块已提交且 pending action 清零，才能进入 `COMPLETE`。

### 12.2 新会话事实证据

| 指标 | 结果 |
|---|---:|
| 用户消息 | 4 |
| 持久化消息 | 97 |
| 工具调用 / 结果 | 66 / 66 |
| 工具错误 | 7 |
| `web_search` / `web_fetch` | 24 / 22 |
| 输入 / 输出 token | 896,953 / 25,264 |
| `write_file` 尝试 / 失败 | 5 / 5 |
| mutation / changed files | 0 / 0 |
| 持久化终态 | `COMPLETE` |

关键失败链：

1. 首次约 9,386 字符的整文件写入因工具 JSON 截断而失败。
2. 后续 4 次写入均被 evidence gate 拒绝；模型反复传入并不存在于 session 的伪造 `tool_use_id`。
3. 数字扫描把当前日期、arXiv 标识符分段以及 `Darknet-19`、`Darknet-53` 等名称中的数字当成独立学术事实，扩大了误拦截。
4. 用户发送“继续完成刚才未完成的当前任务”后，Agent 读取到空文件，却改为“先口头汇报”。
5. runtime 仅因收到 `response` 事件就持久化 `COMPLETE`，没有检查失败 mutation 或未完成交付。
6. `arxiv_search` 请求使用 HTTP 且不跟随重定向，实际返回 301。
7. 部分抓取的 arXiv 编号对应无关论文；仅按编号存在性自动放行会造成错误来源污染。

这条链路直接支持用户反馈：只有拦截、没有恢复，对文件交付没有实际完成价值。

### 12.3 本轮完成的恢复闭环

| 机制 | 修复结果 |
|---|---|
| 证据引用恢复 | 对模型传入的失效或伪造 `tool_use_id`，只有在真实成功工具结果中找到完全一致引文时才重绑定到实际 ID |
| 已有来源自动复用 | 可从 session 内成功的 `web_fetch`、`arxiv_search`、`rag_search`、`read_file`、`run_command` 结果自动取证 |
| 错源防护 | arXiv/source ID 除编号一致外，还要求声明上下文与来源标题或模型词汇重合；无关论文不能仅凭相同编号通过 |
| 误报收敛 | 当前运行日期不再触发 evidence gate；arXiv ID 作为整体来源标识处理；连字符模型名中的数字不再拆成事实 |
| Pending action | 失败写入只持久化工具、目标、错误码和有限诊断信息，不持久化未提交正文；可跨 turn 恢复 |
| 防聊天降级 | pending action 存在时，runtime 自动拒绝前两次聊天终答并要求继续恢复；仍未解决时只能返回 `PARTIAL` |
| 正确终态 | 成功 mutation 或最终写入分块会清除对应 pending action；未清零时不能进入 `COMPLETE` |
| 大文件交付 | `write_file` 新增原子 `overwrite` / `append` 和 `final_chunk`，支持紧凑分块续写并保留 mutation journal / Undo |
| arXiv | 改用 HTTPS、跟随重定向、限制 1–20 条结果并记录来源元数据 |
| 检索预算 | 每 turn 最多 24 次研究工具调用，20 次后提示停止扩张、转入筛选、写入和验证 |
| Prompt 契约 | 明确“安全错误是恢复信号”“不得伪造 ID”“文件交付不得降级成聊天”“大文本分块写入” |

该实现保留最新用户消息的范围优先级：旧 pending action 只在用户明确说“继续 / 未完成 / resume”等情况下恢复，不会自动劫持无关的新任务。

### 12.4 行为级验证

新增回归覆盖：

1. 伪造 ID + 真实精确引文会解析到实际工具结果并成功写入。
2. 同一 arXiv 编号但标题和声明上下文不匹配时，即使传入精确引文仍被拒绝。
3. 当前日期和模型标识符不会制造无意义的证据缺口。
4. 首次写入被拒绝后，Agent 读取已有来源、重算证据、重试 mutation，最终文件真实更新且 pending action 清零。
5. Agent 连续尝试用聊天回复替代文件时，前两次自动恢复，第三次只能得到带 pending action 的 `PARTIAL`。
6. 跨 turn 的“继续完成”可恢复旧 pending action，写入成功后进入 `COMPLETE`。
7. 分块 overwrite/append 的最终文件、工具元数据和 session 持久化均正确。
8. 研究调用在独立预算耗尽时先于全局 64 次工具预算停止。

当前验证结果：

- Agent V2 全套：`795 passed`。
- 后端全量：`2339 passed, 7 skipped`。
- Ruff：修改文件 `check` 通过。
- Git whitespace：`git diff --check` 通过。

### 12.5 尚需真实桌面验收

代码和回归测试已覆盖本次确定性失败链，但仍需用修复后的新 Agent V2 session 做一次桌面复测：

1. 要求 Agent 检索有限数量的相关论文并写入 `draft/untitled.md`。
2. 观察来源错误时是否自动复用真实工具结果并重试，而不是只返回拦截错误。
3. 制造一次大文本分块写入，确认最后一个 `final_chunk=true` 后文件完整且可 Undo。
4. 在写入仍失败时确认 UI 显示 `PARTIAL` 和 pending action，而不是 `COMPLETE`。
5. 重新打开 session 后发送“继续完成”，确认运行时从 pending action 恢复。

旧 session 已经以旧 runtime 记录了错误终态，不能用代码升级追溯性地改写为真实完成；验收必须创建新 session 或明确继续该 session 后重新执行交付。
