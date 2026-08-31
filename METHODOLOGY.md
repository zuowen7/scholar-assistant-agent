# Reviewer Validation Methodology

结论：本研究只验证 Scholar Assistant 当前技术主张，不在两周内用便利样本替代教育效果研究；正式实验必须在冻结语料、提示词、模型和评价规则后，分别回答 Ledger、Anchor 与 venue profile 三个研究问题。

## 0. 文档地位与执行边界

本文档是审稿意见验证工作的唯一方法总纲。研究问题、样本、指标、分析单位、冻结规则与结论门槛以本文档为准；技术实现、命令和运行记录统一放在 methods/reviewer_validation/。

- 基线：main@099b69c。
- 当前阶段：方案冻结前的文档阶段，尚无实验结果。
- 团队：两名研究者，记为 A 与 B。
- 周期：14 个自然日。
- 范围：技术验证，不测量学习增益、写作能力提升、满意度或教育效果。
- 禁止：看见正式测试结果后换主指标、改阈值、换模型、改 profile、删除失败运行或把负面主结果移出正文。

如果后续要研究教育效果，必须另立研究问题、样本量依据、任务、前后测、伦理与数据保护方案；不得把本研究中的两名作者标注活动称为用户研究。

## 1. 研究问题与可支持主张

| 研究问题 | 主要估计对象 | 达标后允许的主张 | 未达标时的表述 |
|---|---|---|---|
| RQ1：Ledger 对 Promise 的提取、类型识别和兑付状态分类有多准确？ | 10 篇 held-out 论文上的提取 F1、四类状态 Macro-F1、证据命中率及端到端正确率 | 在指定语料、生产 excerpt、冻结模型和提示词下达到报告值 | 当前证据未证明可靠提取或分类；报告错误类型与限制 |
| RQ2：三态锚点在文本编辑后能否正确判断并重定位？ | 40 个源锚点的 120 个受控变体上的状态 Macro-F1、联合定位正确率与错误重定位率 | 在冻结挑战集上达到报告值 | 当前算法在相应变换上仍不可靠；不得泛化为稳健重定位 |
| RQ3：相对于同名 venue 的 generic profile，venue-conditioned profile 是否提高对当前官方审稿标准的遵循度，且不增加无依据批评？ | 14 篇论文上的配对遵循度差异和无依据批评率差异 | profile 对当前公开标准的遵循度有增益，且满足预注册安全门槛 | 未证明增益、未证明不劣，或结果不确定；不得声称风格校准 |

RQ3 只估计 profile 文本的增量作用。两种条件中的 venue 名称保持相同，因此不回答“模型能否猜出会议风格”，也不回答“输出能否模仿真人审稿人”。

## 2. 当前代码证据与不可绕过的约束

| 代码证据 | 当前事实 | 方法约束 |
|---|---|---|
| python/src/argument/companion_models.py | PromiseStatus 类型包含 paid、partial、unpaid、mismatch、unknown | 仅前四项是实质状态；unknown 作为解析失败或缺失结果的兜底，单独报告 |
| python/src/argument/ledger.py | build_ledger 先提取 Promise，再在同一生产流程中分类兑付状态；提取区与正文区均经过生产 excerpt 构造 | 评测实现需要暴露两个可独立调用的阶段，但不得改写生产 prompt、excerpt 或解析语义 |
| python/src/argument/ledger.py | 分类 prompt 只允许四个实质状态，其他值被映射为 unknown | 四类状态 Macro-F1 与 unknown rate 分开，禁止把 unknown 当作第五个语义类别 |
| python/src/argument/section_utils.py | 生产评审使用有长度上限和覆盖元数据的 SectionExcerpt | 模型、人工核验和证据判定均以模型实际看到的 production excerpt 为边界，不得用完整论文替模型补证据 |
| python/src/argument/anchor.py | Anchor 的状态是 anchored、drifted、lost；relocate 依次采用精确匹配、上下文和模糊匹配 | 同时评价状态和位置；lost 被错误定位必须计入 false relocation |
| python/src/argument/venue_profiles.yaml | 七个 venue profile 是手写 YAML 文本 | 现有文本不是校准证据；每条正式标准必须在冻结前映射到当前官方来源 |
| python/src/argument/reviewer.py | run_review 同时把 venue 名称和加载后的 profile 注入 prompt，并默认混合多类检查 | RQ3 中 venue 名称恒定，只替换 profile；仅串行运行 checks=["llm"] |
| python/src/argument/llm_client.py | 当前共享客户端按 Cloud、Ollama、空字符串降级 | 正式实验使用单一 provider/model，禁用跨 provider 静默回退；失败与空响应保留为结果 |
| README.md | 当前公开文案使用 conference-calibrated | 在结果支持前改为 manually curated, zero-shot venue-conditioned profiles；不得预写成功结论 |

模型与 provider 在 pilot 后冻结。记录 provider 名称、精确 model ID、模型快照或版本（如可得）、API 格式、temperature、max_tokens、thinking mode、seed（如支持）、运行时间、代码 commit、prompt hash、profile hash 和 excerpt hash。任何 API key、认证头或本地私密配置不得进入记录。

生产内已有的同 provider 格式修复重试可以保留，但每次尝试都必须记录；不得在失败后改用其他 provider/model，也不得用补跑替换失败样本。

## 3. 审稿意见覆盖矩阵

| 审稿关切 | 方法决策 | 可观察产物 | 判定方式 |
|---|---|---|---|
| 缺少真实用户研究，教育效果证据不足 | 选择审稿意见允许的技术验证边界，不仓促开展低效力用户研究 | 论文 scope/limitations 修改、逐点回复、主张审计表 | 全文不得把技术正确性外推为学习、写作或教学效果 |
| Promise–Discharge 无 gold-standard 准确率 | 执行 RQ1 的双人独立标注、自然语料与受控挑战集评测 | 两份不可变原始标注、仲裁 gold、运行日志、指标表、混淆矩阵 | 报告提取、类型、状态、证据和端到端指标 |
| 七 venue profile 无校准方法与 fidelity 验证 | 把问题改为当前官方标准遵循度，执行盲化配对 RQ3 | 官方标准快照与映射表、84 份原始输出、42 个盲化 A/B 包、双人评分 | 只按预注册遵循度与无依据批评门槛下结论 |
| 三态锚点稳健性缺少直接证据 | 执行 RQ2 的配对受控变换 | 40 个源锚点、120 个变体、预期位置与状态、结果表 | 同时报告状态、位置和错误重定位 |

