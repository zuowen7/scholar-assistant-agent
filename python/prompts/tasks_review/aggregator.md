# Aggregator Prompt (used by run_review_parallel)
Three reviewer perspectives are merged by aggregate_perspectives():
- method: methodology & soundness angle
- experiment: baseline & evaluation angle
- writing: clarity & presentation angle

Deduplication: points with identical (title.lower(), category) across perspectives
are merged into the first occurrence. Order: method → experiment → writing.
