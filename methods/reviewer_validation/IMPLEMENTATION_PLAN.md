# Reviewer Validation：实施与验收计划

结论：Work A–F 已通过各自限定范围的开发态、来源追溯与 pre-pilot 验收，但尚无真实模型、held-out 或 formal data 运行，也无 RQ1–RQ3 效果结论；下一执行边界是真实 development 输出的 G1 人工 pilot，G1、G2、G4 仍为 BLOCKED，正式实验继续禁止。

## 1. 状态、依据与共同边界

- Canonical protocol：仓库根目录 `METHODOLOGY.md`。本文件只定义实施所有权与验收，不修改研究问题、指标、阈值或冻结规则。
- 核对基线：`python/src/argument/ledger.py` 当前把 Promise 提取与 discharge 分类串在同一流程；`python/src/argument/reviewer.py` 当前从 venue 自动加载 profile，并让 `run_review` 默认混合多类 checks；`python/src/argument/llm_client.py` 当前可从 Cloud 降级到 Ollama。
- 当前状态：protocol review、开发态基础设施、Work E 官方来源审计与 Work F pre-pilot profile 应用验收为 PASS；G1 Pilot gate、G2 Freeze gate 和 G4 Isolation gate 均为 BLOCKED。任何 scaffold、mock、单元测试、来源复核或 development infrastructure 通过都不得表述为正式实验结果。
- Work A PASS：生产单元测试 30 passed，Ledger staging 测试 24 passed；该结论只覆盖两阶段可评测性、追踪与失败保留基础设施。
- Work B PASS：生产 Reviewer 单元测试 46 passed，venue isolation 测试 12 passed；canonical fixture provenance 遗留项已关闭。该结论只覆盖 profile-only 隔离基础设施，不等于 G4 PASS。
- Work C PASS：scaffold 测试 12 passed，draft verifier 只报告预期 pending，strict verifier 以 `FORMAL_RUN: BLOCKED` 非零退出；这是未冻结状态的正确结果，不等于 G2 PASS。
- Work D PASS（infrastructure only）：生产 Anchor 测试 40 passed，Anchor evaluation 测试 7 passed，scaffold 回归 12 passed；未生成正式 120 项 challenge。15 项 development 指标中的非完美结果已原样保存在 `outputs/pilot/anchor/run/metrics.json`，不得据此形成研究结论。
- 独立 capstone PASS（development infrastructure only）：未调用外部 LLM，未读取 held-out，未生成或运行 formal data；因此不改变任何研究 gate。
- Work E PASS（source audit only）：首轮独立全量复核因两处官方日期遗漏、KDD-Y4/CHI-Y4 适用范围泛化和非规范 decision 术语而 FAIL；窄范围纠正后全量复审 PASS。最终为 20 个官方 source、20 个唯一 URL、42 个旧 YAML atom、35 个 replacement，决策为 6 `keep`/29 `rewrite_conditionally`/7 `remove`。
- Work F PASS（pre-pilot inputs only）：实施后独立复核首先判定 REVISE，因为 `run_venue_ab.py` 仍使用 `profile_text[:600]` 使长 NeurIPS 成对 probe 失败，且 CHI-Y4 的 source 顺序不一致；窄范围修复后最终全量复审 PASS。focused tests 为 Reviewer 60 passed、grounding 19 passed、isolation 13 passed、scaffold 12 passed；长 NeurIPS full-profile mock pair 完整进入 prompt/artifact，generic block 的规范 UTF-8/LF 表示为 219 bytes，SHA-256 `30fd129da348e52128cfceab4844b54dedb7abdb39c9fe217251bc29fb60619a`。draft verifier PASS 但明确 `FORMAL_RUN: BLOCKED`，strict verifier 按预期非零退出。
- 研究证据边界：Work E/F 未运行真实模型，未读取 held-out，未生成或运行 formal data；它们只支持“来源映射和消费路径已按契约实施”，不支持 profile 提高官方标准遵循度或任何 RQ3 效果结论。
- 正式运行禁令：首轮只允许 synthetic fixture 和 protocol 指定的 development 输入。不得对 14 篇 held-out、80 项正式 status challenge 或 120 项正式 Anchor challenge 运行系统、生成预测或调参；正式 Anchor case 本身只能按 Work D 的“生成后再冻结”规则离线生成，生成过程不得调用 `relocate`。
- 等价性原则：评测路径必须复用生产 excerpt、prompt、参数、解析与状态映射；禁止另抄一份“看起来相同”的 prompt，禁止为提高 pilot 表现改写 production semantics。
- 失败保留原则：空响应、无效 JSON、超时、provider 错误和合法空数组是不同结果；不得把失败改写成成功的空结果，不得用补跑覆盖首次记录。
- 安全原则：所有 prompt、excerpt、raw response 和错误可以保存，但 API key、认证头、本地私密配置及未授权全文不得进入 artifact。

## 2. 非重叠所有权

以下是首轮唯一写权限；未列出的文件一律只读。`IMPLEMENTATION_PLAN.md` 与 `METHODOLOGY.md` 由协调者维护，三个实现者均不得编辑。

| 工作包 | 唯一可编辑文件或生成目录 | 明确只读依赖 |
|---|---|---|
| A — Ledger 两阶段可评测性 | `python/src/argument/ledger.py`；`python/tests/unit/test_ledger.py`；`methods/reviewer_validation/scripts/run_ledger.py`；`methods/reviewer_validation/tests/test_ledger_staging.py`；`methods/reviewer_validation/outputs/pilot/ledger/**` | `companion_models.py`、`companion_store.py`、`section_utils.py`、`llm_client.py`、工作包 C 的 schemas |
| B — Venue 单因素隔离 | `python/src/argument/reviewer.py`；`python/tests/unit/test_reviewer.py`；`methods/reviewer_validation/scripts/run_venue_ab.py`；`methods/reviewer_validation/tests/test_venue_isolation.py`；`methods/reviewer_validation/outputs/pilot/venue/**` | `venue_profiles.yaml`、`llm_client.py`、`section_utils.py`、工作包 C 的 schemas |
| C — Protocol/freeze 脚手架 | `methods/reviewer_validation/README.md`；`protocol.yaml`；`protocol.sha256`；`freeze_manifest.json`；`freeze_manifest.sha256`；`schemas/protocol.schema.json`；`schemas/freeze_manifest.schema.json`；`schemas/promise_gold.schema.json`；`schemas/anchor_case.schema.json`；`schemas/venue_applicability.schema.json`；`schemas/venue_review_score.schema.json`；`schemas/run_record.schema.json`；`scripts/verify_freeze.py`；`tests/test_protocol_scaffold.py` | `METHODOLOGY.md` 与当前生产代码 |

