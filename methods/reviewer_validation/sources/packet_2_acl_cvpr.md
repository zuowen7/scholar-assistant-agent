# Work E-P2：ACL 与 CVPR 官方指南来源审计

结论：当前 ACL/CVPR profile 只有会议范围描述得到完整支持；其余断言多数需要缩窄为“与论文主张相关时”的可评分标准，ACL 的普遍人工评测要求及 CVPR 的通用消融、指定基准要求缺少当前官方依据，应删除。

## 1. 审计边界

- packet：E-P2，仅 ACL、CVPR。
- 检索与访问日期：2026-08-29。
- 被审计文件：`python/src/argument/venue_profiles.yaml`，Git commit `099b69c369f13b0259e68f39a1bfb4f1b7ac2d0d`，SHA-256 `da260cdec18eaa2b8d04fcd0ba0e6c223c9967d1a74692290452f9d172eaf59a`。
- 仅采用 `2026.aclweb.org`、`aclrollingreview.org` 与 `cvpr.thecvf.com` 上由会议或主办组织维护的当前页面；搜索结果摘要、论文、workshop 页面、博客、个人页面和第三方材料均未作为支持证据。
- 状态枚举严格使用 `supported`、`partially_supported`、`unsupported`、`conditionality_missing`、`source_uncertain`；动作严格使用 `keep`、`rewrite_conditionally`、`remove`。
- 下文引文按来源累计计数；每个 URL 的英文原文累计均不超过 25 个词。其余均为释义。

## 2. ACL 官方来源

### ACL-S1

- venue：ACL
- source_id：`ACL-S1`
- 页面标题：Main Conference - ACL 2026
- 规范 URL：https://2026.aclweb.org/calls/main_conference_papers/
- URL host：`2026.aclweb.org`
- 官方性依据：ACL 2026 主会议官网的 Main Conference 征稿页；页面列出 ACL 2026 program chairs，并说明主会投稿经 ARR 评审与 meta-review。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径和正文明确）。
- access date：2026-08-29
- 定位：`Overview`，首段；`Paper Submission Information`。
- verbatim criterion（本来源累计 6 词）：“Computational Linguistics and Natural Language Processing”
- 可独立评分的释义标准：论文是否属于计算语言学或自然语言处理范围，并形成实质、原创且未发表的研究贡献。
- applicability/conditionality：适用于 ACL 2026 main conference；页面明确接受多种贡献类型，因此不能把某一种方法或结果形态设成普遍硬门槛。
- 不确定性：无；页面未标示发布日期，故年份字段保留为 `not_stated`。

### ACL-S2

- venue：ACL
- source_id：`ACL-S2`
- 页面标题：ARR Reviewer Guidelines
- 规范 URL：https://aclrollingreview.org/reviewerguidelines
- URL host：`aclrollingreview.org`
- 官方性依据：页面自述为 Association for Computational Linguistics 的同行评审平台；ACL 2026 主会官网明确主会稿件使用 ARR reviews 与 meta-reviews。
- publication/update：`01.05.2025`（页面官方 changelog 最后列出的更新日期，按页面原格式记录）；applicable conference year：持续适用于检索日的当前 ARR，ACL 2026 通过 ARR 收审。
- access date：2026-08-29
- 定位与独立标准：
  - `Common problems in NLP papers` 总则：评估论文是否技术可靠且主张范围适当。短引文：“technically sound and appropriately scoped”（5 词）。
  - `G1`：研究问题、知识缺口、贡献、假设与限制是否清楚。短引文：“Unclear research question or contribution”（5 词）。
  - `G4`：关键术语是否定义清楚（不另引原文）。
  - `R1`：用于公平比较的基线是否与主张相关并得到充分调优。短引文：“baselines that are not sufficiently well-tuned”（6 词）。
  - `M3`：仅在论文提供资源且观察到未披露的数据问题时，将其作为问题提出（不另引原文）。
  - `H10`、`R2`：单语研究本身有价值；跨语言泛化主张必须与实际样本范围相符（不另引原文）。
  - `H13`：额外比较或实验只有在判断论文主张所必需时才可能成为实质要求（不另引原文）。
  - `H14`：要求特定封闭模型比较必须直接关系论文主张，而不是默认要求。短引文：“only reasonable if it directly bears on the claim”（9 词）。
