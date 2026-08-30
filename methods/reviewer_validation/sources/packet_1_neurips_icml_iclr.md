# Work E-P1：NeurIPS、ICML 与 ICLR 官方指南来源审计

结论：当前三个 profile 只有 ICML 的总体方法基础/清晰可复现要求和 ICLR 的主张证据要求得到完整支持；固定消融、固定统计格式、多数据集、代码强制、同算力/同切分及既往投稿意见等断言均超出当前官方标准，必须删除或收窄为由论文主张触发的条件性检查。

## 1. 审计边界

- packet：E-P1，仅 NeurIPS、ICML、ICLR。
- 检索与访问日期：2026-08-29。
- 被审计文件：`python/src/argument/venue_profiles.yaml`，Git commit `099b69c369f13b0259e68f39a1bfb4f1b7ac2d0d`，SHA-256 `da260cdec18eaa2b8d04fcd0ba0e6c223c9967d1a74692290452f9d172eaf59a`。
- 仅采用 `neurips.cc`、`icml.cc`、`iclr.cc` 上由相应会议维护的当前官方页面。检索未发现可用的 NeurIPS/ICML 2027 reviewer guide，故采用最新检得的 2026 页面；ICLR 已发布 2027 reviewer/author guides，采用 2027 页面。
- 搜索结果摘要、博客、论文、workshop 页面、OpenReview 内容、个人页面及第三方材料均未作为支持证据。
- 状态枚举严格使用 `supported`、`partially_supported`、`unsupported`、`conditionality_missing`、`source_uncertain`；动作严格使用 `keep`、`rewrite_conditionally`、`remove`。
- 下文每个 URL 只保留一段短引文且累计不超过 25 个英文词；其余内容均为释义。

## 2. NeurIPS 官方来源

### NEURIPS-S1

- venue：NeurIPS
- source_id：`NEURIPS-S1`
- 页面标题：NeurIPS 2026 Reviewing Guidelines
- 规范 URL：https://neurips.cc/Conferences/2026/ReviewerGuidelines
- URL host：`neurips.cc`
- 官方性依据：NeurIPS 官方会议站的 2026 main-track reviewer guidelines，页面按 General、Theory、Use-Inspired、Concept & Feasibility、Negative Results 划分贡献类型。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径及正文明确）。
- access date：2026-08-29
- 定位：`Reviewing Guidelines for Different Contribution Types`；`General Reviewing Guidelines`；各 contribution-type 小节。
- verbatim criterion（本来源累计 14 词）：“Reviewers should assess a submission according to the Contribution Type selected by the authors.”
- 可独立评分的释义标准：按投稿人选择的贡献类型解释 Quality、Clarity、Significance、Originality；分别判断主张是否可靠、表达是否清楚且足以理解/复现、贡献是否重要、是否产生新见解或新理解。
- applicability/conditionality：适用于 NeurIPS 2026 main track；四维度适用于所有贡献类型，但含义随类型变化。Theory 投稿可在无实证实验时成立，Use-Inspired 等类型也不能套用纯理论优先级。
- 不确定性：无；页面未标示独立发布日期，故年份字段保留为 `not_stated`。

### NEURIPS-S2