同一文件不得跨包修改。A/B 可以并行实现，但只有 C 的 schema handback 被接受后，A/B 才能宣称其记录格式通过集成 gate；在此之前只能报告本地实现状态。

## 3. 工作包 A：Ledger 两阶段可评测性

### Premise

RQ1 需要分别测量 extraction、gold-conditioned discharge classification 和 end-to-end；当前生产流程把前两阶段、重试、组装与持久化串联，阶段输入输出不可完整观察。若不先建立生产等价 staging，任何分阶段指标都会混入实现差异。

### 依赖与实施边界

- 复用 `ledger.py` 当前实际构造的 promise/body excerpt、两段 prompt、生成参数、JSON 兼容解析和四实质状态映射；由实现者选择最小重构方式，不预设新的类名、函数名或公共 API。
- 现有 `build_ledger` 和 `rebuild_ledger` 的生产调用方、SSE 顺序、存储结果与错误语义不得改变。
- Gold-conditioned 路径只把冻结 gold Promise 注入 classification 阶段；不得先运行 extraction 后再把预测结果冒充 gold。
- A 不得修改共享 LLM 客户端。单 client/no-fallback 的正式运行策略由 runner 显式约束，并使用 C 的 run-record schema。

### 可证伪验收 gates

1. **A1 Production-equivalence PASS/FAIL**：对同一 fixture 和同一伪造 LLM 返回，重构前后 `build_ledger` 的外部 SSE 事件类型、Promise/Anchor 内容、complete 统计与持久化 Ledger 等价；允许的差异只有非确定性 ID/时间，且比较器必须显式列出这些字段。
2. **A2 Stage-identifiability PASS/FAIL**：runner 能独立执行 extraction、显式 gold-conditioned classification 和 end-to-end 三种模式；测试证明 classification 模式没有调用 extraction，end-to-end 使用本次 extraction 输出。
3. **A3 Production-path reuse PASS/FAIL**：测试对实际发送值做断言，证明 staging 与生产使用相同 excerpt 字节、prompt 字节、temperature、max tokens、json mode、解析规则和同 provider 内重试语义；源码中不存在第二份手写等价 prompt。
4. **A4 Complete trace PASS/FAIL**：每个 attempt 均保存模型实际看到的 excerpt 文本及 coverage/hash、完整 prompt 及 hash、原始响应及 hash、解析产物、attempt 序号、终止状态、时间、代码 commit、protocol hash 和经脱敏的 provider/model/参数。首次失败记录不可覆盖。
5. **A5 Failure taxonomy PASS/FAIL**：合法空 Promise 数组、空响应、无效 JSON、超时/provider 错误、分类缺项和 unknown 分别可观察并进入记录；测试证明它们不会被静默合并。
6. **A6 Safety/schema PASS/FAIL**：pilot artifact 通过 C 的 run-record schema 和 secret 检查；任何 schema 不符或凭据字段出现都失败关闭。

### 获准的 pytest 命令

在仓库根目录分别运行：

```powershell
Set-Location python
python -m pytest tests/unit/test_ledger.py -q
```

```powershell
Set-Location python
python -m pytest ../methods/reviewer_validation/tests/test_ledger_staging.py -q
```

不得以全量测试通过替代上述阶段等价性断言；首轮也不需要运行全量测试。

### 必须带回的 runtime/pilot 观察

- 至少一个 synthetic fixture 的三模式 trace，以及 C 可用后一个 development 输入的 extraction 与 gold-conditioned trace。
- 实际 LLM 调用次数、每次 attempt 的退出原因、提取数量、分类数量、unknown/empty/invalid/provider-failure 计数。
- 一个可人工打开的记录示例，证明 excerpt、prompt、raw response 与 parser output 均存在且 hash 可复核。
- 生产等价比较摘要；若任何字段不同，列出差异和影响，不得用“测试通过”概括。

## 4. 工作包 B：Venue profile 单因素 prompt/runner 隔离

### Premise

RQ3 只估计 profile 文本的增量作用。当前 Reviewer 同时把 venue 名称和由该名称自动加载的 profile 写入 prompt，且默认 checks 不止 LLM；若没有显式 override 和严格 runner，G/V 差异无法归因于 profile。

### 依赖与实施边界

- 为实验路径提供显式 profile 选择/覆盖能力，但未提供覆盖时的生产行为必须保持不变；由实现者选择最小接口，不预设参数或对象名称。
- 每个 pair 的 G/V 使用完全相同的非空 venue label、paper/excerpt、persona、prompt template、provider/model、生成参数和 `checks=["llm"]`；唯一可进入模型请求的条件差异是 profile 文本。
- 只能调用串行 Reviewer 路径；不得调用 parallel Reviewer、ledger、coherence 或 related-work checks。
- 每次调用恰有一个非空逻辑 provider client。禁止同时传入 Cloud 与 Ollama，禁止失败后构造或调用第二 client/model；同 provider、同模型的 production 格式修复重试可以保留，但每次 attempt 必须记录。

### 可证伪验收 gates

1. **B1 Backward-compatibility PASS/FAIL**：未启用实验 override 时，现有 venue profile 加载、prompt、SSE 和 ReviewSession 行为不变，现有 Reviewer 单元测试通过。
2. **B2 Single-factor diff PASS/FAIL**：对固定 pair 生成 canonical request diff；除 profile 文本/profile hash 和不进入模型的 condition/order metadata 外，diff 必须为空。venue label 在 G/V 中字节相同且均出现在同一 prompt 位置。
3. **B3 Serial LLM-only PASS/FAIL**：测试证明调用只经过串行 `checks=["llm"]` 路径，并证明 ledger、coherence、rw 和 parallel perspective 路径调用次数均为 0。
4. **B4 Exactly-one-client PASS/FAIL**：runner 对零 client 或两个 client 均在请求前失败；一个 client 失败时记录 provider failure 并停止该 invocation，fallback client call count 必须为 0。
5. **B5 Failure visibility PASS/FAIL**：provider exception、timeout、空响应和合法 `[]` 在 manifest 中具有不同终止状态；实验 runner 不得把 Reviewer 当前捕获异常后产生的空 complete 误记为成功空 review。
6. **B6 Manifest completeness PASS/FAIL**：每条记录至少包含 `run_id`、`pair_id`、condition、paper ID、恒定 venue label、profile/prompt/excerpt/output hash、excerpt coverage、唯一 provider/model 与生成参数、attempts、开始/结束时间、终止状态或错误、代码 commit 和 protocol hash；不得包含 secret。