- 可独立评分的释义标准：分别评分技术可靠性与主张范围、问题/贡献清晰度、基线选择与调优是否足以支撑主张、特定 LLM 比较是否确有必要。
- applicability/conditionality：这些是 case-by-case 的审稿检查项；指南明确反对把 SOTA、某种首选方法或无关额外实验当作普遍拒稿理由。
- 不确定性：页面不是 ACL 2026 专版，但为检索日的当前官方 ARR 指南；`01.05.2025` 是页面 changelog 日期，不是 ACL 2026 适用年份，其与 ACL 2026 的流程关联由 `ACL-S1` 明确。

### ACL-S3

- venue：ACL
- source_id：`ACL-S3`
- 页面标题：ACL Rolling Review – A peer review platform for the Association for Computational Linguistics（HTML title；正文将本页标识为 ARR Responsible NLP Research checklist）
- 规范 URL：https://aclrollingreview.org/responsibleNLPresearch/
- URL host：`aclrollingreview.org`
- 官方性依据：ARR 官方站的 Responsible NLP Research checklist 指南；页面说明该 checklist 属于投稿表，reviewers 将其作为评价因素。
- publication/update year：`2024`（页面 credits 明示 updated for ARR October 2024 cycle）；applicable conference year：当前 ARR，ACL 2026 经 ARR 收审。
- access date：2026-08-29
- 定位与独立标准：
  - `B5-B6`：使用或创建数据时，记录来源/覆盖范围、语言/语言现象、域以及基本统计和数据切分。短引文：“Did you provide documentation of the artifacts”（7 词）。
  - `B5`：任何语言数据均报告其语言。短引文：“report the language of any language data”（7 词）。
  - `D1-D5`：若使用人工标注者或参与者，报告指令、招募、补偿、同意/伦理审查及人口信息。短引文：“instructions given to participants”（4 词）。
- 可独立评分的释义标准：分别评分数据文档完整性、语言/域覆盖说明、人工标注过程透明度；缺失项可有明确理由，不能自动视为拒稿依据。
- applicability/conditionality：只在论文使用/创建相应 artifact、人工标注或人类参与者时触发；页面强调 checklist 以透明度为目标，合理说明可以接受。
- 不确定性：无。页面没有要求普遍报告 inter-annotator agreement，也没有要求自动指标不足时必须做人工评测。

## 3. ACL 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `ACL-Y0` | `ACL covers Natural Language Processing and Computational Linguistics.` | `ACL-S1` 直接定义主会覆盖 CL/NLP。 | `supported` | `keep` | ACL covers Computational Linguistics and Natural Language Processing. | `ACL-S1` |
| `ACL-Y1` | `(1) linguistic validity and task definition` | 官方指南支持研究问题、贡献、关键术语、方法与主张范围清楚且技术可靠；没有把“linguistic validity”定义为所有稿件的独立硬指标。 | `partially_supported` | `rewrite_conditionally` | Assess whether the research question, contribution, key terms, methods, and claims are clear, technically sound, and appropriately scoped. | `ACL-S2` |
| `ACL-Y2` | `(2) comparison to strong NLP baselines (including fine-tuned LLMs)` | 相关且充分调优的基线有依据；“包括 fine-tuned LLMs”不是普遍要求，特定模型比较只有直接关系主张时才合理。 | `partially_supported` | `rewrite_conditionally` | Assess comparisons against relevant, sufficiently tuned baselines when they are needed to evaluate the paper's claims; request a particular LLM comparison only when it directly bears on those claims. | `ACL-S2` |
| `ACL-Y3` | `(3) human evaluation where automatic metrics are insufficient` | 检索到的当前 ACL/ARR reviewer、review form 与 Responsible NLP 指南没有规定“自动指标不足时必须人工评测”；它们要求评估证据可靠性和披露实际采用的人类研究，但不能推出该普遍要求。 | `unsupported` | `remove` | 无；删除该普遍断言。 | 无（`ACL-S2`、`ACL-S3` 已核查但不支持） |
| `ACL-Y4` | `(4) dataset construction quality and annotation agreement` | 数据质量披露、artifact 文档和人工标注过程透明度有依据；当前材料未要求普遍报告 annotation agreement。 | `partially_supported` | `rewrite_conditionally` | For papers that use or create datasets or human annotations, assess whether data provenance, coverage, statistics, identified quality issues, and annotation procedures are reported or explicitly justified. | `ACL-S2`, `ACL-S3` |
| `ACL-Y5` | `(5) cross-lingual / multilingual scope if applicable` | `ACL-S3` 要求记录语言与覆盖范围；`ACL-S2` 的 H10 明确承认任何语言的单语研究价值，R2 要求主张与样本范围匹配。因此只能条件化检查覆盖与泛化，不能把多语实验设为普遍门槛。 | `partially_supported` | `rewrite_conditionally` | When language coverage is relevant to the claims, assess whether languages and linguistic/domain coverage are documented and whether generalization claims match that coverage; do not require multilingual evaluation merely because a study is monolingual. | `ACL-S2`, `ACL-S3` |