## 4. 预注册、pilot 与冻结

正式 held-out 运行前，在 `methods/reviewer_validation/protocol.yaml` 固定以下内容：

1. 本文三个 RQ、主要指标、次要指标和主张门槛。
2. 16 篇论文的 manifest、纳入排除规则、development 目的抽样理由、held-out 抽样 seed、文件 hash、分组，以及每个 production excerpt 的坐标映射 hash。
3. 两名标注者的 codebook、span 匹配规则、状态规则、criterion applicability 规则和 venue 评分规则。
4. 单一 provider/model、生成参数、prompt/profile/excerpt 构造版本。
5. 运行次数、执行顺序、A/B 随机化 seed、失败与重试规则。
6. 统计脚本版本、bootstrap 次数、分析单位和不劣界值。
7. 代码 commit 与 `protocol.sha256`；`freeze_manifest.json` 引用该 protocol hash，另由 detached `freeze_manifest.sha256` 记录 manifest 自身 hash，避免循环引用。

`freeze_manifest.json` 是正式运行的唯一输入清单，至少逐项记录 corpus、解析全文、production excerpts、坐标映射、A/B 两份原始标注、仲裁 gold、官方标准快照与映射、80 项状态挑战集、120 项锚点挑战集、prompt/profile、schemas、生成脚本、seed 和运行配置的相对路径、SHA-256、生成时间及 protocol 版本。所有正式挑战项必须由冻结脚本按记录的 seed 生成、交叉核验并在任何正式模型或 Anchor 运行前进入该清单；正式运行当天只读取，不得生成或改写测试项。

只有 `protocol.yaml`、`freeze_manifest.json` 及其引用的每个正式输入都通过 hash 复核，G2 才通过。运行输出不可能预先进入 freeze；其首次落盘 hash 追加到只写的 `run_manifest.jsonl`，不得覆盖。pilot 输入、pilot 输出和 development 样本使用独立目录与 manifest，绝不进入正式分母。

### 4.1 Pilot

仅使用 2 篇 development 论文和不进入正式集的锚点样本。两人必须查看真实 production excerpt、完整请求、原始响应、解析结果和评分包，检查：

在 G1 之前先完成一次独立的开发态模型筛选：固定两篇已选 development 论文，对 `deepseek-v4-pro` 与 `deepseek-v4-flash` 分别运行 Ledger extraction 和 venue-conditioned Reviewer，各模型×论文×工作流重复 2 次，共 16 个逻辑调用。两模型均显式使用 thinking enabled、reasoning effort high、同一生产 prompt/excerpt/参数；实际出站请求在 HTTP 发送前校验，首请求除 model ID 外必须逐字节一致。A、B 分开完成 M1/M2 盲评并各自锁定文件 hash 后才解盲；pairwise wins 优先，unsupported-content 总分不得更差，完全平局时才以预先声明的用户偏好选择 Pro。该筛选只决定后续单模型 pilot 的候选模型，不计入 G1、正式分母或 RQ1–RQ3 结果；筛选后仍须用所选单一模型重跑并完成人工 G1 审计。

- 两阶段 Ledger 的输入与生产路径一致，gold Promise 只在状态分类阶段注入。
- 单一 provider/model 生效，失败不会转入其他模型。
- RQ3 的成对请求除 profile 文本、profile hash 和随机化位置外完全一致；venue 标签、excerpt、模型参数和 checks=["llm"] 相同。
- 合法空数组、空响应、无效 JSON、超时和 provider 错误可区分。
- excerpt 的覆盖与截断元数据被保存，人工评分不越过模型可见内容。
- 两名标注者能够按 codebook 独立完成同一 pilot；分歧能归因于明确规则缺口。
- production excerpt 到 immutable full text 的双坐标映射可往返校验，重复文本不会改变 gold 坐标。
- 正式挑战生成器在同 seed 下逐字节复现同一输出和 hash；pilot 只能使用不同 seed 和隔离样本。
- 日志、配置和产物不含密钥、认证头、私人草稿或未授权全文。

pilot 是否通过必须依赖上述人工审计，不得以“脚本无报错”或聚合指标看似合理代替。pilot 可用于修正实现与 codebook；一旦冻结，2 篇 development 论文永不进入正式分析。

### 4.2 冻结后的变更

- 拼写或展示错误只能通过带时间、原因、影响范围和签名的 amendment 记录修正。
- 影响 prompt、profile、语料、标签、阈值、模型、解析或指标的错误必须暂停正式实验、升级 protocol 版本，并从头重跑所有受影响条件。
- 不得只重跑表现差的样本。
- 正式输出首次解盲后，不再允许改变主要分析。
- freeze 后发现任何正式挑战项是在正式运行期间生成，或任一正式输入不在 `freeze_manifest.json` 中，该轮运行整体无效；修复后必须从头执行所有受影响条件。

## 5. 主语料与抽样

### 5.1 16 篇 master corpus

- 2 篇 development：在看到任何模型输出前按最大差异目的抽样，覆盖不同研究范式、论证结构和 PDF 布局压力，仅用于 pipeline pilot、codebook 迭代、模型筛选和 profile 映射检查；不进入任何正式分母，也不据此作总体推断。
- 14 篇 held-out：七个目标 venue 各 2 篇，用于 RQ3。
- RQ1 从 14 篇 held-out 中预先选定 10 篇作为 Ledger 子集，按领域分层为 5 篇 AI/CS 与 5 篇 HCI、教育或交叉学科论文。

同一 master corpus 可服务不同 RQ，但一个 RQ 的正式样本不得用于该 RQ 的 prompt、阈值或 codebook 调优。

### 5.2 纳入与排除

纳入条件：

- 英文、开放获取、完整研究论文。
- 来自冻结时最新已完成的官方 proceedings 或可核验的正式版本。
- PDF 能被当前产品解析为非空文本，并能形成 production excerpt。
- 属于目标 venue 的常规 full paper 范围。

排除条件：