### 获准的 pytest 命令

在仓库根目录分别运行：

```powershell
Set-Location python
python -m pytest tests/unit/test_reviewer.py -q
```

```powershell
Set-Location python
python -m pytest ../methods/reviewer_validation/tests/test_venue_isolation.py -q
```

不得在首轮运行 `test_reviewer_parallel.py` 作为实验路径证据；它不属于 RQ3 的处理条件。

### 必须带回的 runtime/pilot 观察

- 至少一个 synthetic pair 的 canonical request diff，以及 C 可用后一个 development paper 的 G/V pair trace；不得使用 held-out paper。
- 每个 invocation 的逻辑 client 数、实际 call/attempt 数、fallback call 数、终止状态和原始输出 hash。
- `checks`、venue label、excerpt hash、prompt hash 与 profile hash 的配对表；表中必须能直接看出只有 profile 改变。
- 至少一个注入 provider failure 的 pilot 记录，证明失败未变成合法空 review，也未触发第二 client。

## 5. 工作包 C：Protocol/schema/freeze-manifest 脚手架

### Premise

方法总纲已经规定 G2，但仓库尚无可机读 protocol、schema、detached hash 与 fail-closed verifier。没有该脚手架，A/B 的运行记录无法统一验证，也不能证明正式输入在 held-out 运行前冻结。

### 依赖与实施边界

- 逐项转录 `METHODOLOGY.md` 已确定的 RQ、样本数、seed 槽位、指标、分母、阈值、失败规则、双坐标和 artifact 契约；不得借实现之名改变 protocol 内容。
- scaffold 必须明确标为 `draft`。未知模型、语料、hash 或 seed 使用 schema 允许的未冻结状态，不得伪造值；strict verifier 必须因此非零退出，直至真实输入补齐。
- `protocol.sha256` 与 `freeze_manifest.sha256` 是 detached hash；manifest 不包含自身 hash，避免循环引用。
- 路径必须为仓库内规范化相对路径。verifier 拒绝绝对路径、`..` 边界逃逸、重复 artifact ID、未知 schema 版本、hash 不匹配与 secret-like 字段。

### 可证伪验收 gates

1. **C1 Protocol fidelity PASS/FAIL**：机器可读 protocol 覆盖 METHODOLOGY 的三个 RQ、16/14/10 样本结构、3 runs、80/120 challenge、42 pairs/84 reviews、主要分析单位、bootstrap、+0.05 不劣界和失败/重试规则；人工逐项表无遗漏或新增推断。
2. **C2 Schema enforcement PASS/FAIL**：schemas 拒绝未知枚举、越界/非半开坐标、quote 与 span 不一致、synthetic mapping gold、缺失 denominator 字段、secret-like 字段和无终止状态的 run record；合法最小 fixture 通过。
3. **C3 Fail-closed freeze PASS/FAIL**：draft 模式只验证结构；strict 模式在任一正式输入缺失、未列入 manifest、hash 不匹配或 schema 失败时非零退出并列出具体 artifact，不得自动修复或重算正式输入。
4. **C4 Hash determinism PASS/FAIL**：相同字节产生相同 detached hash；修改任一引用文件的一个字节后 verifier 必须失败。协议与 manifest 自身 hash 不通过内嵌自引用实现。
5. **C5 Boundary/safety PASS/FAIL**：所有 artifact 路径解析后仍位于 `methods/reviewer_validation/` 或 protocol 明确许可的仓库输入路径；日志不打印 secret 值。
6. **C6 Consumer readiness PASS/FAIL**：A/B 的最小示例 run record 均能被同一 schema 校验；Anchor 后续所需 schema 已存在，但不创建 generator、runner 或正式 cases。

### 获准的 pytest 与 verifier 命令

在仓库根目录运行：

```powershell
Set-Location python
python -m pytest ../methods/reviewer_validation/tests/test_protocol_scaffold.py -q
```

以下是无网络的受限观察命令；第一个预期为 0，第二个在正式输入尚未补齐时预期为非 0：

```powershell
Set-Location python
python ../methods/reviewer_validation/scripts/verify_freeze.py --allow-draft
python ../methods/reviewer_validation/scripts/verify_freeze.py
```

### 必须带回的 runtime/pilot 观察

- draft verifier 的摘要和 strict verifier 的完整缺失项列表；strict 失败在本阶段是正确行为，不得据此宣布 G2 PASS。
- 合法/非法 schema fixture 的逐项结果，以及单字节篡改触发 hash failure 的证据。
- protocol-to-methodology 覆盖表、当前 detached hashes 和所有仍未冻结字段。
- A/B 示例记录的 schema 验证结果；不要求也不允许生成正式模型输出。

## 6. 工作包 D：Anchor dev-pilot 修复、确定性挑战生成与指标（顺序执行）

### Premise

RQ2 的真实消费者是审稿回复中的 Anchor 稳健性主张，production `relocate` 是唯一被测实现。现有 34 个 Anchor 单元测试虽通过，却允许两个已知错误：重复 exact quote 会取第一次出现而非上下文一致位置；真实目标删除后，相似干扰项会被 fuzzy path 错误重定位。故本包先用 development-only probes 修复可证伪缺陷，再建立确定性生成、运行与计分路径；它不以测试通过替代正式 120 项结果。

### 依赖、所有权与禁止项

