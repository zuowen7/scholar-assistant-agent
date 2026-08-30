# Work E-P3：KDD 与 CHI 官方指南来源审计

结论：当前 KDD/CHI profile 把特定 track 或特定贡献类型的条件性标准写成了 venue 通用要求；KDD 的真实部署与上线后量化只适用于 ADS track，CHI 的用户研究、场景验证和定性分析要求均应由论文的贡献类型与主张触发。

## 1. 审计边界

- packet：E-P3，仅 KDD、CHI。
- 检索与访问日期：2026-08-29。
- 被审计文件：`python/src/argument/venue_profiles.yaml`，Git commit `099b69c369f13b0259e68f39a1bfb4f1b7ac2d0d`，SHA-256 `da260cdec18eaa2b8d04fcd0ba0e6c223c9967d1a74692290452f9d172eaf59a`。
- 仅采用 `kdd2026.kdd.org` 与 `chi2026.acm.org` 上由 KDD 2026、CHI 2026 维护的当前页面；搜索结果摘要、论文、workshop 页面、博客、个人页面、第三方材料和外部镜像均未作为支持证据。
- KDD 2026 将 Research、Applied Data Science（ADS）、Datasets & Benchmarks、AI for Sciences 等 track 分开；当前 YAML 未指定 track，故不得把 ADS 的部署门槛泛化到所有 KDD 论文。
- CHI 2026 明确按 contribution type 和相应领域规范判断研究质量；当前 YAML 中 user study、mixed methods、qualitative analysis 等不得泛化为所有 CHI 论文的统一方法要求。
- 状态枚举严格使用 `supported`、`partially_supported`、`unsupported`、`conditionality_missing`、`source_uncertain`；动作严格使用 `keep`、`rewrite_conditionally`、`remove`。
- 下文引文按来源累计计数；每个 URL 的英文原文累计均不超过 25 个词。其余内容均为释义。

## 2. KDD 官方来源

### KDD-S1

- venue：KDD
- source_id：`KDD-S1`
- 页面标题：Research Track: Call for Papers – KDD 2026
- 规范 URL：https://kdd2026.kdd.org/research-track-call-for-papers/
- URL host：`kdd2026.kdd.org`
- 官方性依据：KDD 2026 官方会议站的 Research Track 征稿页；页面给出 KDD 2026 Research Track 的 program chairs、投稿入口、范围与决策因素。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径、会议日期及 Cycle 1/2 正文明示）。
- access date：2026-08-29
- 定位：`Scope`；`Reviewing Process` → `Decision`；`Reproducibility`。
- verbatim criterion（本来源累计 18 词）：“technical merit, originality, potential impact, quality of execution, quality of presentation, related work, reproducibility of results, and ethics”
- 可独立评分的释义标准：
  - Research Track 覆盖知识发现、数据科学和 AI，从理论基础到面向科学、商业、医学与工程问题的创新模型、算法和应用型技术贡献。
  - 决策应分别考虑技术价值、原创性、潜在影响、执行与表达质量、相关工作、结果可复现性和伦理。
  - 可扩展系统以及可解释/可信数据科学是允许的主题方向，而不是每篇 Research Track 论文都必须满足的统一实验清单。
  - 代码仓库在投稿时是高度推荐而非强制；不能把 artifact availability 升级为当前 profile 未写明的普遍硬门槛。
- applicability/conditionality：适用于 KDD 2026 Research Track。scalability 只在论文提出大规模系统、效率或相关主张时触发；interpretability/explainability 只在论文以此为贡献或评价对象时触发。理论论文不需要工业数据或真实部署。
- 不确定性：页面未标示独立的 publication/update date，故年份字段为 `not_stated`；会议年份、track 和决策因素均明确，无 `SOURCE_UNCERTAIN`。

### KDD-S2

- venue：KDD
- source_id：`KDD-S2`
- 页面标题：Applied Data Science (ADS) Track: Call for Papers – KDD 2026
- 规范 URL：https://kdd2026.kdd.org/applied-data-science-ads-track-call-for-papers/
- URL host：`kdd2026.kdd.org`
- 官方性依据：KDD 2026 官方会议站的 ADS Track 征稿页；页面给出 ADS program chairs、投稿入口、范围、严格部署门槛和例外。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径、会议日期及 Cycle 1/2 正文明示）。
- access date：2026-08-29
- 定位与独立标准：
  - `Scope`：ADS 面向已经部署的数据挖掘、数据科学、机器学习和 AI 应用；通常必须量化上线后表现。短引文：“quantification of the post-launch performance”（5 词）。
  - `Scope`：仅在页面列明的现实阻碍例外下，未上线系统才可能适用；离线使用现实数据不等同部署。短引文：“deployed in a real-world system”（5 词）。
  - `Scope`：ADS 的新颖性可以来自应用或工程层面，而不必来自基础算法。短引文：“application domain, engineering design, usability approach, or business use case”（10 词）。