- 综述、教程、竞赛说明、数据集介绍短文、摘要-only、撤稿或重复版本。
- 解析后主要正文不可读。
- 团队成员参与创作，或已在 pilot 中看过模型输出。

development 论文可按预先写明的最大差异标准目的选择，因为其目标是尽早暴露 pipeline 与 codebook 缺陷，而非估计总体效果；选择理由、选择时间和“选择前未查看模型输出”必须进入独立 development manifest。正式 held-out 语料则必须先生成完整候选框，再按预注册 seed 分层抽样；不得按预期“容易发现问题”选择正式论文。manifest 至少记录 paper_id、venue、年份、官方 URL、许可状态、原文件 hash、解析文本 hash、excerpt hash、纳入排除原因和分组。若版权不允许再分发全文，仅发布元数据、hash 和获取说明。

### 5.3 数据层级

- 原始层：下载文件与首次解析文本，只读保存并校验 hash。
- 派生层：production excerpt、挑战变体、盲化评分包，可由原始层和脚本再生。
- 标签层：A、B 原始标签分别只追加；gold 是独立派生文件。
- 输出层：每次请求、响应、错误和元数据逐条保留。
- 结果层：只由冻结脚本从前述层生成。

原始文件、原始标签和冻结配置不可原地修改。

### 5.4 唯一坐标契约

所有 RQ1 gold 与 prediction 都以冻结解析得到的 immutable full text 为唯一计分坐标。字符区间统一采用 UTF-8 解码后的 Unicode 字符索引、0-based、左闭右开 `[char_start, char_end)`；换行与 Unicode 规范化在解析产物首次落盘前完成，之后不得再次规范化。full-text SHA-256 是坐标身份的一部分。

由于生产 excerpt 是从多个全文区段重构而成，每个 span 同时保存两套坐标：

- `full_text`: `text_hash`、`char_start`、`char_end`，是 exact/relaxed matching 与最终指标的唯一 gold 坐标。
- `excerpt`: `excerpt_id`、`excerpt_hash`、`char_start`、`char_end`，对应模型实际看到的精确序列化 excerpt。

`methods/reviewer_validation/mappings/<paper_id>.<excerpt_id>.map.json` 保存 piecewise excerpt-to-full-text 映射；每段包含 excerpt 半开区间、full-text 半开区间和 source section，重构分隔符标为 `synthetic` 且不可作为 gold span。mapping 自身及其两端文本的 hash 必须进入 `freeze_manifest.json`。每个 gold span 必须可通过 mapping 从 excerpt 坐标无歧义映射到同一 full-text 坐标；无法映射、跨 synthetic 区或在重复文本中坐标不唯一的项在冻结前修正或标为 `unresolved`，不得进入主要分母。

prediction 先在模型实际收到的 excerpt 中定位，再经同一 mapping 投影到 full text。无法定位的非空 prediction 保留为 unmappable false positive；不得在完整论文中另行搜索以替模型补全坐标。重复候选不按“第一次出现”裁决，而全部进入第 7.3 节的一对一匹配。

## 6. 双人标注协议

### 6.1 独立性与不可变性

1. A、B 先共同用 development 样本完善 codebook。
2. pilot 后先冻结 codebook；两人再独立标注全部正式样本，期间不讨论单项答案。两份 raw 与仲裁 gold 完成后才建立最终 G2 freeze manifest。
3. 提交后对各自文件计算 hash，原始文件转为只读。
4. 先计算未仲裁一致性，再查看分歧。
5. 仲裁结果写入新 gold 文件，不覆盖 A 或 B 的原始标签。
6. 任何未解决项保留 unresolved 标记，不得由统计脚本静默删除。

### 6.2 Ledger 标签

每条 Promise 至少包含 `promise_id`、`paper_id`、`exact_quote`、第 5.4 节定义的 full-text 与 promise-excerpt 双坐标、`kind`、`status`、`gold_evidence_spans`、`annotator_id` 和 `note`。`gold_evidence_spans` 是零项或多项数组；每项包含 `evidence_id`、`exact_quote`、full-text 与 body-excerpt 双坐标及对应 mapping hash。不得用一个拼接 quote 或包围多个离散证据的宽 span 代替多项数组。

`unpaid` 通常对应空证据数组；`paid`、`partial` 与 `mismatch` 原则上至少有一个可定位证据 span。若标注者认为状态可判但证据无法在模型可见 excerpt 中定位，必须标为 `unresolved` 并说明原因，不得填入虚构坐标。schema 校验必须拒绝越界坐标、quote 与坐标切片不一致、未知 mapping hash，以及落在 synthetic 映射段的 span。

kind 固定为 contribution、claim、hypothesis、gap_statement、scope。

四个实质状态的操作定义：

- paid：模型可见正文提供与 Promise 直接对应且足以完成该承诺的证据。
- partial：存在直接相关证据，但预先声明的范围、比较、场景或证明仅完成一部分。
- unpaid：模型可见正文未提供直接兑付证据。
- mismatch：模型可见证据与 Promise 冲突，或以关键限制改变了原承诺含义。

unknown 不由人工作为实质标签使用；它只统计系统无法给出合法四类结果的失败。

### 6.3 Venue 盲评标签

Venue 标注分成两个顺序固定且分别锁定的阶段；不得看到 review 后回改 criterion applicability。

**阶段一：applicability gold。** 对每篇论文的每条冻结官方标准，A、B 只查看匿名 paper ID、模型实际看到的 excerpt 与编号化标准文本，先独立标记：

- `applicable`：该标准适用于这类投稿，且能从模型可见 excerpt 对 review 是否检查该标准作出判断。
- `not_applicable`：官方标准本身是条件性的，而 excerpt 明确显示该条件不成立；“excerpt 信息不足”不得据此标为不适用，默认仍为 `applicable`。

两份 applicability 文件先计算未仲裁 Cohen kappa 并各自加 hash，再仲裁。分歧只能依据官方来源中的条件语句和 excerpt 定位说明裁决；若讨论后仍无共识，按保守规则记为 `applicable`，同时保留 `disputed=true`。因此每个 paper-criterion 在 gold 中必为二值之一，不存在被静默排除的第三类。