- **硬依赖**：协调者已接受 Work C 的 C1–C6；若 C 的 `anchor_case` schema、artifact resolver 或 fail-closed verifier 回退，D 立即停止。C PASS 只授权 development pilot，不授权正式生成或运行；G2 仍为 BLOCKED。
- **D 独占修改**：`python/src/argument/anchor.py`、`python/tests/unit/test_anchor.py`、`methods/reviewer_validation/scripts/generate_challenges.py`、`methods/reviewer_validation/scripts/run_anchor.py`、`methods/reviewer_validation/scripts/score_anchor.py`、`methods/reviewer_validation/tests/test_anchor_evaluation.py`、`methods/reviewer_validation/outputs/pilot/anchor/**`。
- **受门控的正式输出**：仅在协调者提供 40 个已复核源锚点及固定 seed 后，D 才可首次写入 `methods/reviewer_validation/challenges/anchor_cases.jsonl` 与 `methods/reviewer_validation/challenges/anchor_texts/**`；已有目标一律拒绝覆盖。只有 strict PASS 后，formal runner 才可写 `methods/reviewer_validation/outputs/formal/anchor/**`。源锚点清单、protocol、schemas、verifier、freeze manifest 及 detached hashes 不归 D 修改，由协调者在 handback 后登记与冻结。
- `generate_challenges.py` 本包只实现 `anchor` 子命令；不得顺手实现 80 项 Promise status challenge。不得改 Anchor 的三态契约、另写替代 `relocate` 的评测算法、查看 held-out 结果调阈值，或把 development probes 混入正式分母。

### Development-only 已知 probes

以下固定示例只用于回归和 pilot，不得复制、释义或变形后进入 40 个正式源锚点：

1. **重复 exact quote**：原文 `Alpha target Beta. Gamma target Delta.` 的源锚点指向第二个 `target`；新文为 `Prelude. Alpha target Beta. Gamma target Delta.`。PASS 要求 `status=anchored` 且 span 精确指向上下文一致的第二个 occurrence；当前实现实际指向第一个 occurrence。
2. **删除目标 + 相似干扰项**：源 quote 为 `novel transformer architecture`，新文只保留 `This paper discusses a novel transfer architecture elsewhere.`。PASS 要求 `status=lost` 且两个位置均为 null；当前实现实际返回非空 `drifted`。

修复可以利用已保存上下文、原位置和 section 信息对所有 exact/fuzzy candidates 作确定性排序并设置拒绝条件，但阈值只能在 development probes 和隔离 pilot 上确定；必须同时保持纯函数、既有单一 occurrence 行为、上下文更新和长文本运行约束。

### 确定性挑战生成与 freeze 规则

1. 候选输入清单先锁定并计算 hash（此时不得宣称 G2），固定 40 个 `source_anchor_id`、不可变源文本 hash、quote/span/context 及分层标签。主要分层为 8 个 short quote、8 个 long quote、8 个 duplicated-exact-quote、8 个 heading/boundary（至少各 2 个标题附近、文首、文尾）和 8 个 similar-distractor；交叉标签保留，但每个源锚点只有一个 primary stratum。
2. 每个源锚点恰好产生 anchored、drifted、lost 各一项，合计 40 clusters、120 cases、三态各 40。anchored 的四种 operation 各 10；drifted 的 local rewrite/substitution/paraphrase 按固定 seed 分成 14/13/13；lost 全部删除目标并加入相似干扰项。
3. 正式 seed 只能从 `configs/seeds/anchor_challenge.txt` 读取；禁止 CLI 临时覆盖。相同源字节、生成器字节和 seed 必须逐字节生成相同 JSONL、transformed texts、逐项 `item_input_sha256` 与总 SHA-256；改变任一输入必须改变对应 hash。
4. 正式 120 项必须在任何正式 `relocate` 调用前生成、双人交叉核验，并连同源清单、生成器、seed、每份 transformed text 和输出 hash 逐项加入 `freeze_manifest.json`。随后再计算 detached manifest hash 并执行 strict verifier；正式 runner 只读已冻结 artifact，绝不边运行边生成、修复或覆盖 case。

### 指标与分析单位

- `state_macro_f1`、三态各类 Precision/Recall/F1 和混淆矩阵：全部 120 项。
- `correct_location_rate`：80 个 anchored/drifted 项中，预测 span 与 gold span 的半开区间 IoU `>= 0.50`；同时报告 mean span IoU 与零重叠数。
- `false_relocation_rate`：40 个 lost 项中，任一预测位置非空即计 1。
- `joint_status_location_accuracy`：全部 120 项中状态正确，且非 lost 位置达标或 lost 位置为空。
- 主要分析单位为 40 个 `source_anchor_id`；置信区间按源锚点聚类并使用 protocol 固定的 bootstrap seed/10,000 次，禁止把三个变体当作 120 个独立 cluster。

### 可证伪验收 gates

1. **D1 Production-regression PASS/FAIL**：既有 Anchor 测试保持通过；两个已知 probes 分别精确命中第二 occurrence 和 `lost + null span`；测试证明修复仍直接调用 production `relocate`，无评测专用分支。
2. **D2 Candidate/rejection PASS/FAIL**：测试覆盖多个 exact/fuzzy candidate 的确定性排序、tie-break 与拒绝；候选次序变化不得使同一上下文锚点漂到无关重复项，相似度不足或上下文冲突必须返回 lost。
3. **D3 Generator determinism PASS/FAIL**：同一 development source+seed 连续两次生成的文件树与 SHA-256 完全相同；一个输入字节变化触发 hash 变化；输出严格为 40×3 时才允许 formal staging，case ID、cluster、状态、operation 配额和 schema 均逐项验证。
4. **D4 Metrics correctness PASS/FAIL**：手算 fixture 的 state Macro-F1、IoU、correct-location、false-relocation、joint accuracy 与 scorer 完全一致；零分母报告 NA+count，lost 的非空 span 无论状态为何都计 false relocation。
5. **D5 Runtime pilot PASS/FAIL**：隔离 development CLI 必须实际生成、运行并复算一组非正式 cases；PASS 同时要求两个已知 probes 通过、runner predictions 与独立 scorer 指标逐字节一致、无输入被覆盖、无 secret/path escape。任一条件失败即停止，保留失败 artifact，禁止生成正式 120 项。
6. **D6 Formal fail-closed PASS/FAIL**：`run_anchor.py --mode formal` 在 strict verifier BLOCKED 时必须在首次读取 case 或调用 `relocate` 前非零退出；只有 strict PASS 后才可运行，且 runner 对 120 条冻结记录只读并把首次输出 hash 追加到 run manifest。