- venue：NeurIPS
- source_id：`NEURIPS-S2`
- 页面标题：NeurIPS Paper Checklist Guidelines
- 规范 URL：https://neurips.cc/public/guides/PaperChecklist
- URL host：`neurips.cc`
- 官方性依据：NeurIPS 官方 public guide；2026 Main Track Handbook 指示 reviewers 将论文所附 NeurIPS checklist 作为评价因素。
- publication/update year：`not_stated`；applicable conference year：当前 NeurIPS submissions，且由 `NEURIPS-S3` 明确关联至 2026 main track。
- access date：2026-08-29
- 定位：总则；items 1–2（Claims、Limitations）；items 4–8（Reproducibility、Code、Experimental Details、Statistical Significance、Compute）；item 10（Broader Impacts）。
- verbatim criterion（本来源累计 9 词）：“answering ‘no’ or ‘n/a’ is not grounds for rejection”
- 可独立评分的释义标准：检查主张范围与证据是否匹配、重要限制是否披露、是否提供与贡献相称的复现路径；若包含实验，再检查训练/测试设置、不确定性或统计显著性说明及计算资源。代码和数据开放是受鼓励的复现方式之一，不是所有论文的统一拒稿门槛。
- applicability/conditionality：Claims 与 Limitations 广泛适用；实验设置、统计和计算资源只在有实验时触发；代码开放可有解释；broader impact 仅在论文范围和潜在影响适当时触发。
- 不确定性：页面未标示 publication/update year；其官方性及 2026 适用关系由 `NEURIPS-S3` 确认，不据此推定具体发布日期。

### NEURIPS-S3

- venue：NeurIPS
- source_id：`NEURIPS-S3`
- 页面标题：NeurIPS Main Track Handbook
- 规范 URL：https://neurips.cc/Conferences/2026/MainTrackHandbook
- URL host：`neurips.cc`
- 官方性依据：NeurIPS 官方会议站的 2026 Main Track Handbook，正文版本标记 `V2026.3`，覆盖 authors、reviewers、ACs 与 SACs。
- publication/update year：`2026`（页面版本 `V2026.3`）；applicable conference year：`2026`。
- access date：2026-08-29
- 定位：`Review Form`，Questions、Limitations 与 Overall entries。
- verbatim criterion（本来源累计 16 词）：“If you suggest new experiments, please explain what kind of question they would help to answer”
- 可独立评分的释义标准：额外实验请求应对应可能改变判断的明确问题，并考虑 rebuttal 期算力约束；评价 limitations/implications 时应建设性地指出缺口；整体评价综合技术质量、影响、实验/资源、复现与伦理。
- applicability/conditionality：适用于 NeurIPS 2026 main track；ablation 只是可能的例子，只有能回答与主张相关的问题时才应提出，不能转写成所有实证论文的固定必需项。
- 不确定性：无。

## 3. NeurIPS 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `NEURIPS-Y0` | `NeurIPS emphasises theoretical novelty and empirical rigour.` | 官方四维度包含 originality 与 quality，但 2026 明确按贡献类型解释；Theory 可不做实证，其他类型也不以理论新颖性为统一优先项。 | `partially_supported` | `rewrite_conditionally` | For the selected NeurIPS contribution type, assess quality, clarity, significance, and originality; do not assume every submission must combine theory and empirical validation. | `NEURIPS-S1` |
| `NEURIPS-Y1` | `(1) novelty beyond incremental improvement` | 官方要求判断 originality，但明确新见解、理解、任务、指标或既有技术的新组合均可构成原创性，并不要求全新方法；“beyond incremental improvement”过窄。 | `partially_supported` | `rewrite_conditionally` | Assess originality through new insights, understanding, framings, tasks, metrics, methods, or well-motivated combinations; do not require a wholly new method. | `NEURIPS-S1` |
| `NEURIPS-Y2` | `(2) solid ablations isolating each contribution` | 官方只把 ablation 作为“解释额外实验回答什么问题”的例子，没有规定所有论文都必须完整消融；原句遗漏主张相关性与贡献类型条件。 | `conditionality_missing` | `rewrite_conditionally` | Request or weigh an ablation only when it would answer a decision-relevant question about a claim, and state that question. | `NEURIPS-S3` |
| `NEURIPS-Y3` | `(3) correct and complete statistical reporting (mean ± std, seeds)` | 官方 checklist 要求实验主结果给出适当的 error bars、置信区间或显著性信息，并解释变异来源和计算；没有把 `mean ± std` 与 seeds 设为唯一格式，且无实验时不适用。 | `conditionality_missing` | `rewrite_conditionally` | For experiments supporting the main claims, assess whether uncertainty or statistical significance is reported appropriately and whether variability and its calculation are explained. | `NEURIPS-S2` |
| `NEURIPS-Y4` | `(4) reproducibility (code, hyperparams, compute budget)` | 复现路径、实验设置和计算资源有官方依据；但代码仅受鼓励且可有合理替代，具体披露随贡献/实验类型触发。 | `conditionality_missing` | `rewrite_conditionally` | Assess whether the contribution has a reasonable reproducibility path; for experiments, consider code, data or instructions, settings, and compute disclosure, without treating code release as universally mandatory. | `NEURIPS-S2` |
| `NEURIPS-Y5` | `(5) discussion of limitations and broader impact` | limitations 广泛适用；negative societal impacts 由论文范围和直接影响触发，不是每篇基础研究的无条件同构要求。 | `conditionality_missing` | `rewrite_conditionally` | Assess acknowledged limitations and implications; consider negative societal impacts when appropriate to the paper's scope. | `NEURIPS-S2`, `NEURIPS-S3` |