**阶段二：review scoring。** 每个 A/B 包只显示匿名 paper ID、模型实际看到的 excerpt、已冻结且仅以 C1...CK 编号的标准文本，以及两个随机排序并清除条件标记的 review；不显示 venue 名称、条件、profile 名称、模型名称、原文件名或运行顺序。每条标准无论 applicability 如何都保留一行；评分者先复录冻结的 applicability，只有 `applicable` 行进入 0/1/2 coverage 评分，`not_applicable` 行固定记为 `score=null`。

对每条官方标准按 0、1、2 评分：

- 0：未涉及。
- 1：提及该标准，但分析笼统、不可执行或缺乏文本依据。
- 2：实质检查该标准，并给出可定位依据或明确的验证动作。

每个独立批评点另标：

- supported：具体批评可由 excerpt 核验。
- unsupported：断言了 excerpt 中不存在、不可追溯或与 excerpt 冲突的具体缺陷。
- not_assessable：review 明确承认 excerpt 不足，只提出待核验事项，不把它断言为事实。

最后按“更遵循当前官方标准且证据更可靠”选择 A、B 或 Tie。

### 6.4 作者评分者偏差控制

A、B 既参与系统开发又承担评分，属于不可消除的 expectation bias；主要结果必须明确披露这一限制，不能把双人一致性写成独立外部验证。控制措施为：

1. condition 与左右顺序由脚本分别随机化，映射密钥由评分脚本保管；两份评分文件 hash 锁定后才允许解盲。
2. 用中性 paper ID 和 C1...CK；在盲化副本中把 venue、profile、generic、condition 名称及明显运行标记替换为统一占位符。原始输出原样保留，redaction 规则、命中位置和盲化副本 hash 全部记录。
3. A、B 独立保存逐项 applicability、criteria score、批评依据标签和 A/B/Tie；不讨论单项评分，不覆盖原始文件。
4. 评分者仍可能从内容推断条件；在 limitations 中说明残余偏差，不以 blinding 声称完全消除。
5. 若能获得非作者研究者，只对预注册、按 venue 与条件分层抽取的最多 20% 包做 secondary audit；其结果单独报告，既不替换 A/B 原始标签，也不改变主要分母或结论门槛。

## 7. RQ1：Ledger 提取与状态准确率

### 7.1 自然语料

10 篇 held-out Ledger 子集目标形成 60–100 条经仲裁的自然 Promise。正式评测分三层：

1. Extraction：使用 production promise excerpt，预测 Promise span 与 kind。
2. Discharge classification：向冻结的生产分类 prompt 注入 gold Promise，只评价四类 status 与 evidence。
3. End-to-end：使用系统自行提取的 Promise 继续分类，评价联合正确性。

由于 python/src/argument/ledger.py 的 build_ledger 当前是单体流程，技术实现应在 methods/reviewer_validation/ 中增加评测 staging 或最小可测试接口；拆分只为观测阶段输出，不得改变 production excerpt、prompt、解析器、温度或状态映射。

每篇论文、每个 LLM 阶段运行 3 次。若 provider 支持 seed，则相同 run_id 使用预注册 seed；不支持时明确记录为不可控随机性。

### 7.2 受控状态挑战集

在任何正式运行前建立 20 个 Promise–evidence 基础组，每组产生 paid、partial、unpaid、mismatch 四个受控变体，共 80 项。生成脚本使用 `protocol.yaml` 中的固定 seed；A、B 各提出 10 组，由另一人交叉核验。四个变体除实现状态所需的最小文本变化外保持一致。最终 JSONL、生成参数、seed、逐项 gold、生成脚本和 SHA-256 必须进入 `freeze_manifest.json`；freeze 后运行脚本只能读取这 80 项，不能现场构造、随机改写或替换。

该集合只称为 controlled counterfactual challenge set，不得作为自然分布准确率。分析单位是 20 个基础组，而不是把 80 个相关变体当作独立样本。

### 7.3 匹配与指标

- Exact span match：在第 5.4 节的 immutable full-text 坐标上建立 prediction-gold 候选边，仅当 `char_start` 与 `char_end` 都相等才连边；求最大基数一对一匹配。重复 prediction 只能有一个匹配，其余均为 false positive。
- Relaxed span match：另行在同一 full-text 坐标上为字符 span IoU 大于或等于 0.50 的 pair 连边；先求最大匹配基数，再在该基数下最大化总 IoU，仍并列时按冻结的 `gold_id`、`prediction_id` 字典序裁决。不得使用 excerpt 字符、字符串首次出现位置或人工挑选候选作为计分坐标。
- Promise extraction：Exact Precision、Recall、F1；Relaxed Precision、Recall、F1。
- Kind：在 matched Promise 上报告 Accuracy、Macro-F1、各类 F1 和混淆矩阵。
- Status：在 gold Promise 条件下报告 Accuracy、Macro-F1、四类 F1 和混淆矩阵。
- Evidence hit：分母是 `gold_evidence_spans` 非空且状态已裁决的 gold Promises；若任一可映射 prediction evidence 与任一 gold evidence 在 full-text 坐标上的 IoU 大于或等于 0.50，该 Promise 记 1，否则记 0。多个 evidence 仍只贡献一个 Promise-level 命中。
- Spurious evidence rate：分母是 `gold_evidence_spans` 为空且状态已裁决的 gold Promises；系统输出任一非空 evidence 即记 1。分母为 0 时结果为 NA，并显式报告 0-denominator count，不写成 0%。
- End-to-end correct：分母是全部已裁决 gold Promises；要求 Promise relaxed matched、kind 正确、status 正确，并且 gold evidence 非空时 evidence hit、gold evidence 为空时 prediction evidence 也为空，才记 1。未提取的 gold 直接记 0。
- Reliability：invalid JSON rate、empty response rate、provider failure rate、unknown rate。
- 未仲裁标注一致性：A/B 的 Promise relaxed span F1，以及 matched Promise 上 kind 与 status 的 Cohen kappa。