ACL 小结：官方来源 3 个；proposed profile sentence 5 个；`supported=1`、`partially_supported=4`、`unsupported=1`、`conditionality_missing=0`、`source_uncertain=0`。建议删除 `ACL-Y3`；条件化/缩窄 `ACL-Y1`、`ACL-Y2`、`ACL-Y4`、`ACL-Y5`。

## 4. CVPR 官方来源

### CVPR-S1

- venue：CVPR
- source_id：`CVPR-S1`
- 页面标题：CVPR 2026 Call for Papers
- 规范 URL：https://cvpr.thecvf.com/Conferences/2026/CallForPapers
- URL host：`cvpr.thecvf.com`
- 官方性依据：IEEE/CVF CVPR 2026 官方会议站的主会征稿页；页面标示 IEEE Computer Society 与 Computer Vision Foundation。
- publication/update year：`not_stated`；applicable conference year：`2026`（页面标题、路径和正文明确）。
- access date：2026-08-29
- 定位：开篇 `Topics of interest`；主题列表。
- verbatim criterion（本来源累计 8 词）：“all aspects of computer vision and pattern recognition”
- 可独立评分的释义标准：论文是否属于计算机视觉/模式识别的广泛技术范围并构成高质量原创研究；效率与可扩展视觉只是允许的主题之一。
- applicability/conditionality：适用于 CVPR 2026 main technical program；主题列表不是每篇论文都必须满足的检查清单。
- 不确定性：无；页面未标示发布日期，故年份字段保留为 `not_stated`。

### CVPR-S2

- venue：CVPR
- source_id：`CVPR-S2`
- 页面标题：CVPR 2026 Reviewer Guidelines
- 规范 URL：https://cvpr.thecvf.com/Conferences/2026/ReviewerGuidelines
- URL host：`cvpr.thecvf.com`
- 官方性依据：CVPR 2026 官方会议站的 reviewer guidelines，正文明确面向 2026 Reviewing Committee。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径和正文明确）。
- access date：2026-08-29
- 定位与独立标准：
  - `Be Mindful`：评估技术可靠性及对领域的贡献。短引文：“technically sound and make a contribution to the field”（9 词）。
  - 同节：未超过现有 benchmark SOTA 不能单独构成拒稿理由。短引文：“not grounds for rejection by itself”（6 词）。
  - `Check for Reproducibility`：代码随补充材料提交为自愿鼓励，reviewer 检查也为可选。短引文：“submit their code as part of supplementary material”（8 词）。
- 可独立评分的释义标准：分别评分技术可靠性/贡献、性能证据相对主张的充分性、复现信息；不得把 SOTA 或代码提交升级为统一硬要求。
- applicability/conditionality：适用于 CVPR 2026 reviewers；数据发布、个人数据、社会影响和 limitations 等要求均由论文内容触发，且多个项目明确只是鼓励或正向考虑。
- 不确定性：无。

### CVPR-S3

