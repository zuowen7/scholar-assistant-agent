from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
SCHEMA_DIR = BASE_DIR / "schemas"
VERIFY_PATH = BASE_DIR / "scripts" / "verify_freeze.py"

_SPEC = importlib.util.spec_from_file_location(
    "reviewer_validation_verify_freeze", VERIFY_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
verify = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = verify
_SPEC.loader.exec_module(verify)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(path: str, data: bytes = b"x") -> dict[str, object]:
    return {"path": path, "sha256": _sha(data), "byte_length": len(data)}


def _attempt(status: str = "success") -> dict[str, object]:
    prompt = b"prompt"
    request = b'{"prompt":"prompt"}'
    response = b"[]"
    parsed = b"[]"
    return {
        "attempt_number": 1,
        "started_at": "2026-08-28T00:00:00Z",
        "ended_at": "2026-08-28T00:00:01Z",
        "status": status,
        "prompt": _artifact(
            "methods/reviewer_validation/outputs/pilot/prompt.txt", prompt
        ),
        "request": _artifact(
            "methods/reviewer_validation/outputs/pilot/request.json", request
        ),
        "raw_response": _artifact(
            "methods/reviewer_validation/outputs/pilot/response.txt", response
        ),
        "parsed_output": _artifact(
            "methods/reviewer_validation/outputs/pilot/parsed.json", parsed
        ),
        "error": None
        if status in {"success", "legal_empty"}
        else {"type": status, "message_redacted": "synthetic failure"},
    }


def _step(phase: str) -> dict[str, object]:
    attempt = _attempt()
    return {
        "step_id": f"step-{phase}",
        "phase": phase,
        "inputs": {
            "excerpt": _artifact(
                "methods/reviewer_validation/outputs/pilot/excerpt.txt", b"excerpt"
            ),
            "excerpt_coverage": {
                "source_characters": 100,
                "visible_characters": 7,
                "truncated": True,
            },
            "prompt": copy.deepcopy(attempt["prompt"]),
            "profile": None,
            "gold_promises": None,
        },
        "attempts": [attempt],
        "termination": {"status": "success", "attempt_count": 1, "error": None},
    }


def _ledger_record(stage: str = "extraction") -> dict[str, object]:
    phases = {
        "extraction": ["extraction"],
        "gold_conditioned_status": ["discharge_classification"],
        "end_to_end": ["extraction", "discharge_classification"],
    }[stage]
    checks = {
        "extraction": ["extraction"],
        "gold_conditioned_status": ["discharge_classification"],
        "end_to_end": ["extraction", "discharge_classification"],
    }[stage]
    steps = [_step(phase) for phase in phases]
    if stage == "gold_conditioned_status":
        steps[0]["inputs"]["gold_promises"] = _artifact(
            "methods/reviewer_validation/outputs/pilot/gold_promises.json", b"[]"
        )
    return {
        "schema_version": "reviewer-validation-run-record/v1",
        "record_id": "ledger-record-1",
        "run_id": "run-1",
        "experiment": "rq1_ledger",
        "stage": stage,
        "condition": "not_applicable",
        "paper_id": "paper-1",
        "pair_id": None,
        "venue_label": None,
        "checks": checks,
        "protocol_version": "0.1.0-draft",
        "protocol_sha256": "0" * 64,
        "code_commit": "0" * 40,
        "started_at": "2026-08-28T00:00:00Z",
        "ended_at": "2026-08-28T00:00:02Z",
        "provider": {
            "name": "synthetic",
            "api_format": "controlled-fixture",
            "client_count": 1,
            "fallback_call_count": 0,
        },
        "model": {"id": "synthetic-model", "snapshot": None},
        "generation": {
            "temperature": 0.0,
            "max_tokens": 10,
            "thinking_mode": None,
            "seed": 1,
            "json_mode": True,
        },
        "steps": steps,
        "output": _artifact(
            "methods/reviewer_validation/outputs/pilot/output.json", b"[]"
        ),
        "termination": {
            "status": "success",
            "attempt_count": len(steps),
            "error": None,
        },
        "denominators": {
            "planned_invocations": 1,
            "primary_unit": "paper",
            "gold_occurrences": 1,
            "prediction_occurrences": 1,
            "applicable_criteria": None,
            "critique_units": None,
        },
    }


def _venue_record() -> dict[str, object]:
    record = _ledger_record("extraction")
    step = _step("venue_review")
    step["inputs"]["profile"] = _artifact(
        "methods/reviewer_validation/outputs/pilot/profile.txt", b"profile"
    )
    record.update(
        {
            "record_id": "venue-record-1",
            "experiment": "rq3_venue",
            "stage": "venue_llm",
            "condition": "generic",
            "pair_id": "pair-1",
            "venue_label": "NeurIPS",
            "checks": ["llm"],
            "steps": [step],
            "termination": {"status": "success", "attempt_count": 1, "error": None},
            "denominators": {
                "planned_invocations": 1,
                "primary_unit": "review",
                "gold_occurrences": None,
                "prediction_occurrences": None,
                "applicable_criteria": 4,
                "critique_units": 2,
            },
        }
    )
    return record


def _copy_scaffold(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    base = repo / "methods" / "reviewer_validation"
    base.parent.mkdir(parents=True)
    shutil.copytree(BASE_DIR, base)
    shutil.copy2(REPO_ROOT / "METHODOLOGY.md", repo / "METHODOLOGY.md")
    return repo, base


def _rewrite_manifest(base: Path, manifest: dict[str, object]) -> None:
    path = base / "freeze_manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    digest = _sha(path.read_bytes())
    (base / "freeze_manifest.sha256").write_text(
        f"{digest}  freeze_manifest.json\n", encoding="ascii"
    )


def test_protocol_fidelity_to_canonical_methodology() -> None:
    protocol = yaml.safe_load((BASE_DIR / "protocol.yaml").read_text(encoding="utf-8"))
    assert [rq["id"] for rq in protocol["research_questions"]] == ["RQ1", "RQ2", "RQ3"]
    assert protocol["sample_design"]["master_corpus_papers"] == 16
    assert protocol["sample_design"]["development_papers"] == 2
    assert protocol["sample_design"]["held_out_papers"] == 14
    assert protocol["sample_design"]["ledger_subset_papers"] == 10
    assert protocol["execution"]["runs_per_llm_stage"] == 3
    assert protocol["sample_design"]["status_challenge"] == {
        "base_groups": 20,
        "variants_per_group": 4,
        "total_cases": 80,
        "states": ["paid", "partial", "unpaid", "mismatch"],
    }
    assert protocol["sample_design"]["anchor_challenge"]["total_cases"] == 120
    rq3 = protocol["research_questions"][2]
    assert (rq3["blind_pairs"], rq3["total_reviews"]) == (42, 84)
    assert protocol["analysis"]["bootstrap_iterations"] == 10_000
    assert protocol["analysis"]["rq3_claim_gates"][
        "unsupported_rate_one_sided_ci_upper"
    ] == {
        "operator": "less_than",
        "value": 0.05,
    }
    assert protocol["coordinate_contract"]["interval"] == "half_open"
    assert (
        protocol["execution"]["retry_policy"]["cross_provider_fallback_allowed"]
        is False
    )
    assert protocol["execution"]["code_commit"] is None
    assert protocol["status"] == "draft"
    assert protocol["formal_run_authorized"] is False


def test_all_declared_schemas_are_valid_draft_2020_12() -> None:
    for schema_id in verify.SCHEMA_ID_TO_FILE:
        schema = verify.load_schema(SCHEMA_DIR, schema_id)
        assert schema["$id"] == schema_id
    with pytest.raises(ValueError, match="unknown schema version"):
        verify.load_schema(SCHEMA_DIR, "reviewer-validation-unknown/v9")


def test_run_record_accepts_minimal_ledger_and_venue_consumers() -> None:
    for record in (
        _ledger_record(),
        _ledger_record("gold_conditioned_status"),
        _ledger_record("end_to_end"),
        _venue_record(),
    ):
        assert (
            verify.validate_instance(
                record, "reviewer-validation-run-record/v1", SCHEMA_DIR
            )
            == []
        )
    early_stop = _ledger_record("end_to_end")
    early_stop["steps"] = early_stop["steps"][:1]
    early_stop["termination"] = {
        "status": "legal_empty",
        "attempt_count": 1,
        "error": None,
    }
    assert (
        verify.validate_instance(
            early_stop, "reviewer-validation-run-record/v1", SCHEMA_DIR
        )
        == []
    )


def test_run_record_rejects_missing_termination_unknown_enum_and_secrets() -> None:
    missing = _ledger_record()
    del missing["termination"]
    assert any(
        "termination" in error
        for error in verify.validate_instance(
            missing, "reviewer-validation-run-record/v1", SCHEMA_DIR
        )
    )
    unknown = _ledger_record()
    unknown["steps"][0]["attempts"][0]["status"] = "mysterious"
    assert any(
        "mysterious" in error
        for error in verify.validate_instance(
            unknown, "reviewer-validation-run-record/v1", SCHEMA_DIR
        )
    )
    secret = _ledger_record()
    secret["api_key"] = "redacted"
    errors = verify.validate_instance(
        secret, "reviewer-validation-run-record/v1", SCHEMA_DIR
    )
    assert any("secret-like field" in error for error in errors)
    suffixed_secret = _ledger_record()
    suffixed_secret["openai_api_key"] = "redacted"
    errors = verify.validate_instance(
        suffixed_secret, "reviewer-validation-run-record/v1", SCHEMA_DIR
    )
    assert any("secret-like field" in error for error in errors)


def test_run_record_enforces_stage_inputs_failure_details_and_artifact_boundary() -> (
    None
):
    missing_gold = _ledger_record("gold_conditioned_status")
    missing_gold["steps"][0]["inputs"]["gold_promises"] = None
    assert any(
        "required for gold-conditioned" in error
        for error in verify.validate_instance(
            missing_gold, "reviewer-validation-run-record/v1", SCHEMA_DIR
        )
    )
    missing_profile = _venue_record()
    missing_profile["steps"][0]["inputs"]["profile"] = None
    assert any(
        "required for venue" in error
        for error in verify.validate_instance(
            missing_profile, "reviewer-validation-run-record/v1", SCHEMA_DIR
        )
    )
    failed_without_error = _ledger_record()
    failed_without_error["steps"][0]["attempts"][0]["status"] = "provider_error"
    assert verify.validate_instance(
        failed_without_error, "reviewer-validation-run-record/v1", SCHEMA_DIR
    )
    escaped = _ledger_record()
    escaped["output"]["path"] = "outside/output.json"
    assert verify.validate_instance(
        escaped, "reviewer-validation-run-record/v1", SCHEMA_DIR
    )


def test_promise_semantics_reject_quote_mismatch_bounds_and_synthetic_mapping() -> None:
    full = b"Alpha promise. Evidence follows."
    excerpt = b"Alpha promise."
    mapping = {
        "schema_version": "reviewer-validation-coordinate-map/v1",
        "full_text_artifact_id": "full",
        "full_text_sha256": _sha(full),
        "excerpt_artifact_id": "excerpt",
        "excerpt_sha256": _sha(excerpt),
        "segments": [
            {
                "kind": "source",
                "excerpt_start": 0,
                "excerpt_end": len(excerpt.decode()),
                "full_text_start": 0,
                "full_text_end": len(excerpt.decode()),
                "source_section": "abstract",
            }
        ],
    }
    mapping_bytes = json.dumps(mapping, sort_keys=True).encode()
    blobs = {"full": full, "excerpt": excerpt, "mapping": mapping_bytes}
    resolver = blobs.__getitem__
    record = {
        "schema_version": "reviewer-validation-promise-gold/v1",
        "promise_id": "p1",
        "paper_id": "paper-1",
        "exact_quote": "Alpha",
        "full_text": {
            "artifact_id": "full",
            "text_sha256": _sha(full),
            "char_start": 0,
            "char_end": 5,
        },
        "excerpt": {
            "artifact_id": "excerpt",
            "excerpt_id": "promise",
            "text_sha256": _sha(excerpt),
            "char_start": 0,
            "char_end": 5,
        },
        "mapping": {"artifact_id": "mapping", "sha256": _sha(mapping_bytes)},
        "kind": "claim",
        "status": "unpaid",
        "gold_evidence_spans": [],
        "annotator_id": "A",
        "resolution": "resolved",
        "note": "none visible",
        "denominators": {"gold_occurrence": 1, "evidence_bearing": False},
    }
    assert (
        verify.validate_instance(
            record, "reviewer-validation-promise-gold/v1", SCHEMA_DIR, resolver
        )
        == []
    )
    bad_quote = copy.deepcopy(record)
    bad_quote["exact_quote"] = "Omega"
    assert any(
        "exact_quote" in error
        for error in verify.validate_instance(
            bad_quote, "reviewer-validation-promise-gold/v1", SCHEMA_DIR, resolver
        )
    )
    bad_bounds = copy.deepcopy(record)
    bad_bounds["full_text"]["char_end"] = 0
    assert verify.validate_instance(
        bad_bounds, "reviewer-validation-promise-gold/v1", SCHEMA_DIR, resolver
    )
    synthetic = copy.deepcopy(mapping)
    synthetic["segments"][0]["kind"] = "synthetic"
    synthetic_bytes = json.dumps(synthetic, sort_keys=True).encode()
    blobs["mapping"] = synthetic_bytes
    synthetic_record = copy.deepcopy(record)
    synthetic_record["mapping"]["sha256"] = _sha(synthetic_bytes)
    errors = verify.validate_instance(
        synthetic_record, "reviewer-validation-promise-gold/v1", SCHEMA_DIR, resolver
    )
    assert any("synthetic mapping" in error for error in errors)


def test_anchor_schema_rejects_unknown_state_and_quote_mismatch() -> None:
    transformed = b"prefix target suffix"
    resolver = {"transformed": transformed}.__getitem__
    record = {
        "schema_version": "reviewer-validation-anchor-case/v1",
        "case_id": "a1-anchored",
        "source_anchor_id": "a1",
        "cluster_id": "a1",
        "variant": "anchored",
        "gold_status": "anchored",
        "source_quote": "target",
        "transformed_text": {"artifact_id": "transformed", "sha256": _sha(transformed)},
        "gold_quote": "target",
        "gold_span": {"char_start": 7, "char_end": 13},
        "transformation": {
            "operation": "insert_before",
            "description": "prefix inserted",
        },
        "generator_seed": 7,
        "item_input_sha256": "1" * 64,
        "denominators": {"variant_occurrence": 1, "source_anchor_cluster": 1},
    }
    assert (
        verify.validate_instance(
            record, "reviewer-validation-anchor-case/v1", SCHEMA_DIR, resolver
        )
        == []
    )
    unknown = copy.deepcopy(record)
    unknown["gold_status"] = "unknown"
    assert verify.validate_instance(
        unknown, "reviewer-validation-anchor-case/v1", SCHEMA_DIR, resolver
    )
    mismatch = copy.deepcopy(record)
    mismatch["gold_quote"] = "wrong!"
    assert any(
        "transformed text slice" in error
        for error in verify.validate_instance(
            mismatch, "reviewer-validation-anchor-case/v1", SCHEMA_DIR, resolver
        )
    )
    wrong_operation = copy.deepcopy(record)
    wrong_operation["transformation"]["operation"] = "paraphrase"
    assert verify.validate_instance(
        wrong_operation, "reviewer-validation-anchor-case/v1", SCHEMA_DIR, resolver
    )
    wrong_cluster = copy.deepcopy(record)
    wrong_cluster["cluster_id"] = "different-source"
    assert any(
        "source_anchor_id" in error
        for error in verify.validate_instance(
            wrong_cluster, "reviewer-validation-anchor-case/v1", SCHEMA_DIR, resolver
        )
    )


def test_venue_score_requires_and_recomputes_denominators() -> None:
    packet = b"blind packet"
    record = {
        "schema_version": "reviewer-validation-venue-review-score/v1",
        "score_id": "s1",
        "pair_id": "pair-1",
        "paper_id": "paper-1",
        "rater_id": "A",
        "applicability_gold_sha256": "2" * 64,
        "blind_packet": {"artifact_id": "packet", "sha256": _sha(packet)},
        "criteria": [
            {
                "criterion_id": "C1",
                "side": "A",
                "applicability": "applicable",
                "score": 2,
                "evidence_note": "located",
            },
            {
                "criterion_id": "C1",
                "side": "B",
                "applicability": "applicable",
                "score": 1,
                "evidence_note": "generic",
            },
            {
                "criterion_id": "C2",
                "side": "A",
                "applicability": "not_applicable",
                "score": None,
                "evidence_note": "conditional",
            },
            {
                "criterion_id": "C2",
                "side": "B",
                "applicability": "not_applicable",
                "score": None,
                "evidence_note": "conditional",
            },
        ],
        "critique_units": [
            {
                "critique_id": "q1",
                "side": "A",
                "text": "claim",
                "label": "supported",
                "excerpt_support_note": "line 1",
            }
        ],
        "preference": "A",
        "denominators": {
            "criteria_defined": 2,
            "review_sides": 2,
            "criterion_rows": 4,
            "applicable_criteria_per_review": 1,
            "scored_criterion_occurrences": 2,
            "criteria_max_points_per_review": 2,
            "supported_critique_units": 1,
            "unsupported_critique_units": 0,
            "not_assessable_critique_units": 0,
            "fact_claim_critique_units": 1,
            "preference_label": 1,
        },
        "note": "",
    }
    assert (
        verify.validate_instance(
            record, "reviewer-validation-venue-review-score/v1", SCHEMA_DIR
        )
        == []
    )
    missing = copy.deepcopy(record)
    del missing["denominators"]["criteria_defined"]
    assert verify.validate_instance(
        missing, "reviewer-validation-venue-review-score/v1", SCHEMA_DIR
    )
    wrong = copy.deepcopy(record)
    wrong["denominators"]["criteria_max_points_per_review"] = 4
    assert any(
        "criteria_max_points_per_review" in error
        for error in verify.validate_instance(
            wrong, "reviewer-validation-venue-review-score/v1", SCHEMA_DIR
        )
    )
    missing_side = copy.deepcopy(record)
    missing_side["criteria"] = missing_side["criteria"][:-1]
    assert any(
        "once for each side" in error
        for error in verify.validate_instance(
            missing_side, "reviewer-validation-venue-review-score/v1", SCHEMA_DIR
        )
    )


def test_hash_is_deterministic_and_one_byte_tamper_fails(tmp_path: Path) -> None:
    target = tmp_path / "raw.jsonl"
    detached = tmp_path / "raw.sha256"
    target.write_bytes(b'{"label":"A"}\n')
    first = verify.sha256_file(target)
    second = verify.sha256_file(target)
    assert first == second
    detached.write_text(f"{first}  raw.jsonl\n", encoding="ascii")
    assert verify.verify_detached_hash(target, detached) == []
    target.write_bytes(target.read_bytes() + b" ")
    assert any(
        "mismatch" in error for error in verify.verify_detached_hash(target, detached)
    )


def test_draft_verifier_passes_but_formal_guard_fails_closed() -> None:
    draft = verify.verify_repository(
        allow_draft=True, base_dir=BASE_DIR, repo_root=REPO_ROOT
    )
    assert draft.ok, draft.errors
    assert draft.pending_artifacts
    assert draft.formal_run_authorized is False
    strict = verify.verify_repository(
        allow_draft=False, base_dir=BASE_DIR, repo_root=REPO_ROOT
    )
    assert not strict.ok
    assert strict.formal_run_authorized is False
    assert any("protocol status is draft" in error for error in strict.errors)
    assert any("unfrozen seed slot" in error for error in strict.errors)
    assert any(
        "unfrozen execution slot: code_commit" in error for error in strict.errors
    )
    assert any(
        "artifact anchor_challenges: missing" in error for error in strict.errors
    )
    with pytest.raises(verify.FreezeVerificationError, match="formal run blocked"):
        verify.require_formal_run_ready(base_dir=BASE_DIR, repo_root=REPO_ROOT)


def test_manifest_rejects_duplicate_ids_unknown_schema_and_boundary_escape(
    tmp_path: Path,
) -> None:
    repo, base = _copy_scaffold(tmp_path)
    manifest = json.loads((base / "freeze_manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"].append(copy.deepcopy(manifest["artifacts"][0]))
    _rewrite_manifest(base, manifest)
    report = verify.verify_repository(allow_draft=True, base_dir=base, repo_root=repo)
    assert not report.ok
    assert any("duplicate artifact ID" in error for error in report.errors)

    repo, base = _copy_scaffold(tmp_path / "unknown")
    manifest = json.loads((base / "freeze_manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["schema_id"] = "reviewer-validation-unknown/v9"
    _rewrite_manifest(base, manifest)
    report = verify.verify_repository(allow_draft=True, base_dir=base, repo_root=repo)
    assert any("schema_id" in error for error in report.errors)

    repo, base = _copy_scaffold(tmp_path / "escape")
    manifest = json.loads((base / "freeze_manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["path"] = "../outside.txt"
    _rewrite_manifest(base, manifest)
    report = verify.verify_repository(allow_draft=True, base_dir=base, repo_root=repo)
    assert any("path" in error for error in report.errors)


def test_raw_artifact_hash_is_immutable_after_first_listing(tmp_path: Path) -> None:
    repo, base = _copy_scaffold(tmp_path)
    raw_path = base / "annotations" / "raw" / "ledger_A.jsonl"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"first immutable bytes\n")
    manifest = json.loads((base / "freeze_manifest.json").read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"] if item["artifact_id"] == "ledger_raw_A"
    )
    artifact.update(
        {
            "sha256": _sha(raw_path.read_bytes()),
            "byte_length": len(raw_path.read_bytes()),
            "schema_id": None,
            "record_count": 1,
            "created_at": "2026-08-28T00:00:00Z",
            "status": "verified",
        }
    )
    _rewrite_manifest(base, manifest)
    before = verify.verify_repository(allow_draft=True, base_dir=base, repo_root=repo)
    assert before.ok, before.errors
    raw_path.write_bytes(b"first immutable bytes!\n")
    after = verify.verify_repository(allow_draft=True, base_dir=base, repo_root=repo)
    assert any("ledger_raw_A: SHA-256 mismatch" in error for error in after.errors)