计数单位是 gold/prediction 在每个正式 `paper_id × run_id` 中的一次出现；三个 run 不是三个独立论文，推断时仍按 paper 聚类。Extraction Precision 分母是 `TP + FP`（全部 prediction occurrences），Recall 分母是 `TP + FN`（全部已裁决 gold occurrences）；unmappable prediction 和匹配外 prediction 都是 FP，未匹配 gold 是 FN。若某 run 无 prediction，该 run 的 Precision 为 NA、Recall 为 0；汇总 Precision 用所有 run 的 `sum(TP) / sum(TP+FP)`，同时报告零 prediction run 数。Kind 分母是 relaxed one-to-one matched-pair occurrences。Gold-conditioned Status 分母是全部已裁决、具有四类实质状态的 `gold Promise × run` occurrences，系统失败、空结果或 unknown 均计错并同时进入 reliability 分母；不得静默删除。Evidence hit、Spurious evidence 与 End-to-end 的 Promise 分母同样按对应条件下的 `gold Promise × run` occurrences 计算。Reliability 各 rate 的分母是该阶段 protocol 列出的全部正式调用。若 gold 本身 unresolved，则不进入上述主要 gold 数量，但必须在流程图和单独敏感性分析中报告其数量与原因。

主要分析单位是论文（n=10）；每篇内先聚合 3 次运行，再对论文做 10,000 次 cluster bootstrap，报告 95% CI。Promise 级总计仅作描述，不能作为独立样本夸大精度。挑战集按 20 个基础组聚类。

## 8. RQ2：Anchor 三态与重定位

在任何正式运行前，从 development 之外选择并冻结 40 个源锚点；生成脚本使用预注册 seed 为每个锚点产生三种成对变体，共 120 项：

- anchored：原 quote 不变，但在前文执行插入、删除、移动或空白变化。
- drifted：目标语义位置保留，但 quote 有受控的小改写、替换或局部释义。
- lost：删除真实目标，并在其他位置放置相似干扰项。

40 个源锚点需覆盖长短 quote、重复短语、标题附近文本、首尾位置和相似上下文。变换脚本保存原文、变换操作、gold status，以及每个变体自身 immutable transformed full text 中按第 5.4 节半开区间约定记录的 gold char span 与文本 hash。源数据、生成脚本、seed、120 项逐项 gold 和输出 SHA-256 全部进入 `freeze_manifest.json`；formal runner 只消费已冻结 JSONL，禁止边运行边生成或改写 case。

直接调用 python/src/argument/anchor.py 的 production relocate，不另写“更聪明”的评测算法。

指标：

- 三态 Accuracy、Macro-F1、各类 Precision、Recall、F1 和混淆矩阵：分母/样本集是全部 120 个冻结变体；每项恰有一个 gold status。
- Correct-location rate：分母是 80 个 anchored 或 drifted 变体；预测 span 与该变体 gold span 的 IoU 大于或等于 0.50 记 1，否则记 0。
- False-relocation rate：分母是 40 个 lost 变体；返回任何非空位置记 1。
- Joint status-location accuracy：分母是全部 120 个变体；状态正确，且 anchored/drifted 的位置正确或 lost 的位置为空才记 1。

主要分析单位是源锚点（n=40），按源锚点聚类 bootstrap；不得把同源的三个变体当作独立样本。

## 9. RQ3：Venue profile 的当前标准遵循度

### 9.1 官方标准映射

对 NeurIPS、ICML、ICLR、ACL、CVPR、KDD、CHI，在冻结日保存当前官方 reviewer guideline 的 URL、访问日期、页面或 PDF hash、允许引用的原文片段和操作化标准。A 提取，B 逐条核验；有争议项共同裁决。

python/src/argument/venue_profiles.yaml 中任何无法映射到当前官方材料的断言，都必须在 pilot 期间删除或改为条件性表述。不得增加人为权重、venue 指纹、强制关键词或为了提高可区分度而设计的暗号。

### 9.2 条件与运行

对 14 篇 held-out 论文分别运行：

- G：目标 venue 标签 + generic profile。
- V：同一个目标 venue 标签 + 对应 venue profile。

除 profile 文本和 profile hash 外，G/V 的 excerpt、venue 标签、persona、prompt 模板、provider/model、参数、checks=["llm"] 与 run_id 保持一致。需要在评测实现中加入显式 profile override，因为当前 python/src/argument/reviewer.py 会根据 venue 自动加载 profile；该 override 只服务隔离实验。

使用串行 run_review 路径，禁止调用 parallel review，禁止加入 ledger、coherence 或 rw 检查。每个条件运行 3 次：

- 14 papers × 2 conditions × 3 runs = 84 reviews。
- 同 paper、同 run_id 的 G/V 组成 1 个 pair，共 42 个盲化 A/B 包。
- G/V 调用顺序按预注册 seed 在每个 pair 内随机化，所有调用仍串行执行。

正式运行前，14 篇论文 × 各自全部官方标准的 applicability raw/gold、标准编号映射、excerpt 和坐标 mapping 均须进入 `freeze_manifest.json`。正式输出落盘后，脚本以独立 seed 随机左右顺序，并按第 6.4 节生成去除 profile/venue 标记的盲化副本；原始输出、redaction log、pair mapping 与副本分别 hash。pair mapping 在 A、B 两份评分 hash 锁定前不可读取。

### 9.3 指标与结论门槛

令 `K_app(p)` 为论文 p 在第 6.3 节仲裁后的 `applicable` 标准数；只有这些 criterion 构成 coverage 分母，`not_applicable` 永不以 0 分惩罚 review，也不进入分母。冻结语料应保证 `K_app(p) >= 1`；若正式 gold 出现 0，该论文的两个条件都将 adherence/coverage 记为 NA，仍保留在输出、失败计数与 critique 指标中，并单列 zero-denominator paper count，不得事后换标准。