- venue：CVPR
- source_id：`CVPR-S3`
- 页面标题：CVPR 2026 Reviewer Training Material
- 规范 URL：https://cvpr.thecvf.com/Conferences/2026/ReviewerTrainingMaterial
- URL host：`cvpr.thecvf.com`
- 官方性依据：CVPR 2026 官方会议站的 reviewer training，页面明确其补充 `CVPR-S2`。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径和正文明确）。
- access date：2026-08-29
- 定位与独立标准：
  - `Careful Reading and Brief Summary`：识别核心主张并判断证据能否支持。短引文：“evaluate the evidence supporting them”（5 词）。
  - `What Should Be Accepted?`：复现、数据贡献、伦理、社会影响和 limitations 作为正向考虑因素。短引文：“limitations discussions positively”（3 词）。
  - `Large Language Models`：真实 CVPR 评审不得由 LLM 起草 review。短引文：“Using LLMs to draft any portion of your review”（9 词）。
  - `Good Final Justification Examples` 与 `Common Reviewing Pitfalls`：示例文字出现 ablations、ImageNet、controlled experiments 和 inference time，但它们描述特定假想论文或改进建议，不构成每篇投稿都必须满足的政策（不另引原文）。
- 可独立评分的释义标准：分别评分核心主张—证据对应、limitations 讨论质量；LLM 禁令是评审流程政策而非论文质量标准。
- applicability/conditionality：前两项适用于 2026 评审；LLM 禁令适用于真实、保密的 CVPR review workflow。对已公开论文进行离线研究模拟不等同于 CVPR 官方评审，但不得宣称系统可合规用于真实 CVPR 审稿。
- 不确定性：无。

### CVPR-S4

- venue：CVPR
- source_id：`CVPR-S4`
- 页面标题：CVPR 2026 Author Guidelines
- 规范 URL：https://cvpr.thecvf.com/Conferences/2026/AuthorGuidelines
- URL host：`cvpr.thecvf.com`
- 官方性依据：CVPR 2026 官方会议站的 author guidelines。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径和正文明确）。
- access date：2026-08-29
- 定位：`What's New for Submissions & Authors at CVPR 2026?`，Compute reporting。
- verbatim criterion（本来源累计 5 词）：“will not influence acceptance decisions”
- 可独立评分的释义标准：2026 compute reporting 是实验性、对 reviewer 不可见且不参与录用决定，因此不能据此把 FLOPs、参数量或推理时间设为所有投稿的审稿硬标准。
- applicability/conditionality：适用于 CVPR 2026 compute-reporting initiative；论文若主动提出效率/可扩展性贡献，仍应以主张—证据充分性评估，但那是条件触发的技术判断。
- 不确定性：无。

## 5. CVPR 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `CVPR-Y0` | `CVPR covers Computer Vision and Pattern Recognition.` | `CVPR-S1` 直接定义范围。 | `supported` | `keep` | CVPR covers computer vision and pattern recognition. | `CVPR-S1` |
| `CVPR-Y1` | `(1) benchmark performance with reproducible protocol` | 官方材料支持技术可靠性、性能证据和复现性，但明确反对仅因未超过 benchmark SOTA 而拒稿；当前句把 benchmark performance 写得过于普遍。 | `partially_supported` | `rewrite_conditionally` | Assess technical soundness and contribution, interpret benchmark results alongside novelty and impact, and consider whether the reported method and results are reproducible; do not require state-of-the-art performance. | `CVPR-S2`, `CVPR-S3` |
| `CVPR-Y2` | `(2) ablation study isolating visual components` | `CVPR-S3` 的示例 review 提到 ablations 与 controlled experiments，但只针对示例中的特定主张；当前官方 CFP、reviewer guidelines、training 与 author guidelines 均未把 component ablation 规定为普遍标准。一般“证据支持主张”不足以推出固定实验设计。 | `unsupported` | `remove` | 无；删除该普遍断言。 | 无（`CVPR-S1`—`CVPR-S4` 已核查但不支持普遍要求） |
| `CVPR-Y3` | `(3) qualitative results showing failure modes` | 官方指南正向看待诚实的 limitations 讨论，但没有要求必须用 qualitative results 展示 failure modes，也不要求单独 limitations section。 | `partially_supported` | `rewrite_conditionally` | Consider an honest discussion of limitations positively; do not require a separate limitations section or treat its absence alone as a rejection reason. | `CVPR-S2`, `CVPR-S3` |
| `CVPR-Y4` | `(4) comparison on standard benchmarks (ImageNet, COCO, etc.)` | `CVPR-S3` 的训练示例提到 ImageNet 与标准 baseline，但这些是针对假想论文的示范措辞；没有当前官方材料要求所有论文使用 ImageNet、COCO 或其他指定 benchmark，且 `CVPR-S2` 说明未超过既有 benchmark SOTA 不能单独决定拒稿。 | `unsupported` | `remove` | 无；删除指定 benchmark 的普遍断言。 | 无（`CVPR-S1`—`CVPR-S4` 已核查但不支持普遍要求） |
| `CVPR-Y5` | `(5) efficiency (FLOPs, params, inference time) reported` | 效率/可扩展性是允许的主题，`CVPR-S3` 的示例也会在相关主张下讨论推理时间；但 2026 compute report 对 reviewer 不可见且不影响录用，当前句遗漏“论文提出效率主张时”这一条件。 | `conditionality_missing` | `rewrite_conditionally` | Only when a paper makes an efficiency or scalability claim, assess whether the evidence supports that claim; the CVPR 2026 compute report is not visible to reviewers and does not affect acceptance decisions. | `CVPR-S1`, `CVPR-S3`, `CVPR-S4` |