- 可独立评分的释义标准：
  - 对 ADS 稿件，评分真实部署是否成立以及是否量化上线后表现；若因现实阻碍未部署，则评分部署尝试、障碍记录和可迁移经验是否满足官方例外。
  - 评分问题意义、设计取舍、数据收集/建模/受限环境部署挑战、成功与失败经验及其对广泛应用数据科学受众的价值。
  - ADS 新颖性可以体现在应用领域、工程设计、可用性方案或业务用例；不能机械要求基础算法创新。
- applicability/conditionality：只适用于 KDD 2026 ADS Track。页面明确 Research 与 ADS 二选一；“现实部署、上线后量化”不得用于 Research Track。官方要求的是真实部署证据而非“工业所有的数据”，故 academic/industrial 数据来源不是判定边界。
- 不确定性：页面未标示独立的 publication/update date，故年份字段为 `not_stated`；严格要求及例外均明确，无 `SOURCE_UNCERTAIN`。

## 3. KDD 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `KDD-Y0` | `KDD emphasises knowledge discovery and data mining with real-world impact.` | 官方范围现为 knowledge discovery、data science 与 AI，且分成多个 track。现实部署/影响是 ADS 的核心条件，但不是 Research Track 的普遍门槛；当前句既缩窄了范围又遗漏 track 条件。 | `partially_supported` | `rewrite_conditionally` | KDD covers knowledge discovery, data science, and AI; apply Research-track criteria to research papers and ADS criteria only to ADS submissions. | `KDD-S1`, `KDD-S2` |
| `KDD-Y1` | `(1) scalability to large datasets` | Research CFP 把 scalable AI 和 large-scale systems 列为主题之一，并以技术价值、执行质量和证据作决策；它没有要求所有 KDD 论文都用大数据集证明 scalability。 | `conditionality_missing` | `rewrite_conditionally` | When a paper makes scalability or large-scale-systems claims, assess whether its execution and evidence support those claims; do not require large-dataset experiments of every KDD paper. | `KDD-S1` |
| `KDD-Y2` | `(2) evaluation on real industrial data (not just academic benchmarks)` | Research Track 可接受理论与一般方法，不要求工业数据；ADS 要求真实上线和 post-launch 量化，且明确仅在现实数据上离线测试仍不算部署。官方依据没有要求数据必须由 industry 提供。 | `partially_supported` | `rewrite_conditionally` | For ADS submissions, assess evidence of live deployment and quantified post-launch performance, or the documented barriers and broadly applicable lessons allowed by the stated exception; do not impose this requirement on Research-track papers. | `KDD-S2` |
| `KDD-Y3` | `(3) interpretability / explainability of results` | interpretability/explainability 是 Trustworthy and Responsible Data Science 的允许主题；没有官方依据把它设成每篇 KDD 论文的独立硬指标。 | `conditionality_missing` | `rewrite_conditionally` | When interpretability or explainability is part of the claimed contribution, assess its technical merit, execution, and evidence; do not treat it as a universal requirement. | `KDD-S1` |
| `KDD-Y4` | `(4) practical deployment considerations` | ADS 明确要求部署、取舍、障碍和上线后表现；Research Track 没有通用部署要求。当前句遗漏 track 条件，且 ADS-only 来源不能支持把该标准扩展到其他声称部署的论文。 | `conditionality_missing` | `rewrite_conditionally` | For ADS submissions, assess design tradeoffs, deployment challenges, post-launch evidence, and lessons learned; do not impose ADS deployment criteria on Research-track papers. | `KDD-S2` |
| `KDD-Y5` | `(5) novelty relative to data mining literature` | Research Track 的创新技术贡献、originality 与 related work 有直接依据；ADS 的 novelty 可以来自应用领域、工程、可用性或业务用例，不必是新的数据挖掘算法。当前句未区分 track。 | `partially_supported` | `rewrite_conditionally` | For Research-track papers, assess originality and innovative technical contribution in relation to relevant work; for ADS papers, recognize that novelty may lie in the application domain, engineering design, usability, or business use case. | `KDD-S1`, `KDD-S2` |