- Criteria adherence score：对每个 rater-review，`sum(score_c for applicable c) / (2 * K_app(p))`，范围 0–1；分母是该 paper 的 applicable criterion 数乘以最高分 2。
- Evidence-supported coverage：对每个 rater-review，`count(score_c == 2 for applicable c) / K_app(p)`。
- Critique unit：一个可独立核验的缺陷断言为一项；并列句中可分别真假的断言必须拆分，纯摘要或建议不计。每项恰标为 supported、unsupported 或 not_assessable。
- Unsupported critique rate：`unsupported / (supported + unsupported)`；分母只包含作为事实提出、可判断真假的实质批评，not_assessable 不进入该比例而单独计数。分母为 0 时记 NA 并报告 zero-denominator review count，绝不写成 0%。
- Unsupported critiques per review：该 review 的 unsupported 数；分母是全部 84 reviews，空 review 贡献 0，但同时进入 empty review rate。
- Empty review rate：无任何 critique unit 的 review 数 / 全部 84 reviews；空 review 的 adherence 与 coverage 按 applicable criterion 全部 0 分处理，不能因 unsupported rate 为 NA 获得优势。
- Blind preference：每名评分者在全部 42 pairs 上各给一个 V win、G win 或 Tie；分母是 84 个独立 raw preference labels，另报告 pair-level 仲裁结果，不能只保留一致 pair。
- 一致性：applicability 使用未加权 Cohen kappa；applicable 标准的 0/1/2 使用加权 Cohen kappa；批评依据标签和 A/B/Tie 使用未加权 Cohen kappa。每个 kappa 都报告其实际 item 数和类别分布。

主要分析单位是论文（n=14）。每篇、每条件先跨 3 次运行与 2 名评分者聚合，再计算 V−G 的论文内配对差异；以论文为 cluster 做 10,000 次 bootstrap，报告 95% CI。

RQ3 只有同时满足以下预注册门槛才可作正面主张：

1. Criteria adherence 的 V−G 平均差异（只按上述 `K_app(p)` 计算），其双侧 95% CI 下界大于 0。
2. Unsupported critique rate 的 V−G 差异，其单侧 95% CI 上界小于预注册不劣界 +0.05。

+0.05 表示最多容忍五个百分点的绝对增加，必须在查看 held-out 输出前冻结。若任一门槛未满足，只能写“未证明提升且不增加无依据批评”，不能把 p 大于 0.05 解释为等价或无伤害。

每个 venue 仅 2 篇论文，因此分 venue 结果只作描述，不做显著性结论。唯一主要推断是七 venue 汇总后的预注册配对比较。

## 10. 14 天日程与 A/B 分工

| 日 | A 负责人 | B 负责人 | 共同门槛 |
|---|---|---|---|
| Day 1 | 审计 Ledger/Anchor 评测接口 | 收集七 venue 当前官方标准来源 | 冻结 RQ、主指标、主张边界草案 |
| Day 2 | 建候选语料 manifest 与文件 hash | 独立复核来源、许可、纳入排除 | 按 seed 选定 2 dev + 14 held-out + 10 Ledger 子集 |
| Day 3 | 实现 RQ1/RQ2 staging、双坐标 mapping 与挑战生成器 | 实现 RQ3 profile override、applicability schema、盲化与测试 | 交叉 code review；正式生成器固定 seed，技术文件只进 methods/reviewer_validation/ |
| Day 4 | 运行隔离的 Ledger/Anchor pilot | 运行隔离的 Venue A/B pilot | 修正规则后生成并交叉核验全部 80 + 120 正式挑战项；此日不运行正式项 |
| Day 5 | 独立标注全部 Ledger gold 与 RQ3 applicability | 独立标注全部 Ledger gold 与 RQ3 applicability | 不看正式输出，不讨论单项标签 |
| Day 6 | 继续独立标注并提交 hash | 继续独立标注并提交 hash | 锁定 Ledger 与 applicability 两套 raw 标签 |
| Day 7 | 计算未仲裁一致性 | 独立复算一致性 | 仲裁 gold；建立并复核含全部正式输入、gold、mapping、挑战项和 seed 的 freeze_manifest |
| Day 8 | 只读取冻结项运行 RQ1 | 只读取冻结项运行 RQ2 | G2 hash gate 通过后才执行；本日禁止创建、改写或替换 case |
| Day 9 | 审计 RQ1 完整性与失败记录 | 审计 RQ2 完整性与失败记录 | 保存全部请求、响应、错误和首次落盘 hash |
| Day 10 | 监控串行运行与失败记录 | 生成 84 份 RQ3 review | 完成 42 个随机盲化包，不解盲 |
| Day 11 | 独立评分 42 个包 | 独立评分 42 个包 | 不讨论单项评分 |
| Day 12 | 主统计与表格 | 从原始数据独立复算 | 两份评分文件 hash 锁定并计算未仲裁一致性后才解盲；保留全部复算差异 |
| Day 13 | 修改方法、结果与限制 | 修改 README 主张和逐点回复 | 负面结果进入正文，不换指标 |
| Day 14 | 从空环境执行复现 | 审计安全、许可与 artifact hash | 完成复现清单、主张审计和最终 handoff |

A 主导 Ledger、Anchor 与主统计；B 主导官方标准映射、Venue 实验与复算。两人对正式 gold 与 RQ3 评分拥有同等独立责任，任何一人不得独自生成并裁定自己的标签。

## 11. 技术实现与目录契约

所有技术实现追踪在 `methods/reviewer_validation/`，以下是必需的最小结构；路径不得由执行者临时改名：