CVPR 小结：官方来源 4 个；proposed profile sentence 4 个；`supported=1`、`partially_supported=2`、`unsupported=2`、`conditionality_missing=1`、`source_uncertain=0`。建议删除 `CVPR-Y2`、`CVPR-Y4`；条件化/缩窄 `CVPR-Y1`、`CVPR-Y3`、`CVPR-Y5`。

## 6. 完整性、重复与版权检查

- E-P2 范围：ACL、CVPR 各出现一次；未审计 generic 或其他五个 venue。
- Current-YAML coverage：12/12 个原子项恰好审计一次（每个 venue 的范围句 1 个、列举项 5 个）；无漏项、无重复 sentence_id。
- Proposed sentence traceability：ACL 5/5、CVPR 4/4 均映射至少一个本 packet 官方 `source_id`；三个 `remove` 项没有伪造替代句或用非官方材料补证。
- URL 检查：本 packet 共 7 个规范 URL，均唯一；host 仅为 `2026.aclweb.org`、`aclrollingreview.org`、`cvpr.thecvf.com`。
- cross_packet_escalation：`none`；未发现需要其他 packet 归属裁决的跨 venue 通用 URL。
- SOURCE_UNCERTAIN：0；ACL-S1 与 CVPR-S1—CVPR-S4 未标示页面级 publication/update 日期，按字段要求写 `not_stated`；ACL-S2 记录官方 changelog 日期 `01.05.2025`，ACL-S3 的 2024 更新年份由页面 credits 明示；均未把适用会议年份冒充发布日期。
- 版权检查：各来源累计短引文词数分别为 ACL-S1=6、ACL-S2=25、ACL-S3=18、CVPR-S1=8、CVPR-S2=23、CVPR-S3=17、CVPR-S4=5；其余内容为释义，无整页复制或附件。
- 适用性警示：CVPR 2026 官方政策禁止在真实保密审稿中用 LLM 起草 review；后续 RQ3 只能表述为对公开论文的离线标准遵循模拟，不能表述为 CVPR 官方流程可部署工具。

## 7. Packet gates 与停止点

下表只判定 E-P2 packet-local gates；七 venue 全局唯一性、跨 packet URL 重复、synthesis 与独立复核尚未发生，因此不构成 Work E 总体 PASS。

| Gate | 结果 | E-P2 证据 |
|---|---|---|
| E1 Scope/domain | PASS | 恰含 ACL/CVPR；7 个 URL 全在官方会议/组织控制域名；packet 内无重复。 |
| E2 Field completeness | PASS | 每个来源均记录标题、URL/host、官方性、年份、access date、定位、短引文、释义、条件性与不确定性。 |
| E3 Current-YAML audit | PASS | `ACL-Y0..Y5` 与 `CVPR-Y0..Y5` 共 12 项各出现一次。 |
| E4 Sentence traceability | PASS | 9 个 proposed sentence 全部映射官方 source_id。 |
| E5 Unsupported/uncertain handling | PASS | 3 个 unsupported 项均为 remove；1 个缺条件项及 6 个部分支持项均缩窄到证据范围。 |
| E6 Copyright/scope | PASS | 每来源英文原文累计不超过 25 词；未写入凭据、私密路径、附件或正式输入 hash。 |

明确停止点：本 packet 只完成 E-P2 证据收集与逐句审计；未修改 `venue_profiles.yaml`、`METHODOLOGY.md`、protocol、manifest、criteria 文件或任何 detached hash，也未启动 RQ3 development/formal 运行。