NeurIPS 小结：官方来源 3 个；proposed profile sentence 6 个；`supported=0`、`partially_supported=2`、`unsupported=0`、`conditionality_missing=4`、`source_uncertain=0`。建议条件化/缩窄 `NEURIPS-Y0`—`NEURIPS-Y5`，无整项删除。

## 4. ICML 官方来源

### ICML-S1

- venue：ICML
- source_id：`ICML-S1`
- 页面标题：ICML 2026 Call for Papers
- 规范 URL：https://icml.cc/Conferences/2026/CallForPapers
- URL host：`icml.cc`
- 官方性依据：ICML 官方会议站的 2026 main-track call for papers，含明确 `Reviewing Criteria`。
- publication/update：`Revised January 25, 2026`（页面明确标示）；applicable conference year：`2026`（由页面标题、路径及正文明确）。
- access date：2026-08-29
- 定位：`Reviewing Criteria`。
- verbatim criterion（本来源累计 15 词）：“All claims must be clearly stated and supported by reproducible experiments and/or sound theoretical analysis.”
- 可独立评分的释义标准：投稿应为对机器学习社区有重要意义的原创、严谨研究；主张应清楚，并由可复现实验和/或可靠理论分析支持；贡献应置于相关科学及机器学习文献中并与先前工作区分。
- applicability/conditionality：适用于 ICML 2026 main track；`and/or` 表明理论与实证不是每篇论文必须同时具备，也没有规定固定 baseline、数据集数量或形式化保证。
- 不确定性：无；页面明确标示 `Revised January 25, 2026`。

### ICML-S2

- venue：ICML
- source_id：`ICML-S2`
- 页面标题：ICML 2026 Reviewer Instructions
- 规范 URL：https://icml.cc/Conferences/2026/ReviewerInstructions
- URL host：`icml.cc`
- 官方性依据：ICML 官方会议站的 2026 reviewer instructions，含 main-track review form 的逐维说明。
- publication/update year：`not_stated`；applicable conference year：`2026`（由页面标题、路径及 reviewer timeline 明确）。
- access date：2026-08-29
- 定位：`Tips for Reviewing`；`Main Track Reviewer Form Instructions` 下的 Strengths and Weaknesses、Soundness、Presentation、Significance、Originality。
- verbatim criterion（本来源累计 5 词）：“Soundness is distinct from impact.”
- 可独立评分的释义标准：分别评估 soundness、presentation、significance 与 originality；核对主张是否由正确理论或设计良好的实验支持、方法是否适当、论述是否清楚且置于相关文献中，并把技术可靠性与影响大小分开判断。
- applicability/conditionality：适用于 ICML 2026 main track；理论检查只在论文含理论结果时触发，实验设计检查只在论文含实证结果时触发。指南不规定统一 baseline 清单或用多个数据集作为所有泛化主张的必要条件。
- 不确定性：无。