- `README.md`：从环境准备到结果复算的唯一运行手册。
- `protocol.yaml` 与 `protocol.sha256`：冻结参数、seed、分析门槛、amendment 记录及 detached hash。
- `freeze_manifest.json` 与 `freeze_manifest.sha256`：所有正式输入、gold、schema、mapping、脚本、配置及其 SHA-256；detached 文件记录 manifest 自身 hash。
- `run_manifest.jsonl`：每个运行/输出首次落盘 hash 的只追加日志。
- `manifests/corpus.csv`：语料来源、许可、hash 与分组。
- `criteria/official_sources.json` 与 `criteria/criterion_map.json`：七 venue 的官方来源元数据、快照 hash 与编号化标准映射。
- `mappings/<paper_id>.<excerpt_id>.map.json`：production excerpt 到 immutable full text 的 piecewise 双坐标映射。
- `schemas/promise_gold.schema.json`、`schemas/anchor_case.schema.json`、`schemas/venue_applicability.schema.json`、`schemas/venue_review_score.schema.json`、`schemas/run_record.schema.json`：冻结字段、枚举、坐标和 denominator 所需 schema。
- `challenges/status_cases.jsonl` 与 `challenges/anchor_cases.jsonl`：分别固定 80 与 120 个正式 case，含 generator seed、gold 和逐项输入 hash。
- scripts/prepare_corpus.py：生成生产解析文本、excerpt 和 manifest。
- scripts/run_ledger.py：独立运行 Extraction、Gold-conditioned Status 与 End-to-end。
- scripts/generate_challenges.py：只在 freeze 前按 seed 生成 status/anchor 正式 case。
- scripts/run_anchor.py：只读取冻结的 40 × 3 锚点挑战集并运行 production relocate。
- scripts/run_venue_ab.py：恒定 venue 标签、串行 checks=["llm"] 的 84 次运行与盲化。
- scripts/score_metrics.py：冻结指标、cluster bootstrap 和表格生成。
- tests/：staging 等价性、无 fallback、条件隔离、盲化、schema 与指标测试。
- `annotations/raw/ledger_A.jsonl`、`ledger_B.jsonl`、`venue_applicability_A.jsonl`、`venue_applicability_B.jsonl` 与 `venue_scores_A.jsonl`、`venue_scores_B.jsonl`：只追加原始标签，各自 hash。
- `annotations/adjudicated/ledger_gold.jsonl` 与 `venue_applicability_gold.jsonl`：仲裁 gold，不覆盖 raw。
- outputs/raw/：逐次响应与错误；按许可决定是否进入版本库。
- results/：机器生成的表、混淆矩阵、CI 与主张门槛判定。

`freeze_manifest.json` 必须覆盖上述所有正式运行前即可确定的文件；`run_manifest.jsonl` 覆盖之后产生的 raw outputs、盲化包、评分文件和结果。任一 pre-run artifact 无 hash、hash 不匹配或 schema 校验失败会阻断 G2，不得开始运行；任一 post-run output 无 hash、损坏或 schema 校验失败则保留原始记录，并按预注册 failure rule 计入对应调用失败分母，不能被另一输出替换。

METHODOLOGY.md 定义“为什么、评什么、何时能下结论”；methods/reviewer_validation/ 定义“如何运行”。技术文档不得反向改变本方法，除非走 amendment 流程。

## 12. 数据、安全与可复现约束

- 只使用公开、允许研究使用的论文；不使用用户私人工作区、未发表稿件或个人信息。
- 全文仅在许可允许时分发；否则本地只读保存，公开 manifest、hash、URL、脚本和允许的短片段。
- python/config/default.local.yaml、环境变量、API key、认证头、代理信息和个人路径不得复制到实验包。
- 运行配置使用脱敏快照；日志只记录 provider/model 元数据，不记录凭据。
- 盲化包不得包含 condition、venue/profile 名称、profile hash 到条件的映射、原文件名暗示或运行顺序；deterministic redaction log 与未改写 raw output 分开保存并 hash。
- A/B 原始标签、冻结配置和原始输出写入后计算 hash；清洗与标准化只生成派生文件。
- 所有失败、空输出、截断和解析异常进入 denominator，并在结果中单列。
- 发布前运行 secret scan、许可审计和从空环境复现。

## 13. 结果解释与负面结果规则

1. 自动测试通过只证明实现按测试运行，不证明 RQ1–RQ3 的实证有效性。
2. 正式结果低于预期时，不得改成 Top-2、关键词命中或会议猜测作为新的主要终点。
3. 不得修改 YAML 强塞 venue 指纹，也不得用关键词数量替代标准遵循度。
4. LLM-as-judge 若后续加入，只能作为预注册的辅助敏感性分析，并须先在人工评分子集上报告一致性；多个模型同意不等于正确。
5. 不得把无显著差异写成等价；“不增加无依据批评”必须满足预注册不劣门槛。
6. 无论正负，正文报告主要指标、CI、失败率、混淆矩阵和限制；附录保存完整次要分析。
7. README 和论文只能采用结果实际支持的最窄表述；conference-calibrated 与 educational effectiveness 在获得对应证据前删除。

## 14. 交付物与验收门

| 交付物 | 最低内容 | 对应 RQ/关切 |
|---|---|---|
| METHODOLOGY.md | RQ、样本、指标、分析单位、冻结与结论规则 | 全部 |
| methods/reviewer_validation/protocol.yaml + freeze_manifest.json | 可机读冻结值、seed、所有正式输入与 gold 的 hash | 全部 |
| corpus manifest + source hashes | 16 篇语料和 10 篇 Ledger 子集的可追溯选择 | RQ1、RQ3 |
| annotation codebook + A/B raw + adjudicated gold | 双人未仲裁一致性和不可变原始标签 | RQ1、RQ3 |
| 80 项状态挑战集 + 120 项锚点挑战集 | 受控边界条件与 gold | RQ1、RQ2 |
| 84 份 review + 42 个 blind pairs | 恒定 venue 标签的 profile-only 对照 | RQ3 |
| metrics tables + confusion matrices + CI | 由冻结脚本生成、可复算 | RQ1–RQ3 |
| manuscript claim audit + response letter | 技术范围、负面结果和限制的一致表述 | 三条审稿关切 |
| reproducibility and security checklist | 空环境复现、许可、secret scan、artifact hashes | 全部 |

正式执行的总 gate：

- G0 Premise gate：研究问题与审稿关切一一对应。
- G1 Pilot gate：真实输出通过人工内容、完整性、边界和安全审计。
- G2 Freeze gate：protocol、语料、模型、prompt/profile、schemas、双坐标 mappings、两套 gold、全部 80 + 120 正式挑战项、指标、seed 与 commit 均在 freeze_manifest 且 hash 复核通过；Day 8 以后只读。
- G3 Data gate：两份原始标签锁定，先算一致性，后做仲裁。
- G4 Isolation gate：RQ3 成对条件只改变 profile，单模型无静默 fallback。
- G5 Analysis gate：按论文或源锚点聚类，不把嵌套观测伪装为独立样本。
- G6 Claim gate：所有公开主张均能追溯到预注册指标和原始 artifact。

## 15. Pattern Memory