### 获准的 pytest 与 CLI 命令

在 `python/` 下运行；前三组用于实现与 development pilot：

```powershell
python -m pytest tests/unit/test_anchor.py -q
python -m pytest ../methods/reviewer_validation/tests/test_anchor_evaluation.py -q
python -m pytest ../methods/reviewer_validation/tests/test_protocol_scaffold.py -q
python ../methods/reviewer_validation/scripts/generate_challenges.py anchor --mode dev --sources ../methods/reviewer_validation/outputs/pilot/anchor/dev_sources.jsonl --seed-file ../methods/reviewer_validation/outputs/pilot/anchor/dev_seed.txt --output-dir ../methods/reviewer_validation/outputs/pilot/anchor/generated
python ../methods/reviewer_validation/scripts/run_anchor.py --mode dev --cases ../methods/reviewer_validation/outputs/pilot/anchor/generated/anchor_cases.jsonl --output-dir ../methods/reviewer_validation/outputs/pilot/anchor/run
python ../methods/reviewer_validation/scripts/score_anchor.py --cases ../methods/reviewer_validation/outputs/pilot/anchor/generated/anchor_cases.jsonl --predictions ../methods/reviewer_validation/outputs/pilot/anchor/run/predictions.jsonl --output ../methods/reviewer_validation/outputs/pilot/anchor/run/metrics.recomputed.json
python ../methods/reviewer_validation/scripts/verify_freeze.py --allow-draft
python ../methods/reviewer_validation/scripts/run_anchor.py --mode formal --cases ../methods/reviewer_validation/challenges/anchor_cases.jsonl --output-dir ../methods/reviewer_validation/outputs/formal/anchor
```

末条在 G2 BLOCKED 时**必须非零退出**，是 D6 的负向 gate，不是授权正式运行。下列正式生成命令只有在 D1–D5 PASS、协调者书面确认源清单与 seed 后才获准；它必须在 strict freeze 前运行，且不得调用 `relocate`：

```powershell
python ../methods/reviewer_validation/scripts/generate_challenges.py anchor --mode formal --sources ../methods/reviewer_validation/challenges/anchor_sources.jsonl --seed-file ../methods/reviewer_validation/configs/seeds/anchor_challenge.txt --output-dir ../methods/reviewer_validation/challenges
```

生成后立即停止并交由协调者更新 manifest/hashes、执行 strict verifier；D 不得自行把 protocol 改成 frozen，也不得接着运行 formal runner。

## 7. 工作包 E：七 venue 官方指南来源审计（仅证据收集）

### Premise

RQ3 的真实比较对象是“对当前官方审稿标准的遵循度”，而 `python/src/argument/venue_profiles.yaml` 目前只是手写描述；在逐句建立官方来源映射之前，任何 profile 改写、冻结或正式 A/B 运行都缺少可审计依据。Work E 只收集和核验来源，不修改 `METHODOLOGY.md`、`venue_profiles.yaml`、protocol、manifest 或任何 detached hash。

### 三个互斥 research packets

三个 packet 可以并行，但 venue、检索范围和写入文件严格互斥；作者只能编辑自己的一份文件，不得替其他 packet 补项或修改其结论。

| Packet | 唯一 venue 范围 | 唯一输出文件 |
|---|---|---|
| E-P1 | NeurIPS、ICML、ICLR | `methods/reviewer_validation/sources/packet_1_neurips_icml_iclr.md` |
| E-P2 | ACL、CVPR | `methods/reviewer_validation/sources/packet_2_acl_cvpr.md` |
| E-P3 | KDD、CHI | `methods/reviewer_validation/sources/packet_3_kdd_chi.md` |

- 每个 venue 只能出现在所属 packet；`generic` 不属于七 venue 官方来源审计，本包保持其文本不变。
- 只允许使用检索当日仍由目标 venue、会议或其主办专业组织控制的官方域名页面/PDF。博客、百科、实验室或个人网页、第三方总结、搜索结果摘要和非官方镜像均不得作为支持证据。
- 同一 URL 不得跨 packet 重复。若发现跨 venue 通用政策页，只在最先发现它的 packet 的 `cross_packet_escalation` 中登记，不据此写 proposed sentence；由后续 synthesis 统一裁决归属。
- 不确定某域名、页面版本或适用年份是否官方时，不得推定；以 `SOURCE_UNCERTAIN` 显式记录并说明缺口。

### 每条来源与标准的必填字段

每份 packet 对所属 venue 逐条覆盖当前 YAML 的全部句子和列举项，并为每个候选官方标准记录：

1. `venue`、稳定的 `source_id`、页面标题、规范 URL、URL host、官方性依据。
2. 页面/PDF 标示的 publication/update year 与适用会议年份；未标示时写 `not_stated`，不得猜测。
3. 按实际检索日记录 access date；不得预填计划日期。
4. 来源内定位信息，以及不超过 25 个词、且同一来源累计不超过 25 个词的 verbatim criterion；其余内容必须释义，不能拼接长引文。
5. 可独立评分的 paraphrased criterion；不得加入来源没有表达的权重、强度、venue 指纹或强制关键词。
6. applicability/conditionality：记录适用对象、触发条件、例外和来源是否明确使用条件语气；无条件性证据时不得自行发明。
7. 与当前 `venue_profiles.yaml` 对应句子或列举项的显式比较，状态限定为 `supported`、`partially_supported`、`unsupported`、`conditionality_missing` 或 `source_uncertain`。
8. 建议动作限定为 `keep`、`rewrite_conditionally` 或 `remove`，并列出 proposed profile sentence 及其全部 `source_id`；`source_uncertain` 不得支持 `keep`。

### 可证伪验收 gates

