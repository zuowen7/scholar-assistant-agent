# Development corpus audit

结论：A、B 必须先独立确认两篇论文无团队作者冲突，且 PDF、解析正文和三类 production excerpt 可读；两份记录锁定前，模型筛选不会发出请求。

1. A 填写 `annotator_A.yaml`，B 填写 `annotator_B.yaml`，不要互相复制结论，也不要用 LLM 代填。
   `../raw/`、`../parsed/` 和 `../excerpts/` 已随仓库提供，拉取后即可直接核对。
2. 对每篇论文打开 `../raw/<paper_id>.pdf`，并核对 `../parsed/<paper_id>.txt` 与 `../excerpts/<paper_id>.*.txt`。
3. 只有实际检查通过的布尔项才填 `true`；任何会改变主要论点、方法、结果或局限理解的解析问题写入 `material_issues`，并把 `overall_decision` 设为 `fail`。
4. 全部通过时，将 `independent_review_complete` 设为 `true`、`overall_decision` 设为 `pass`，填写姓名或缩写及日期。不要自行修改 `manifest.yaml` 或运行付费命令。
5. 两人完成后交回协调者计算 SHA-256、锁定 manifest 状态并重跑零费用 preflight。
