# Reviewer Validation execution scaffold

结论：本目录已有可审计的 `draft` protocol、开发语料与零网络模型筛选入口；当前只允许完成 A/B 开发语料审计，审计锁定前 DeepSeek 调用会失败关闭，held-out 与正式运行继续禁止。

## Development model screen

- `inputs/development/manifest.yaml` 固定两篇开发论文、解析结果、production excerpts 与来源/代码 hash；`model_selection.yaml` 固定 Pro/Flash 的 8 对、16 次逻辑调用和盲评规则。
- A、B 先分别填写 `inputs/development/human_audit/annotator_A.yaml` 与 `annotator_B.yaml`；协调者核验并写入 hash 后，付费运行才可能通过预检。
- 零费用检查：`python ../methods/reviewer_validation/scripts/run_model_selection.py preflight`。当前预期结果为 `ready_for_paid_execution: false`，且 `network_calls: 0`。
- 多模型筛选不计入 G1；选定单一模型后仍须重跑 development pilot。任何 held-out/formal runner 仍受 strict freeze gate 阻断。

## Authority and scope

- `../../METHODOLOGY.md` is the canonical research design. This directory only implements its execution contract.
- `IMPLEMENTATION_PLAN.md` defines file ownership and the sanctioned first-round work packages.
- The checked-in scaffold is deliberately `draft`: corpus, labels, challenge cases, model configuration, seeds, mappings, and several hashes are not yet frozen.
- Passing unit tests or `--allow-draft` proves structure only. It is not G1, G2, or an empirical result.

## Freeze states

1. **Draft validation** checks schema versions, detached hashes, path boundaries, duplicate IDs, any hashes that are already supplied, secret-like fields, and the structural contract. Missing formal artifacts are reported as pending but do not make this command fail:

   ```powershell
   Set-Location python
   python ../methods/reviewer_validation/scripts/verify_freeze.py --allow-draft
   ```

2. **Strict validation** is the mandatory precondition for every formal runner. It fails until the protocol and manifest are marked `frozen`, the exact 40-character execution commit plus all seed/model slots are concrete, all required inputs exist, every artifact is individually listed, immutable, schema-valid, and hash-valid, and `formal_run_authorized` is true:

   ```powershell
   Set-Location python
   python ../methods/reviewer_validation/scripts/verify_freeze.py
   ```

3. A formal runner must call `require_formal_run_ready()` from `scripts/verify_freeze.py` immediately before reading formal inputs. `--allow-draft` must never be used by a formal runner. There is no override flag and the verifier never repairs or rewrites an input.

## Immutable-data rule

- Source papers, first parsed text, A/B raw labels, adjudicated gold, official-source snapshots, mappings, challenge cases, prompts, profiles, schemas, seeds, and run configuration are formal inputs.
- Each is listed with a repository-relative POSIX path, byte length, SHA-256, schema ID where applicable, and `immutable: true`.
- Raw and frozen files are never reformatted or edited in place. Corrections create a new artifact plus a protocol amendment; affected formal conditions are rerun from the start.
- Outputs are not part of the pre-run freeze. Their first-write hashes are appended to `run_manifest.jsonl`; an earlier record is never overwritten or replaced by a retry.

## Schemas

- `protocol.schema.json`: exact pre-registered design constants and draft/frozen slots.
- `freeze_manifest.schema.json`: detached, non-self-referential artifact inventory.
- `promise_gold.schema.json`: dual-coordinate Promise/evidence annotations.
- `anchor_case.schema.json`: one frozen transformed Anchor case.
- `venue_applicability.schema.json`: stage-one applicability labels.
- `venue_review_score.schema.json`: blinded stage-two review scores for both A/B sides, paired criterion identity, critique labels, and per-review denominators.
- `run_record.schema.json`: common Ledger/Venue attempt and termination record, including the one logical provider/API format, stage-specific gold/profile inputs, every attempt, and output references confined to this directory.

JSON Schema handles structure and enums. The verifier adds cross-file checks that JSON Schema cannot express: half-open bounds, quote-to-source slices, mapping identity, rejection of synthetic mapping spans, denominator arithmetic, duplicate IDs, path containment, secret-like fields, and content hashes.

## Sanctioned C-package checks

```powershell
Set-Location python
python -m pytest ../methods/reviewer_validation/tests/test_protocol_scaffold.py -q
python ../methods/reviewer_validation/scripts/verify_freeze.py --allow-draft
python ../methods/reviewer_validation/scripts/verify_freeze.py
```

The final command is expected to return non-zero in this scaffold stage. Do not start held-out work, generate the formal 80/120 challenge sets, or run Anchor until the coordinator accepts C1-C6 and later completes G1-G4.
