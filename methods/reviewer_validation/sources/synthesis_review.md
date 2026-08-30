# Venue-profile synthesis review

结论：三份 packet 与当前 YAML 可一致合并；20 个官方来源对应 20 个唯一规范 URL，42 个 current-YAML atom 均覆盖一次，形成 6 个 `keep`、29 个 `rewrite_conditionally`、7 个 `remove` 决策；generic control unchanged。

## 1. Reconciliation and controls

- Source records: packet 1 = 7, packet 2 = 7, packet 3 = 6; total = **20**. Source IDs are exactly `NEURIPS-S1..S3`, `ICML-S1..S2`, `ICLR-S1..S2`, `ACL-S1..S3`, `CVPR-S1..S4`, `KDD-S1..S2`, `CHI-S1..S4`.
- Official URLs: packet 1 = 7, packet 2 = 7, packet 3 = 6; total = **20 unique** after cross-packet reconciliation (within-packet and cross-packet duplicate count = 0).
- Current YAML: 7 venues × 6 atoms = **42**; every `VENUE-Y0..Y5` appears exactly once in the matrix below. Generic is a control and remains unchanged:
  `This is a rigorous academic venue. Focus on: soundness of methodology, statistical validity, significance of contribution, clarity of writing, and reproducibility of experiments. Be thorough but fair.`
- Decision totals: **`keep` 6; `rewrite_conditionally` 29; `remove` 7; total 42**. `rewrite_conditionally` includes narrowing or adding claim/track/contribution-type conditions; uncertainty is retained from the packets and no new source or web evidence is introduced.

## 2. Current-YAML atom decision matrix (42 rows)

| atom | current YAML atom | decision | source IDs |
|---|---|---|---|
| NEURIPS-Y0 | NeurIPS emphasises theoretical novelty and empirical rigour. | rewrite_conditionally | NEURIPS-S1 |
| NEURIPS-Y1 | novelty beyond incremental improvement | rewrite_conditionally | NEURIPS-S1 |
| NEURIPS-Y2 | solid ablations isolating each contribution | rewrite_conditionally | NEURIPS-S3 |
| NEURIPS-Y3 | correct and complete statistical reporting (mean ± std, seeds) | rewrite_conditionally | NEURIPS-S2 |
| NEURIPS-Y4 | reproducibility (code, hyperparams, compute budget) | rewrite_conditionally | NEURIPS-S2 |
| NEURIPS-Y5 | discussion of limitations and broader impact | rewrite_conditionally | NEURIPS-S2; NEURIPS-S3 |
| ICML-Y0 | ICML values machine-learning methodology with strong theoretical or empirical foundations. | keep | ICML-S1 |
| ICML-Y1 | clear problem formulation | rewrite_conditionally | ICML-S1; ICML-S2 |
| ICML-Y2 | theoretical guarantees or rigorous empirical analysis | rewrite_conditionally | ICML-S1; ICML-S2 |
| ICML-Y3 | comparison to strong, up-to-date baselines | rewrite_conditionally | ICML-S1; ICML-S2 |
| ICML-Y4 | generalisation claims backed by multiple datasets | remove | ICML-S1; ICML-S2 (do not support a universal multi-dataset requirement) |
| ICML-Y5 | clarity and reproducibility | keep | ICML-S1; ICML-S2 |
| ICLR-Y0 | ICLR uses open peer review and rewards reproducible, open-science work. | rewrite_conditionally | ICLR-S1; ICLR-S2 |
| ICLR-Y1 | open-source code (expected, not optional) | remove | ICLR-S2 (code is encouraged, not mandatory) |
| ICLR-Y2 | ablation completeness | remove | ICLR-S1; ICLR-S2 (no universal ablation requirement) |
| ICLR-Y3 | fair comparison (same compute budget, same data splits) | rewrite_conditionally | ICLR-S1 |
| ICLR-Y4 | addressing reviewer comments from prior submissions if applicable | remove | ICLR-S1; ICLR-S2 (no prior-submission requirement) |
| ICLR-Y5 | theoretical insight or strong empirical justification | keep | ICLR-S1 |
| ACL-Y0 | ACL covers Natural Language Processing and Computational Linguistics. | keep | ACL-S1 |
| ACL-Y1 | linguistic validity and task definition | rewrite_conditionally | ACL-S2 |
| ACL-Y2 | comparison to strong NLP baselines (including fine-tuned LLMs) | rewrite_conditionally | ACL-S2 |
| ACL-Y3 | human evaluation where automatic metrics are insufficient | remove | ACL-S2; ACL-S3 (no universal human-evaluation rule) |
| ACL-Y4 | dataset construction quality and annotation agreement | rewrite_conditionally | ACL-S2; ACL-S3 |
| ACL-Y5 | cross-lingual / multilingual scope if applicable | rewrite_conditionally | ACL-S2; ACL-S3 |
| CVPR-Y0 | CVPR covers Computer Vision and Pattern Recognition. | keep | CVPR-S1 |
| CVPR-Y1 | benchmark performance with reproducible protocol | rewrite_conditionally | CVPR-S2; CVPR-S3 |
| CVPR-Y2 | ablation study isolating visual components | remove | CVPR-S1; CVPR-S2; CVPR-S3; CVPR-S4 (no universal component-ablation rule) |
| CVPR-Y3 | qualitative results showing failure modes | rewrite_conditionally | CVPR-S2; CVPR-S3 |
| CVPR-Y4 | comparison on standard benchmarks (ImageNet, COCO, etc.) | remove | CVPR-S1; CVPR-S2; CVPR-S3; CVPR-S4 (no universal named-benchmark rule) |
| CVPR-Y5 | efficiency (FLOPs, params, inference time) reported | rewrite_conditionally | CVPR-S1; CVPR-S3; CVPR-S4 |
| KDD-Y0 | KDD emphasises knowledge discovery and data mining with real-world impact. | rewrite_conditionally | KDD-S1; KDD-S2 |
| KDD-Y1 | scalability to large datasets | rewrite_conditionally | KDD-S1 |
| KDD-Y2 | evaluation on real industrial data (not just academic benchmarks) | rewrite_conditionally | KDD-S2 |
| KDD-Y3 | interpretability / explainability of results | rewrite_conditionally | KDD-S1 |
| KDD-Y4 | practical deployment considerations | rewrite_conditionally | KDD-S2 |
| KDD-Y5 | novelty relative to data mining literature | rewrite_conditionally | KDD-S1; KDD-S2 |
| CHI-Y0 | CHI focuses on Human-Computer Interaction with mixed-methods evaluation. | rewrite_conditionally | CHI-S1; CHI-S2; CHI-S3 |
| CHI-Y1 | user study design (participants, tasks, measures) | rewrite_conditionally | CHI-S2; CHI-S3 |
| CHI-Y2 | ecological validity (lab vs. real-world setting) | rewrite_conditionally | CHI-S3 |
| CHI-Y3 | qualitative analysis rigour (thematic analysis, grounded theory) | rewrite_conditionally | CHI-S2 |
| CHI-Y4 | ethical considerations for human subjects | keep | CHI-S4; CHI-S2 |
| CHI-Y5 | contribution to HCI theory or design guidelines | rewrite_conditionally | CHI-S1; CHI-S2; CHI-S3 |