1. **E1 Scope/domain PASS/FAIL**：七个 venue 恰好各出现一次且归属正确；每个支持性 URL 均通过官方域名检查，无博客、聚合页或非官方镜像；跨 packet URL 重复数为 0。
2. **E2 Field completeness PASS/FAIL**：每条来源均有标题、URL、publication/year、access date、短引文、释义、适用性/条件性与不确定性字段；缺失信息以显式状态表示，而非空白或猜测。
3. **E3 Current-YAML audit PASS/FAIL**：七个现有 profile 的每个句子和列举项都恰好得到一次比较判定；不得只收集“看起来正确”的标准而遗漏现有断言。
4. **E4 Sentence traceability PASS/FAIL**：每个 proposed profile sentence 至少映射到一个通过 E1 的官方 `source_id`；合并多个标准的句子必须映射全部组成来源。
5. **E5 Unsupported/uncertain handling PASS/FAIL**：无官方证据的断言只允许 `remove`，不得用博客或常识补证；部分支持或条件性缺失只允许缩窄为来源实际支持的条件性表述；所有来源不确定性在 packet 和 handback 中可见。
6. **E6 Copyright/scope PASS/FAIL**：短引文满足上述单来源上限，全文以释义和定位信息为主；packet 不含整页复制、未授权附件、凭据、私密路径或正式输入 hash。

### Capped packet handback

每个 packet 完成后只交回一次，最多 **500 中文字或 8 个 bullets**，并严格包含：唯一输出文件；各 venue 的官方来源数与 proposed sentence 数；当前 YAML 的 `supported/partial/unsupported/uncertain` 计数；建议删除或条件化的句子 ID；重复 URL 检查结果；版权检查结果；仍未解决的来源不确定性；明确停止点。packet 正文可包含完整审计表，但 handback 不得粘贴长引文或搜索过程，也不得顺手修改 YAML、criteria 文件或 freeze artifacts。

### 后续独立 synthesis/review（不得与 packet 并行完成）

1. 三个 packet 全部 handback 后，由未参与任一 packet 编写的 synthesizer 只读合并，输出 `methods/reviewer_validation/sources/synthesis_review.md`；它必须建立“现有 YAML 句子 → 官方来源 → 释义标准 → proposed sentence → keep/rewrite/remove”的全量追踪矩阵，统一重复概念与条件性，但不得修改 YAML。
2. 再由未参与 packet 编写且未担任 synthesizer 的 reviewer 独立复核全部 URL、官方性、年份、短引文、释义忠实度、条件性和逐句映射；抽样复核不够，任何一条失败都使 Work E 保持 BLOCKED。
3. 只有 synthesis/review 双方签署 PASS，协调者才可在新的串行工作项中据矩阵提出 `venue_profiles.yaml` 修改，并生成 `criteria/official_sources.json` 与 `criteria/criterion_map.json`；未支持内容直接删除，不从非官方材料补齐。
4. 这些被接受的来源、映射和最终 profile 随后才进入正常 G2 freeze 流程。Work E 当前不得修改 `METHODOLOGY.md`、`protocol.sha256`、`freeze_manifest.json` 或 `freeze_manifest.sha256`，也不得宣称 profile 已冻结或 RQ3 已获验证。

## 8. 集成顺序与停止条件

1. C1–C6、A1–A6、B1–B6 与 D1–D6 的开发态基础设施 handback 均已完成；独立 capstone 复核也仅在该范围内 PASS。
2. 现有 synthetic/development artifacts 与非完美指标保持原样；不得清洗、替换或纳入正式分母。
3. Work E 已在纠正首轮 FAIL 项后经独立全量复审 PASS；Work F 已在纠正首轮 REVISE 的 runner 截断与 source 顺序问题后经独立全量复审 PASS。两者只完成官方来源追溯和 pre-pilot profile 应用，没有生成研究效果证据。
4. 下一执行边界是由两名研究者完成真实 development 输出的人工 pilot 审计；在完成并签署前 G1 保持 BLOCKED。
5. 40 个正式源锚点、fixed seed、双人核验的 120 项 cases，以及其余正式语料、gold、mapping、模型、已验收官方来源映射与配置全部进入 manifest 并通过 strict verifier 后，G2 才可重新判定。
6. 外部单模型成对运行证明 canonical requests 只改变 profile，且无 fallback 后，G4 才可重新判定；G0–G4 全部通过前不得读取 held-out 或启动 formal runner。

## 9. Capped handback contract

每个工作包只允许一次主 handback，最多 **500 中文字或 8 个 bullets**，并严格包含：修改文件清单；实际运行的获准命令与逐条结果；本包 gates 的 PASS/FAIL 表；pilot artifact 相对路径及 hashes；关键 runtime 观察；与 canonical protocol 的任何偏差；未解决风险；明确停止点。D 的 handback 还必须给出两个已知 probe 的 expected/actual status 与 span、两次 development 生成的总 hash，以及 formal cases 是否生成；不得粘贴大段日志、用全量测试数替代本包证据或顺手实施其他工作包。A/B/C 不得越权实施 Anchor，D 不得越过其 development/formal-generation gates。达到上限或发现 blocker 时立即停止并交回协调者。

## 10. Work Item F：应用官方来源约束的 venue-conditioned profiles 与评分标准映射（顺序执行）

### 执行状态（2026-08-30）

- F-I 已完成 20-source/35-criterion 机器可读映射、七个 source-grounded profile、完整 profile 生产消费和描述性公开文案。
- F-R 首轮判定 REVISE：`run_venue_ab.py` 仍在 canonical request 构造/比较中截断长 profile，CHI-Y4 的 source 顺序在 synthesis 与 criterion map 之间不一致。
- 窄范围 remediation 后，F-R 对 20 sources、35 criteria、YAML/map 一一对应、generic hash、长 NeurIPS full-profile mock pair、banned claims、focused tests 与 freeze 状态完成全量复核并最终 PASS。
- 该 PASS 不更改研究 gate：未运行真实模型、held-out 或 formal data，G1/G2/G4 仍为 BLOCKED，不得提出 RQ3 效果结论。

### Premise 与硬依赖

RQ3 的处理文本与评分标准必须来自同一套、可逐项追溯的官方标准。Work E 已形成三个 packet 和 `sources/synthesis_review.md`：20 个官方 `source_id`、20 个唯一 URL、42 个旧 YAML atom 全覆盖，以及 35 个获准的 replacement sentence（NeurIPS 6、ICML 5、ICLR 3、ACL 5、CVPR 4、KDD 6、CHI 6）；七个 unsupported atom 没有 replacement，`generic` 明确保持不变。Work F 只把这份已复核矩阵应用到生产 profile、机器可读评分标准和当前公开文案，不增加新标准，也不生成效果证据。