## 5. ICML 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `ICML-Y0` | `ICML values machine-learning methodology with strong theoretical or empirical foundations.` | 官方 Reviewing Criteria 明确要求原创、严谨的机器学习研究，并允许可复现实验和/或可靠理论分析支持主张。 | `supported` | `keep` | ICML values rigorous machine-learning research whose claims have sound theoretical and/or empirical support. | `ICML-S1` |
| `ICML-Y1` | `(1) clear problem formulation` | 官方要求主张清楚、presentation 清晰并置于相关文献中；没有单独定义名为 problem formulation 的统一评分项，现有概念只得到部分支持。 | `partially_supported` | `rewrite_conditionally` | Assess whether the problem, contributions, and claims are clearly stated and contextualized. | `ICML-S1`, `ICML-S2` |
| `ICML-Y2` | `(2) theoretical guarantees or rigorous empirical analysis` | 官方支持 sound theoretical analysis 和设计良好、可复现的实验，但未要求所有理论工作给出 guarantees；当前措辞把理论门槛写得过强。 | `partially_supported` | `rewrite_conditionally` | Assess whether the claims are supported by reproducible, well-designed experiments and/or sound theoretical analysis; do not require formal guarantees from every contribution. | `ICML-S1`, `ICML-S2` |
| `ICML-Y3` | `(3) comparison to strong, up-to-date baselines` | 官方要求在当前相关研究中定位并区分贡献，但没有规定统一的“强且最新”baseline 集合；比较需求应由论文主张决定。 | `partially_supported` | `rewrite_conditionally` | Assess whether the contribution is situated and distinguished against relevant prior research; require a particular baseline only when it is needed to test a claim. | `ICML-S1`, `ICML-S2` |
| `ICML-Y4` | `(4) generalisation claims backed by multiple datasets` | 当前官方 CFP 与 reviewer instructions 只要求证据支持主张及其范围，没有规定用多个数据集作为所有泛化主张的必要条件。 | `unsupported` | `remove` | 无；删除固定多数据集要求。 | 无（`ICML-S1`, `ICML-S2` 已核查但不支持） |
| `ICML-Y5` | `(5) clarity and reproducibility` | presentation/clarity 与可复现证据均是官方明确评价内容。 | `supported` | `keep` | Assess clarity and whether the paper provides enough information and evidence for an expert to understand and reproduce the claimed results. | `ICML-S1`, `ICML-S2` |

ICML 小结：官方来源 2 个；proposed profile sentence 5 个；`supported=2`、`partially_supported=3`、`unsupported=1`、`conditionality_missing=0`、`source_uncertain=0`。建议删除 `ICML-Y4`；条件化/缩窄 `ICML-Y1`、`ICML-Y2`、`ICML-Y3`。

## 6. ICLR 官方来源

### ICLR-S1

- venue：ICLR
- source_id：`ICLR-S1`
- 页面标题：ICLR 2027 Reviewer Guide
- 规范 URL：https://iclr.cc/Conferences/2027/ReviewerGuidelines
- URL host：`iclr.cc`
- 官方性依据：ICLR 官方会议站的 2027 reviewer guide，页面包含 ICLR 2027 reviewer tasks、dates 与逐步评审说明。
- publication/update year：`not_stated`；applicable conference year：`2027`（由页面标题、路径及 reviewer timeline 明确）。
- access date：2026-08-29
- 定位：`Reviewing a submission: step-by-step`，Strong points 与 four key questions。
- verbatim criterion（本来源累计 6 词）：“Does the paper support the claims?”
- 可独立评分的释义标准：判断论文是否清楚、技术正确、实验严谨、可复现并具有新颖发现；核对理论或实证结果是否正确、科学严谨且足以支持主张，并评估工作对社区的意义和新知识价值。
- applicability/conditionality：适用于 ICLR 2027 reviewers；理论与实证是按论文目标选择的证据形态。指南没有规定完整消融、统一算力/切分、既往投稿意见或指定实验模板为普遍门槛。
- 不确定性：无。