## 3. Proposed replacement sentences (35, grouped by venue)

Atoms with decision `remove` have no replacement sentence. The following 35 sentences are the packet-proposed, source-grounded replacements; source IDs are retained inline.

### NeurIPS (6)

1. **NEURIPS-Y0** — For the selected NeurIPS contribution type, assess quality, clarity, significance, and originality; do not assume every submission must combine theory and empirical validation. *(NEURIPS-S1)*
2. **NEURIPS-Y1** — Assess originality through new insights, understanding, framings, tasks, metrics, methods, or well-motivated combinations; do not require a wholly new method. *(NEURIPS-S1)*
3. **NEURIPS-Y2** — Request or weigh an ablation only when it would answer a decision-relevant question about a claim, and state that question. *(NEURIPS-S3)*
4. **NEURIPS-Y3** — For experiments supporting the main claims, assess whether uncertainty or statistical significance is reported appropriately and whether variability and its calculation are explained. *(NEURIPS-S2)*
5. **NEURIPS-Y4** — Assess whether the contribution has a reasonable reproducibility path; for experiments, consider code, data or instructions, settings, and compute disclosure, without treating code release as universally mandatory. *(NEURIPS-S2)*
6. **NEURIPS-Y5** — Assess acknowledged limitations and implications; consider negative societal impacts when appropriate to the paper's scope. *(NEURIPS-S2; NEURIPS-S3)*

### ICML (5)

1. **ICML-Y0** — ICML values rigorous machine-learning research whose claims have sound theoretical and/or empirical support. *(ICML-S1)*
2. **ICML-Y1** — Assess whether the problem, contributions, and claims are clearly stated and contextualized. *(ICML-S1; ICML-S2)*
3. **ICML-Y2** — Assess whether the claims are supported by reproducible, well-designed experiments and/or sound theoretical analysis; do not require formal guarantees from every contribution. *(ICML-S1; ICML-S2)*
4. **ICML-Y3** — Assess whether the contribution is situated and distinguished against relevant prior research; require a particular baseline only when it is needed to test a claim. *(ICML-S1; ICML-S2)*
5. **ICML-Y5** — Assess clarity and whether the paper provides enough information and evidence for an expert to understand and reproduce the claimed results. *(ICML-S1; ICML-S2)*

### ICLR (3)

1. **ICLR-Y0** — ICLR uses OpenReview with public reviews and discussion; assess technical correctness, experimental rigor, reproducibility, novelty, claim support, and significance. *(ICLR-S1; ICLR-S2)*
2. **ICLR-Y3** — Assess whether experimental comparisons are rigorous and whether their evidence supports the claims; require matched compute or data splits only when a claim-specific rationale makes them necessary. *(ICLR-S1)*
3. **ICLR-Y5** — Assess whether theoretical or empirical results are correct, scientifically rigorous, and sufficient to support the paper's claims. *(ICLR-S1)*

### ACL (5)