KDD 小结：官方来源 2 个；proposed profile sentence 6 个；`supported=0`、`partially_supported=3`、`unsupported=0`、`conditionality_missing=3`、`source_uncertain=0`。条件化/分 track 改写 `KDD-Y0`—`KDD-Y5`；无句子可按当前无条件形式直接保留。

## 4. CHI 官方来源

### CHI-S1

- venue：CHI
- source_id：`CHI-S1`
- 页面标题：Guide to Reviewing Papers - ACM CHI 2026
- 规范 URL：https://chi2026.acm.org/guide-to-reviewing-papers/
- URL host：`chi2026.acm.org`
- 官方性依据：CHI 2026 官方会议站面向 Papers reviewer 的评审指南；页面说明贡献判断、透明度和评审流程注意事项。
- publication/update year：`not_stated`；applicable conference year：`2026`（由站点、页面导航和正文中的 CHI 2026 明示）。
- access date：2026-08-29
- 定位：`Contributions`；`Transparency`。
- verbatim criterion（本来源累计 11 词）：“primary criterion for the evaluation of all papers”；“original research contribution”
- 可独立评分的释义标准：所有论文的首要标准是其对 HCI 的原创研究贡献；贡献可以有多种形态，reviewer 应按论文实际贡献评价。报告不透明可以使贡献可信度受到质疑。
- applicability/conditionality：适用于 CHI 2026 Papers 全部贡献类型；它不要求统一的 mixed-methods、user-study 或 theory 结果。具体方法与证据必须根据贡献类型缩窄。
- 不确定性：原检索路径重定向至上述规范 URL；规范页面仍在 CHI 2026 官方域名。页面未标示发布日期，故写 `not_stated`，无 `SOURCE_UNCERTAIN`。

### CHI-S2

- venue：CHI
- source_id：`CHI-S2`
- 页面标题：Guide to a Successful Submission - ACM CHI 2026
- 规范 URL：https://chi2026.acm.org/guide-to-a-successful-submission/
- URL host：`chi2026.acm.org`
- 官方性依据：CHI 2026 官方会议站的 Papers 投稿与 review-form 指南；页面明确列出评审表标准并给出不同贡献/方法的透明度要求。
- publication/update year：`not_stated`；applicable conference year：`2026`。
- access date：2026-08-29
- 定位与独立标准：
  - `The Review Form`：评审涉及 significance、originality、research quality、presentation clarity 与 relevant previous work。短引文：“Significance, Originality, Research quality, Presentation clarity, Relevant previous work”（9 词）。
  - `Transparency`：透明度适用于全部论文，但评价细节随贡献和方法变化。短引文：“regardless of the contribution type and methodology”（7 词）。
- 可独立评分的释义标准：
  - 评分贡献的显著性、原创性、研究质量、表达清晰度以及相关工作的充分性。
  - 对技术或定量贡献，评分方法、软件与分析细节是否足以检查正确性、有效性、可靠性并支持复现/复制。
  - 对定性研究，评分理论或概念基础、方法选择、参与者/场地选择、数据收集与分析、主题形成、研究者 positionality/偏差及伦理考虑是否透明且有理由。
  - 对涉及人类提问的研究，评分研究工具、问题措辞和程序是否充分披露；不能反推出所有 CHI 论文都必须招募参与者。
- applicability/conditionality：总评审维度适用于全部 CHI Papers；技术/定量、定性及人类参与者细项仅由相应贡献类型和方法触发。页面没有要求必须使用 thematic analysis、grounded theory 或 mixed methods。
- 不确定性：页面未标示发布日期，故写 `not_stated`；页面及适用范围明确，无 `SOURCE_UNCERTAIN`。

### CHI-S3

- venue：CHI
- source_id：`CHI-S3`
- 页面标题：Contributions to CHI - ACM CHI 2026
- 规范 URL：https://chi2026.acm.org/contributions-to-chi/
- URL host：`chi2026.acm.org`
- 官方性依据：CHI 2026 官方会议站给 reviewer/author 的贡献类型与对应评价问题页面；该页由 CHI review guide 直接引用。
- publication/update year：`not_stated`；applicable conference year：`2026`。
- access date：2026-08-29
- 定位：`Introduction`；`Development or Refinement of Interface Artifacts or Techniques`；`Understanding Users`；`Systems, Tools, Architectures, and Infrastructure`；`Theory`；`Validation and Replication`。
- verbatim criterion（本来源累计 11 词）：“a good systems paper does not necessarily require a user study”
- 可独立评分的释义标准：
  - 贡献可包括 artifact/technique、理解用户、system/tool/infrastructure、methodology、theory、innovation/vision、argument、validation/replication 等；各类型使用不同问题判断价值与严谨性。
  - 对 artifact 或 systems 贡献，验证可以是合理论证、经验反思、用户研究或其他足以证明价值的证据；用户研究不是统一门槛。
  - 当 system 主张依赖目标环境时，评分预期场景、任务、用户、实际障碍及验证证据是否支撑该主张。
  - 对 understanding-users 或 replication 贡献，参与者、程序、measure 和 context 是条件触发的评价对象。
  - theory 或 design implications 是可能的贡献类型，不是每篇 CHI 论文必须同时提供的输出。