### ICLR-S2

- venue：ICLR
- source_id：`ICLR-S2`
- 页面标题：ICLR 2027 Author Guidelines
- 规范 URL：https://iclr.cc/Conferences/2027/AuthorGuidelines
- URL host：`iclr.cc`
- 官方性依据：ICLR 官方会议站的 2027 author guidelines，覆盖 supplementary code、reproducibility statement 与 OpenReview 流程。
- publication/update year：`not_stated`；applicable conference year：`2027`（由页面标题、路径、submission deadlines 及 reviewing timeline 明确）。
- access date：2026-08-29
- 定位：`Supplementary Materials`；`Recommended: Reproducibility statement`；`Reviewing Process`。
- verbatim criterion（本来源累计 12 词）：“We encourage all authors to submit code as part of their submission.”
- 可独立评分的释义标准：复现性重要，作者被强烈鼓励提供复现说明并可提交补充代码；代码是增加可复制信息的受鼓励材料而非强制条件。官方 reviews 与 public discussion 通过 OpenReview 公开。
- applicability/conditionality：适用于 ICLR 2027 submissions；复现方式依贡献而异，代码只是示例之一。公开评审描述的是流程透明度，不能推出 conference 对笼统“open-science style”的奖励权重。
- 不确定性：无。

## 7. ICLR 当前 YAML 逐项审计

| sentence_id | 当前 YAML 句子或列举项 | 官方证据比较 | status | action | proposed profile sentence | source_ids |
|---|---|---|---|---|---|---|
| `ICLR-Y0` | `ICLR uses open peer review and rewards reproducible, open-science work.` | 官方确认 OpenReview 上公开 reviews/discussion，并强调可复现性；但没有定义“奖励 open-science work”的独立权重，且开放代码不是强制条件。 | `partially_supported` | `rewrite_conditionally` | ICLR uses OpenReview with public reviews and discussion; assess technical correctness, experimental rigor, reproducibility, novelty, claim support, and significance. | `ICLR-S1`, `ICLR-S2` |
| `ICLR-Y1` | `(1) open-source code (expected, not optional)` | 官方明确只是鼓励提交代码和复现说明；“not optional”与当前规则相冲突。 | `unsupported` | `remove` | 无；删除代码强制断言。 | 无（`ICLR-S2` 明确提供反证） |
| `ICLR-Y2` | `(2) ablation completeness` | 当前官方 reviewer/author guides 没有把完整消融设为普遍标准；一般实验严谨性不足以推出特定实验设计。 | `unsupported` | `remove` | 无；删除普遍消融断言。 | 无（`ICLR-S1`, `ICLR-S2` 已核查但不支持） |
| `ICLR-Y3` | `(3) fair comparison (same compute budget, same data splits)` | 官方要求实验严谨且证据支持主张，但没有规定所有比较必须使用完全相同的 compute budget 和 data splits；当前句只得到更一般原则的部分支持。 | `partially_supported` | `rewrite_conditionally` | Assess whether experimental comparisons are rigorous and whether their evidence supports the claims; require matched compute or data splits only when a claim-specific rationale makes them necessary. | `ICLR-S1` |
| `ICLR-Y4` | `(4) addressing reviewer comments from prior submissions if applicable` | 当前指南只要求在本轮 discussion 中回应信息并更新判断，没有要求披露或回应先前投稿的 reviewer comments。 | `unsupported` | `remove` | 无；删除既往投稿意见要求。 | 无（`ICLR-S1`, `ICLR-S2` 已核查但不支持） |
| `ICLR-Y5` | `(5) theoretical insight or strong empirical justification` | 官方要求理论或实证结果正确、科学严谨并支持主张，且不要求 state-of-the-art；该项与官方主张—证据标准一致。 | `supported` | `keep` | Assess whether theoretical or empirical results are correct, scientifically rigorous, and sufficient to support the paper's claims. | `ICLR-S1` |