1. **ACL-Y0** — ACL covers Computational Linguistics and Natural Language Processing. *(ACL-S1)*
2. **ACL-Y1** — Assess whether the research question, contribution, key terms, methods, and claims are clear, technically sound, and appropriately scoped. *(ACL-S2)*
3. **ACL-Y2** — Assess comparisons against relevant, sufficiently tuned baselines when they are needed to evaluate the paper's claims; request a particular LLM comparison only when it directly bears on those claims. *(ACL-S2)*
4. **ACL-Y4** — For papers that use or create datasets or human annotations, assess whether data provenance, coverage, statistics, identified quality issues, and annotation procedures are reported or explicitly justified. *(ACL-S2; ACL-S3)*
5. **ACL-Y5** — When language coverage is relevant to the claims, assess whether languages and linguistic/domain coverage are documented and whether generalization claims match that coverage; do not require multilingual evaluation merely because a study is monolingual. *(ACL-S2; ACL-S3)*

### CVPR (4)

1. **CVPR-Y0** — CVPR covers computer vision and pattern recognition. *(CVPR-S1)*
2. **CVPR-Y1** — Assess technical soundness and contribution, interpret benchmark results alongside novelty and impact, and consider whether the reported method and results are reproducible; do not require state-of-the-art performance. *(CVPR-S2; CVPR-S3)*
3. **CVPR-Y3** — Consider an honest discussion of limitations positively; do not require a separate limitations section or treat its absence alone as a rejection reason. *(CVPR-S2; CVPR-S3)*
4. **CVPR-Y5** — Only when a paper makes an efficiency or scalability claim, assess whether the evidence supports that claim; the CVPR 2026 compute report is not visible to reviewers and does not affect acceptance decisions. *(CVPR-S1; CVPR-S3; CVPR-S4)*

### KDD (6)

1. **KDD-Y0** — KDD covers knowledge discovery, data science, and AI; apply Research-track criteria to research papers and ADS criteria only to ADS submissions. *(KDD-S1; KDD-S2)*
2. **KDD-Y1** — When a paper makes scalability or large-scale-systems claims, assess whether its execution and evidence support those claims; do not require large-dataset experiments of every KDD paper. *(KDD-S1)*
3. **KDD-Y2** — For ADS submissions, assess evidence of live deployment and quantified post-launch performance, or the documented barriers and broadly applicable lessons allowed by the stated exception; do not impose this requirement on Research-track papers. *(KDD-S2)*
4. **KDD-Y3** — When interpretability or explainability is part of the claimed contribution, assess its technical merit, execution, and evidence; do not treat it as a universal requirement. *(KDD-S1)*
5. **KDD-Y4** — For ADS submissions, assess design tradeoffs, deployment challenges, post-launch evidence, and lessons learned; do not impose ADS deployment criteria on Research-track papers. *(KDD-S2)*
6. **KDD-Y5** — For Research-track papers, assess originality and innovative technical contribution in relation to relevant work; for ADS papers, recognize that novelty may lie in the application domain, engineering design, usability, or business use case. *(KDD-S1; KDD-S2)*

### CHI (6)

1. **CHI-Y0** — CHI evaluates original contributions to HCI; assess rigor and evidence according to the contribution type rather than requiring mixed methods. *(CHI-S1; CHI-S2; CHI-S3)*
2. **CHI-Y1** — For work involving users or human participants, assess whether the relevant population, tasks or instruments, procedures, measures, and analysis are transparently reported and justified; do not require a user study for every contribution. *(CHI-S2; CHI-S3)*
3. **CHI-Y2** — When claims depend on a proposed setting or context, assess whether the setting, tasks, users, obstacles, and chosen validation support those claims; do not impose a universal lab-versus-field requirement. *(CHI-S3)*
4. **CHI-Y3** — For qualitative research, assess transparent justification of its conceptual basis, participant or site selection, data collection and analysis, theme construction, researcher positionality, and potential bias; do not require a named method such as thematic analysis or grounded theory. *(CHI-S2)*
5. **CHI-Y4** — For research involving human subjects, assess compliance with applicable ethics-review requirements and disclosure of the institutional context; for qualitative research, separately assess transparent treatment of anonymity, privacy, consent, and data use. *(CHI-S4; CHI-S2)*
6. **CHI-Y5** — Assess whether the paper makes an original and significant contribution to HCI according to its contribution type; require theoretical or design implications only when they are part of the claimed contribution. *(CHI-S1; CHI-S2; CHI-S3)*

## 4. Verification result

- **PASS** — 42 matrix rows; unique atom IDs = 42; duplicate atom IDs = 0; missing current atoms = 0.
- **PASS** — 35 replacement sentences; venue counts = NeurIPS 6, ICML 5, ICLR 3, ACL 5, CVPR 4, KDD 6, CHI 6.
- **PASS** — all referenced source IDs exist in packet 1–3; unknown source IDs = 0.
- **PASS** — 20 source IDs and 20 unique official URLs; cross-packet URL duplicates = 0.
- **PASS** — generic unchanged control retained; no edits to YAML, plan, protocol, methodology, detached hashes, or files outside the source-audit documents.