- applicability/conditionality：先识别论文声称的 contribution type，再使用对应问题；不得从某一类型的示例推导 venue-wide 方法要求。
- 不确定性：页面未标示发布日期，故写 `not_stated`；当前 CHI 2026 页面和引用关系明确，无 `SOURCE_UNCERTAIN`。

### CHI-S4

- venue：CHI
- source_id：`CHI-S4`
- 页面标题：Papers - ACM CHI 2026
- 规范 URL：https://chi2026.acm.org/authors/papers/
- URL host：`chi2026.acm.org`
- 官方性依据：CHI 2026 官方 Papers 主页面；正文列出会议年份、投稿日期、review 质量口径和 human-subjects 政策。
- publication/update year：`not_stated`；applicable conference year：`2026`（页面标题、会议日程及正文明确）。
- access date：2026-08-29
- 定位：`Message from the Papers Chairs`；`Policy on Research Involving Human Participants and Subjects`；`Preparing and Submitting Your Paper` → `Research Quality`。
- verbatim criterion（本来源累计 11 词）：“involves human subjects must go through the appropriate ethics review requirements”
- 可独立评分的释义标准：
  - CHI Papers 可来自多种 HCI 活动，评价 originality、significance、validity、research quality 与 presentation clarity。
  - 涉及 human subjects 的研究必须遵循作者研究环境中适用的伦理审查要求，并向 reviewer 简述该制度背景。
  - 研究质量应按相关 subcommittee 的规范判断；不同贡献社群的 rigor 标准不能互换为单一方法模板。
- applicability/conditionality：human-subjects 伦理要求只在研究涉及相应对象时触发；研究质量适用于全部论文，但具体方法标准由 contribution/subcommittee 决定。
- 不确定性：页面未标示发布日期，故写 `not_stated`；会议年份和政策适用对象明确，无 `SOURCE_UNCERTAIN`。

## 5. CHI 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `CHI-Y0` | `CHI focuses on Human-Computer Interaction with mixed-methods evaluation.` | HCI 范围得到直接支持；官方同时强调多种贡献类型与方法，并明确系统论文不一定需要用户研究。没有官方依据把 mixed-methods 设为 CHI 的通用评价方式。 | `partially_supported` | `rewrite_conditionally` | CHI evaluates original contributions to HCI; assess rigor and evidence according to the contribution type rather than requiring mixed methods. | `CHI-S1`, `CHI-S2`, `CHI-S3` |
| `CHI-Y1` | `(1) user study design (participants, tasks, measures)` | participants/tasks/measures 对涉及用户、human-subjects 或 replication 的研究是可评分项；系统、理论、论证等贡献可用其他合理证据验证。当前句遗漏触发条件。 | `conditionality_missing` | `rewrite_conditionally` | For work involving users or human participants, assess whether the relevant population, tasks or instruments, procedures, measures, and analysis are transparently reported and justified; do not require a user study for every contribution. | `CHI-S2`, `CHI-S3` |
| `CHI-Y2` | `(2) ecological validity (lab vs. real-world setting)` | 官方贡献指南要求在主张依赖场景时说明预期 setting、tasks、users、障碍并采用适当验证；它没有要求所有论文做 lab-versus-real-world 比较，也未把“ecological validity”列为统一硬指标。 | `conditionality_missing` | `rewrite_conditionally` | When claims depend on a proposed setting or context, assess whether the setting, tasks, users, obstacles, and chosen validation support those claims; do not impose a universal lab-versus-field requirement. | `CHI-S3` |
| `CHI-Y3` | `(3) qualitative analysis rigour (thematic analysis, grounded theory)` | 官方透明度指南支持严格披露定性研究的理论基础、方法、抽样/场地、收集、分析、主题形成、positionality 与偏差；未要求必须采用 thematic analysis 或 grounded theory。 | `partially_supported` | `rewrite_conditionally` | For qualitative research, assess transparent justification of its conceptual basis, participant or site selection, data collection and analysis, theme construction, researcher positionality, and potential bias; do not require a named method such as thematic analysis or grounded theory. | `CHI-S2` |
| `CHI-Y4` | `(4) ethical considerations for human subjects` | CHI Papers 页面明确要求涉及 human subjects 的研究遵循适用伦理审查，并披露制度背景；这是 CHI-S4 支持的通用 human-subjects 条件。CHI-S2 对 anonymity、privacy、consent 与 data use 的透明度要求仅在定性研究方法适用时触发，不能推广到全部 human-subjects 研究。 | `supported` | `keep` | For research involving human subjects, assess compliance with applicable ethics-review requirements and disclosure of the institutional context; for qualitative research, separately assess transparent treatment of anonymity, privacy, consent, and data use. | `CHI-S4`, `CHI-S2` |
| `CHI-Y5` | `(5) contribution to HCI theory or design guidelines` | theory 与 design implications 都是可能的 HCI 贡献，但官方列出更多贡献类型，且首要标准是对 HCI 的原创贡献。当前句把两个可能类型误写成通用二选一。 | `partially_supported` | `rewrite_conditionally` | Assess whether the paper makes an original and significant contribution to HCI according to its contribution type; require theoretical or design implications only when they are part of the claimed contribution. | `CHI-S1`, `CHI-S2`, `CHI-S3` |