ICLR 小结：官方来源 2 个；proposed profile sentence 3 个；`supported=1`、`partially_supported=2`、`unsupported=3`、`conditionality_missing=0`、`source_uncertain=0`。建议删除 `ICLR-Y1`、`ICLR-Y2`、`ICLR-Y4`；条件化/缩窄 `ICLR-Y0`、`ICLR-Y3`。

## 8. 完整性、重复、版权与不确定性检查

- E-P1 范围：仅 NeurIPS、ICML、ICLR；未审计 generic 或其他四个 venue。
- Current-YAML coverage：18/18 个原子项恰好审计一次（每个 venue 的总述句 1 个、列举项 5 个）；无漏项、无重复 sentence_id。
- Proposed sentence traceability：NeurIPS 6/6、ICML 5/5、ICLR 3/3 均映射至少一个本 packet 官方 `source_id`；4 个 `remove` 项没有用非官方材料或一般常识补证。
- 汇总：官方来源 7 个、proposed profile sentence 14 个；`supported=3`、`partially_supported=7`、`unsupported=4`、`conditionality_missing=4`、`source_uncertain=0`。
- URL 检查：本 packet 共 7 个规范 URL，packet 内均唯一；host 仅为 `neurips.cc`、`icml.cc`、`iclr.cc`。与当前 E-P2 的 7 个 URL 交集为 0；E-P3 文件尚未出现，因此其重复检查待 synthesis/review 在 packet 到齐后复核。
- cross_packet_escalation：`none`；未用 NeurIPS/ICML/ICLR 的通用政策替其他 packet 写 proposed sentence。
- SOURCE_UNCERTAIN：0；页面未标示 publication/update year 时写 `not_stated`，ICML-S1 则记录页面明确标示的 `Revised January 25, 2026`。ICLR 采用已发布的 2027 指南；NeurIPS/ICML 采用检索日最新可用的 2026 指南，不把搜索不到的 2027 页面当成已发布来源。
- 版权检查：各来源累计短引文词数分别为 NEURIPS-S1=14、NEURIPS-S2=9、NEURIPS-S3=16、ICML-S1=15、ICML-S2=5、ICLR-S1=6、ICLR-S2=12；其余内容为释义，无整页复制、附件或长引文。
- 安全检查：文件不含凭据、认证信息、私密配置、未授权全文或正式输入 hash。

## 9. Packet gates 与停止点

| Gate | 结果 | E-P1 证据 |
|---|---|---|
| E1 Scope/domain | PASS | 恰含 NeurIPS/ICML/ICLR；7 个 URL 均为所属会议官方域名，packet 内无重复，与现有 E-P2 无重复。 |
| E2 Field completeness | PASS | 每个来源均记录标题、URL/host、官方性、年份、access date、定位、短引文、释义、条件性与不确定性。 |
| E3 Current-YAML audit | PASS | `NEURIPS-Y0..Y5`、`ICML-Y0..Y5`、`ICLR-Y0..Y5` 共 18 项各出现一次。 |
| E4 Sentence traceability | PASS | 14 个 proposed sentence 全部映射官方 source_id。 |
| E5 Unsupported/uncertain handling | PASS | 4 个 unsupported 项均为 remove；4 个缺条件项及 7 个部分支持项均缩窄到证据范围。 |
| E6 Copyright/scope | PASS | 每来源英文原文累计不超过 25 词；未写入附件、凭据、私密路径或正式实验 artifact。 |

明确停止点：本 packet 只完成 E-P1 来源收集与逐句审计；未修改 `venue_profiles.yaml`、`METHODOLOGY.md`、protocol、manifest、criteria 文件或任何 detached hash，也未启动 RQ3 development/formal 运行。