| ID | 已观察或批准的前提 | 决策模式 | 后续复用条件 |
|---|---|---|---|
| PM-001 | 用户已批准“两人、14 天、三项技术验证”的前提，并要求先形成方案文档再执行 | 先把 METHODOLOGY.md 冻结为 canonical plan，本步只写文档、不运行正式实验 | 审稿意见要求新增实证证据，且执行周期与人员已明确 |
| PM-002 | 当前 Ledger 将提取与分类串在 build_ledger 内 | 为可辨识指标拆出评测 staging，同时保持生产 prompt/excerpt 等价 | 一个端到端流程包含多个待分别验证的推断阶段 |
| PM-003 | 当前 LLM 客户端存在 Cloud 到 Ollama 的自动降级 | 正式实验单 provider/model、失败即记录，不让处理差异污染条件 | 评测系统存在自动路由、重试或 fallback |
| PM-004 | 当前 Reviewer prompt 同时受 venue 名称与 profile 影响 | venue 名称恒定，只替换 profile，并使用 checks=["llm"] 串行路径 | 要估计一个提示组件的增量因果作用 |
| PM-005 | 两名作者同时承担标注与评分 | 先冻结 applicability、独立作答、去除 venue/profile 标记、锁定 raw 后解盲；外部小样本只能作 secondary audit | 无额外外部标注者且仍需降低期望偏差 |
| PM-006 | Protocol review PASS；首轮实施 brief 已核对当前 Ledger、Reviewer 与 LLM client 路径 | 首轮只并行三个非重叠工作包：Ledger 两阶段可评测性、venue profile 单因素隔离、protocol/schema/freeze-manifest 脚手架；Anchor 待脚手架 handback 后顺序启动 | canonical protocol 已通过方法审查，但 G1/G2 尚未通过，且需要先建立可失败关闭的执行边界 |
| PM-007 | Work C 结构性 handback 已完成：12 个 scaffold tests PASS，draft verifier PASS（9 verified、24 pending），strict verifier 非零退出并显示 `FORMAL_RUN: BLOCKED` | 把“结构已可审计”与“正式输入已冻结”分开；允许顺序启动 Work D 的 Anchor development pilot，但保持所有正式生成与运行 fail-closed | schema/verifier 已落地而 code commit、seeds、model 与正式 artifacts 尚未冻结；strict BLOCKED 是当前预期状态，不是 G2 失败修复目标 |
| PM-008 | 首轮开发态基础设施 handback 已完成：Work A 30+24 tests PASS；Work B 46+12 tests PASS，canonical fixture provenance 遗留项已关闭；Work C 12 tests PASS，draft 只列预期 pending 且 strict BLOCKED；Work D 40+7+12 tests PASS | 把 A/B/C/D 的 PASS 限定为生产等价 staging、单因素隔离、冻结校验和 Anchor development infrastructure 的可执行性；保留开发态负向指标，不生成或运行正式 120 项 Anchor challenge | 这些证据均来自 synthetic/development inputs，只能支持下一阶段的人工 pilot 与冻结准备，不能支持 RQ1–RQ3 研究结论 |
| PM-009 | 独立 capstone 复核对当前 development infrastructure 判定 PASS，但未调用外部 LLM，未读取 held-out，也未生成或运行任何 formal data | 独立复核通过不升级研究 gate；G1 Pilot、G2 Freeze 与 G4 Isolation 继续保持 BLOCKED | 只有真实输出人工 pilot、全部正式输入冻结校验和外部单模型成对隔离证据分别完成后，才重新判定 G1/G2/G4 |
| PM-010 | Work E 首轮独立全量复核 FAIL：遗漏 ICML-S1 的 2026 revised date 与 ACL-S2 的 2025 changelog date，KDD-Y4 将 ADS-only 证据泛化，CHI-Y4 将 qualitative-only 隐私/同意指南泛化，synthesis 使用了非规范 decision 术语；窄范围纠正后全量复审 PASS，最终为 20 个官方 source/20 个唯一 URL、42 个旧 YAML atom、35 个 replacement，决策分布 6 `keep`/29 `rewrite_conditionally`/7 `remove` | 来源审计首次失败必须先显式记录并纠正，再独立全量复审；PASS 只关闭官方来源、条件性和逐句 lineage 缺口 | 当手写 profile 要转为可评分标准时，必须全量复核来源日期、适用边界和规范枚举；该 PASS 不是 profile 效果证据 |
| PM-011 | Work F 实施完成后的首轮独立复核为 REVISE：`run_venue_ab.py` 在构造/比较时仍对 `profile_text[:600]` 截断，导致长 NeurIPS 成对 probe 失败，且 CHI-Y4 的 source 顺序在 synthesis 与 criterion map 间不一致；窄范围修复后最终全量复审 PASS，focused tests 为 60/19/13/12 passed，长 NeurIPS full-profile mock pair 完整进入 prompt/artifact；最终 capstone 将 `venue_profiles.yaml` 规范化为 LF，generic block 的规范 UTF-8/LF 表示为 219 bytes，SHA-256 `30fd129da348e52128cfceab4844b54dedb7abdb39c9fe217251bc29fb60619a` | 实施 PASS 必须由实际长输入消费路径证明，不能只检查 YAML 和单元句；独立 REVISE 后只允许对失败原因做窄范围修复再全量复审；byte-exact 契约必须基于 `.gitattributes` 要求的 LF 表示，避免 checkout 换行导致伪漂移 | 该 PASS 仅证明 source-grounded profile/评分映射与 mock 消费路径正确；未运行真实模型、held-out 或 formal data，G1/G2/G4 仍为 BLOCKED，不支持 RQ3 效果结论 |

VERDICT: PROCEED AFTER PILOT AND FREEZE
CLAIM: This protocol can test three bounded technical claims but cannot establish educational effectiveness or human-reviewer style fidelity.
GATE: Begin held-out runs only after G0–G4 pass, every formal input is listed in freeze_manifest.json, and every listed hash verifies.
EVIDENCE: The design is constrained by main@099b69c paths listed in Section 2, immutable dual-coordinate mappings, criterion-specific denominators, and pre-run frozen challenge artifacts; no empirical result is claimed.
CONFIDENCE: HIGH FOR EXECUTABILITY, UNDETERMINED FOR OUTCOMES
CONFOUND CHECK: Provider fallback, excerpt/full-text coordinate drift, criterion applicability, venue/profile leakage, author-rater expectation, nested samples, runtime case generation, and post-hoc metric changes are explicitly controlled.