CHI 小结：官方来源 4 个；proposed profile sentence 6 个；`supported=1`、`partially_supported=3`、`unsupported=0`、`conditionality_missing=2`、`source_uncertain=0`。直接保留并明确化 `CHI-Y4`；条件化/缩窄 `CHI-Y0`—`CHI-Y3`、`CHI-Y5`。

## 6. 完整性、重复与版权检查

- E-P3 范围：KDD、CHI 各出现一次；未审计 generic 或其他五个 venue。
- Current-YAML coverage：12/12 个原子项恰好审计一次（每个 venue 的范围句 1 个、列举项 5 个）；无漏项、无重复 sentence_id。
- Proposed sentence traceability：KDD 6/6、CHI 6/6 均映射至少一个本 packet 官方 `source_id`；无句子使用第三方材料补证。
- URL 检查：本 packet 共 6 个规范 URL，均唯一；host 仅为 `kdd2026.kdd.org`、`chi2026.acm.org`；与检索时已存在的 E-P2 URL 重复数为 0，所属 venue 官方域名与 E-P1 也不共享。
- cross_packet_escalation：`none`；未使用 ACM 通用政策页或其他可能跨 venue 复用的 URL，外链只用于官方页面自身说明而未作为支持来源。
- SOURCE_UNCERTAIN：0；全部页面的 page-level publication/update date 均未标示，已按要求写 `not_stated`，没有猜测；conference year 和适用 track/type 均由页面明确。
- 版权检查：各来源累计短引文词数分别为 KDD-S1=18、KDD-S2=20、CHI-S1=11、CHI-S2=16、CHI-S3=11、CHI-S4=11；均不超过每来源 25 词，其余内容为释义，无整页复制或附件。
- 条件性警示：KDD 后续 profile 必须携带 track 语义，否则无法同时忠实表达 Research 与 ADS 标准；CHI 后续 profile 必须先识别 contribution type，不能用 user-study 或 mixed-methods 作为 venue 指纹。

## 7. Packet gates 与停止点

| Gate | 结果 | E-P3 证据 |
|---|---|---|
| E1 Scope/domain | PASS | 恰含 KDD/CHI；6 个 URL 全在当前官方会议域名；packet 内及已存在 packet 间无重复。 |
| E2 Field completeness | PASS | 每个来源均记录标题、URL/host、官方性、年份、access date、定位、短引文、释义、条件性与不确定性。 |
| E3 Current-YAML audit | PASS | `KDD-Y0..Y5` 与 `CHI-Y0..Y5` 共 12 项各出现一次。 |
| E4 Sentence traceability | PASS | 12 个 proposed sentence 全部映射官方 source_id。 |
| E5 Unsupported/uncertain handling | PASS | 5 个缺条件项与 6 个部分支持项均缩窄到来源范围；没有用非官方来源或常识扩大标准。 |
| E6 Copyright/scope | PASS | 每来源英文原文累计不超过 25 词；未写入凭据、私密路径、附件或正式输入 hash。 |

明确停止点：本 packet 只完成 E-P3 证据收集与逐句审计；未修改 `venue_profiles.yaml`、`METHODOLOGY.md`、protocol、manifest、criteria 文件或任何 detached hash，也未启动 RQ3 development/formal 运行。