- **硬依赖**：协调者已记录 Work E 的三个 packet E1–E6 全部 PASS，且 synthesis 与独立全文复核均 PASS。若 20/20/42/35 任一计数、任一 source ID、URL 官方性、条件性或 replacement sentence 仍有争议，F 立即停止并把问题退回 Work E；F 实现者不得自行补证据、浏览后改写标准或扩大来源含义。
- **研究 gate 不变**：F 只产生 pre-pilot candidate inputs。它不通过 G1，不冻结 G2，也不通过需要真实单模型成对调用的 G4；不得把“source-grounded”写成“已证明改善标准遵循度”。
- **关键消费约束**：当前 `run_review` 的 focused/document prompt 分别使用 `venue_profile[:400]` 与 `venue_profile[:600]`。35 个获准句子写入 YAML 后会超过这些边界；F 必须让两个生产 prompt 使用完整已加载 profile，并用首句、末句同时出现的测试证明没有静默截断。不得以缩写、删句或另建实验专用 prompt 绕过此问题。

### 串行角色与精确所有权

F 分成 **F-I Implementation** 与 **F-R Independent review**，必须串行执行且由不同执行者承担。F-I 完成、停止并交回后，协调者才可启动 F-R；F-R 不得边审边改。

**F-I 唯一可编辑文件：**

- 生产 profile 与消费路径：`python/src/argument/venue_profiles.yaml`、`python/src/argument/reviewer.py`、`python/tests/unit/test_reviewer.py`。
- 机器可读来源与标准：`methods/reviewer_validation/criteria/official_sources.json`、`methods/reviewer_validation/criteria/criterion_map.json`、`methods/reviewer_validation/schemas/official_sources.schema.json`、`methods/reviewer_validation/schemas/criterion_map.schema.json`、`methods/reviewer_validation/tests/test_venue_profiles_grounding.py`。
- 当前公开主张：`README.md`、`README_zh.md`。

**F-R 唯一可写文件：** `methods/reviewer_validation/sources/profile_application_review.md`。除该报告外，F-R 对 F-I 输出、Work E packet、synthesis、protocol 和生产代码全部只读。若 F-R 判 FAIL，由协调者另派窄范围 remediation；原实现者不得自签 PASS。

**本包明确只读或禁止修改：** `METHODOLOGY.md`、三个 Work E packet、`sources/synthesis_review.md`、`methods/reviewer_validation/protocol.yaml`、`protocol.sha256`、`freeze_manifest.json`、`freeze_manifest.sha256`、`scripts/verify_freeze.py`、`scripts/run_venue_ab.py`、既有 pilot/formal outputs 与 `CHANGELOG.md`。历史 changelog 中的旧 `conference-calibrated` 记录保留，不得重写历史。当前扫描未发现其他 live `docs/**` 主张；若实施时出现新的 tracked live surface，停止并向协调者申请扩展所有权。

### F-I 实施契约

#### 1. Profile 文本与 generic control

1. `venue_profiles.yaml` 的 key 必须恰为 `generic`、`NeurIPS`、`ICML`、`ICLR`、`ACL`、`CVPR`、`KDD`、`CHI`，大小写与顺序保持现状，不得增加 alias、权重、关键词、venue 指纹或隐藏指令。
2. 七个非 generic 值只能按 `synthesis_review.md` 第 3 节逐字采用 35 个获准句子；每句独占一个逻辑行且顺序不变。不得保留七个已删除 atom，也不得把 source ID、URL、审计结论或未获准说明注入模型文本。
3. `generic: |` 起始到 `NeurIPS: |` 前一字节的规范 UTF-8/LF 原始块必须 byte-equivalent；基线为 219 bytes，SHA-256 `30fd129da348e52128cfceab4844b54dedb7abdb39c9fe217251bc29fb60619a`。解析后的 generic 值、unknown-venue 的 `Venue: <name>. ` 前缀行为以及 `None` fallback 同样保持不变。
4. YAML 顶部注释和 loader docstring 改为 `source-grounded`、`manually curated`、`venue-conditioned` 等描述性措辞；不得再称 calibration、review culture 或 hard requirements。

#### 2. 机器可读来源与 criterion 映射

`official_sources.json` 与 `criterion_map.json` 均使用顶层七 venue record 数组，以便与现有 freeze scaffold 的 venue 粒度一致；新增 schema 必须拒绝额外字段、重复 ID、空 source reference 和未知枚举。

- `official_sources.json`：七个 venue record 合计恰含 Work E 的 20 个 source record。每个 source 至少含 `source_id`、`venue`、`title`、`canonical_url`、`official_host`、`officiality_basis`、`publication_or_update`、`applicable_conference_year`、`access_date`、`locator`、`source_packet` 和 `snapshot`。`snapshot.path/sha256` 若尚未采集必须显式为 null 且 `status=pending_g2`，不得伪造；其未冻结状态由后续 G2 处理。
- `criterion_map.json`：七个 venue record 合计恰含 35 个 criterion；每个 criterion 至少含稳定的 `criterion_id`、原 `profile_atom_id`、`rater_order`、与 YAML 逐字相同的 `profile_sentence`/`rater_text`、非空 `source_ids`、`decision`，以及 `applicability`。
- `applicability` 必须机器可读地区分 `universal` 与 `conditional`，并含 `applies_when`、`not_applicable_when`、`exceptions`、`rater_instruction`、`excerpt_insufficient_default=applicable`。条件只能来自 Work E，不得由实现者根据常识补写；KDD 必须保留 Research/ADS track 边界，CHI 必须保留 contribution-type 边界，其余 claim/method/data/human-subject 条件也不得丢失。
- 全部 35 个 criterion 的 `source_ids` 必须存在于 20-source 集合且 venue 一致；全部 YAML 句子与 criterion 一一对应、顺序相同，无孤立 source reference、无 source-less criterion。后续盲评才把稳定 ID 投影为 paper 内 `C1...CK`；本包不创建 paper applicability gold 或盲化包。

#### 3. 生产消费与公开措辞

- `_load_venue_profile`、case-insensitive lookup、explicit override、unknown/None fallback 和 SSE/API 契约保持不变；只更新不准确的 calibration wording，并消除两个 profile slice，使 focused 与 document LLM prompt 都包含完整 profile。测试必须断言每个 venue 的第一条和最后一条 criterion 均进入实际 mock LLM prompt。
- README 的三处 live 主张改为“manually curated, zero-shot venue-conditioned profiles/reviews”及等义中文；只能描述配置来源与机制，不得声称已校准、复现真人风格、提高准确率或通过 RQ3。
- 以下 active-surface 字符串必须为零命中：`conference-calibrated`、`calibrated reviews`、`会议校准`、`venue calibration profiles`、`calibration text`、`review culture and hard requirements`。扫描范围只含 `README.md`、`README_zh.md`、`python/src/argument/reviewer.py`、`python/src/argument/venue_profiles.yaml`；方法文档中的否定性审计说明和未修改的 `CHANGELOG.md` 不属于 live claim。
- 七个被移除的旧 atom 的完整短语不得出现在 active profile 或 `criterion_map.json`：ICML 多数据集普遍要求；ICLR 代码强制、完整消融、既往投稿意见；ACL 普遍人工评测；CVPR 普遍组件消融与指定 ImageNet/COCO benchmark。

### 可证伪验收 gates

1. **F1 Work-E lineage PASS/FAIL**：三个 packet 与 synthesis hash 被记录；20 source IDs、20 unique URLs、42 audited atoms、35 replacements、七 venue 计数和七个 remove 决策与 synthesis 完全一致。任何新增、缺失或改写均 FAIL。
2. **F2 YAML/generic exactness PASS/FAIL**：PyYAML 加载成功且 key 集合/顺序精确；七 profile 的逻辑行数为 6/5/3/5/4/6/6，总计 35，并逐字等于 criterion map；generic 规范 UTF-8/LF 原始块为 219 bytes 和上述 SHA-256。
3. **F3 Source/criterion integrity PASS/FAIL**：两个 JSON 均通过新增 schema；七 venue、20 sources、35 criteria、source-ID 外键、venue 归属、URL 唯一性、official host、rater order 与 applicability 字段全部通过；null snapshot 明确标为 `pending_g2`，不得被算作冻结证据。
4. **F4 Production consumption PASS/FAIL**：现有 loader/fallback/override 测试通过；focused 与 document mock 调用均收到完整 profile，最后一条 criterion 可见，且 profile 之外的 prompt、SSE、provider 和 ReviewSession 行为无变化。源码不得残留 profile 的 400/600 字符静默截断。
5. **F5 Claim hygiene PASS/FAIL**：四个 active surfaces 对六个 banned claim 字符串零命中，七个 unsupported 旧 atom 不在 active profile/map；README 只使用描述性、未验证措辞；`git diff -- CHANGELOG.md` 为空。
6. **F6 Offline regression/safety PASS/FAIL**：所有获准 pytest 通过且只使用 mock/静态 fixture；无网络、无真实 LLM、无 held-out、无新增 pilot/formal output、无 secret 或私密路径进入 JSON、测试或日志。
7. **F7 Freeze remains blocked PASS/FAIL**：draft verifier 返回 0 但明确 `FORMAL_RUN: BLOCKED`；strict verifier 必须非零退出。protocol/manifest/status、detached hashes、profile snapshot 和 `formal_run_authorized=false` 不得由 F 修改；`official_sources`/`criterion_map` 的 hash、snapshot 和 manifest 登记留给后续 G1 人工 pilot 与 G2 freeze。
8. **F8 Independent review PASS/FAIL**：F-R 逐项复核而非抽样复核 20 sources、35 criteria、YAML 一一对应、generic hash、完整 prompt 消费、banned claims、测试输出与 freeze 状态，并在唯一 review report 中签署各 gate。F-R 未 PASS 前，Work F 保持 BLOCKED。

### 获准的离线命令

在 `python/` 下运行；所有 LLM 路径必须由 mock 驱动：

```powershell
python -m pytest tests/unit/test_reviewer.py -q
python -m pytest ../methods/reviewer_validation/tests/test_venue_profiles_grounding.py -q
python -m pytest ../methods/reviewer_validation/tests/test_venue_isolation.py -q
python -m pytest ../methods/reviewer_validation/tests/test_protocol_scaffold.py -q
python ../methods/reviewer_validation/scripts/verify_freeze.py --allow-draft
python ../methods/reviewer_validation/scripts/verify_freeze.py
```

最后一条必须非零退出并显示 `FORMAL_RUN: BLOCKED`；这是一项负向 gate，不是待修复失败。回到仓库根目录后只允许以下只读检查：

```powershell
git diff --check -- README.md README_zh.md python/src/argument/reviewer.py python/src/argument/venue_profiles.yaml python/tests/unit/test_reviewer.py methods/reviewer_validation/criteria methods/reviewer_validation/schemas methods/reviewer_validation/tests/test_venue_profiles_grounding.py
git grep -n -I -i -E 'conference-calibrated|calibrated reviews|会议校准|venue calibration profiles|calibration text|review culture and hard requirements' -- README.md README_zh.md python/src/argument/reviewer.py python/src/argument/venue_profiles.yaml
git diff -- CHANGELOG.md
```

本包不获准调用 `run_venue_ab.py`、任何 provider/client、浏览器、网络 API、held-out reader 或 formal runner，也不获准写 `outputs/pilot/**`、`outputs/formal/**`、annotations、snapshots、manifest 或 detached hash。

### 两阶段 capped handback 与停止点

- **F-I handback**：最多 500 中文字或 8 bullets，只含修改文件、35/20/7 数量、generic block hash、获准命令逐条结果、F1–F7 表、profile 首末句消费证据、strict BLOCKED 输出摘要、偏差/风险和停止点；不得粘贴 35 句全文或大段测试日志。
- **F-R handback**：最多 500 中文字或 8 bullets，只含唯一 review report、逐项复核范围、F1–F8 判定、发现的问题、是否需要 remediation，以及明确停止点。PASS 只表示 source-grounded profile 与评分映射已正确应用；它不表示 G1/G2/G4 PASS，也不支持任何 RQ3 效果主张。
- 明确停止点：F-R PASS 后交回协调者；下一步只能是用真实 development 输出进行 G1 人工 pilot、根据 pilot 完善待冻结输入并在后续独立步骤执行 G2。G1/G2 未通过前不得读取 held-out 或运行正式 A/B；本包全程不得进行真实模型调用。
