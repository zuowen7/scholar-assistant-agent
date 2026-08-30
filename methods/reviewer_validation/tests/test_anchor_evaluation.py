from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
SCRIPTS = BASE_DIR / "scripts"
DEV_SOURCES = BASE_DIR / "outputs" / "pilot" / "anchor" / "dev_sources.jsonl"
DEV_SEED = BASE_DIR / "outputs" / "pilot" / "anchor" / "dev_seed.txt"


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = _load("generate_challenges.py", "test_anchor_generator")
scorer = _load("score_anchor.py", "test_anchor_scorer")
runner = _load("run_anchor.py", "test_anchor_runner")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _configure_temp_base(monkeypatch: pytest.MonkeyPatch, base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(generator, "BASE_DIR", base)
    monkeypatch.setattr(generator, "REPO_ROOT", base.parents[1])
    monkeypatch.setattr(runner, "BASE_DIR", base)
    monkeypatch.setattr(runner, "REPO_ROOT", base.parents[1])
    (base / "protocol.yaml").write_bytes((BASE_DIR / "protocol.yaml").read_bytes())


def test_generator_is_byte_deterministic_and_input_sensitive(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "repo" / "methods" / "reviewer_validation"
    _configure_temp_base(monkeypatch, base)
    source_one = base / "pilot-one" / "dev_sources.jsonl"
    source_one.parent.mkdir(parents=True)
    source_one.write_bytes(DEV_SOURCES.read_bytes())
    seed = base / "pilot-one" / "dev_seed.txt"
    seed.write_bytes(DEV_SEED.read_bytes())

    first = generator.generate_anchor_challenges(
        mode="dev", sources_path=source_one, seed_path=seed, output_dir=base / "out-one"
    )
    second = generator.generate_anchor_challenges(
        mode="dev", sources_path=source_one, seed_path=seed, output_dir=base / "out-two"
    )
    assert first["artifact_tree_sha256"] == second["artifact_tree_sha256"]
    assert first["artifact_tree_sha256"] == _jsonl(
        base / "out-one" / "anchor_cases.jsonl"
    )[0].get("not_a_field", first["artifact_tree_sha256"])
    first_files = {
        path.relative_to(base / "out-one").as_posix(): path.read_bytes()
        for path in (base / "out-one").rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(base / "out-two").as_posix(): path.read_bytes()
        for path in (base / "out-two").rglob("*")
        if path.is_file()
    }
    assert first_files == second_files

    changed_source = base / "pilot-two" / "dev_sources.jsonl"
    changed_source.parent.mkdir(parents=True)
    changed_source.write_bytes(
        DEV_SOURCES.read_bytes().replace(b"Prelude. ", b"Prelude! ", 1)
    )
    changed_seed = base / "pilot-two" / "dev_seed.txt"
    changed_seed.write_bytes(DEV_SEED.read_bytes())
    changed = generator.generate_anchor_challenges(
        mode="dev",
        sources_path=changed_source,
        seed_path=changed_seed,
        output_dir=base / "out-changed",
    )
    assert changed["artifact_tree_sha256"] != first["artifact_tree_sha256"]
    original_items = {
        item["case_id"]: item["item_input_sha256"]
        for item in _jsonl(base / "out-one" / "anchor_cases.jsonl")
    }
    changed_items = {
        item["case_id"]: item["item_input_sha256"]
        for item in _jsonl(base / "out-changed" / "anchor_cases.jsonl")
    }
    assert original_items.keys() == changed_items.keys()
    assert all(original_items[key] != changed_items[key] for key in original_items)


def _formal_source(index: int, stratum: str) -> dict:
    quote = f"target phrase {index}"
    text = f"Document {index} preface. {quote} remains supported by surrounding context. End."
    start = text.index(quote)
    end = start + len(quote)
    boundary_tags = []
    if stratum == "heading_boundary":
        boundary_tags = [["near_heading"], ["document_start"], ["document_end"]][
            index % 3
        ]
    source_id = f"formal-{index:02d}"
    return {
        "schema_version": "reviewer-validation-anchor-source/v1",
        "source_anchor_id": source_id,
        "doc_id": f"doc-{index:02d}",
        "primary_stratum": stratum,
        "cross_tags": [stratum],
        "boundary_tags": boundary_tags,
        "source_text": text,
        "source_text_sha256": _sha(text.encode()),
        "anchor": {
            "id": source_id,
            "doc_id": f"doc-{index:02d}",
            "char_start": start,
            "char_end": end,
            "quote": quote,
            "context_before": text[max(0, start - 48) : start],
            "context_after": text[end : end + 48],
            "section_path": None,
            "status": "anchored",
        },
        "transform_inputs": {
            "insert_text": "Inserted preface. ",
            "delete_before_chars": 4,
            "move_separator": "\n",
            "drifted_quotes": {
                "local_rewrite": f"target wording {index}",
                "substitution": f"objective phrase {index}",
                "paraphrase": f"research objective number {index}",
            },
            "similar_distractor": f"A target-like phrase number {index} appears elsewhere.",
        },
        "development_only": False,
    }


def test_formal_generator_enforces_40_by_3_schema_and_operation_quotas(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "repo" / "methods" / "reviewer_validation"
    _configure_temp_base(monkeypatch, base)
    challenges = base / "challenges"
    seeds = base / "configs" / "seeds"
    challenges.mkdir(parents=True)
    seeds.mkdir(parents=True)
    strata = [stratum for stratum in sorted(generator.PRIMARY_STRATA) for _ in range(8)]
    sources = [_formal_source(index, stratum) for index, stratum in enumerate(strata)]
    source_path = challenges / "anchor_sources.jsonl"
    source_path.write_bytes(b"".join(generator._json_bytes(item) for item in sources))
    seed_path = seeds / "anchor_challenge.txt"
    seed_path.write_text("271828\n", encoding="ascii")

    manifest = generator.generate_anchor_challenges(
        mode="formal",
        sources_path=source_path,
        seed_path=seed_path,
        output_dir=challenges,
    )
    cases = _jsonl(challenges / "anchor_cases.jsonl")

    assert manifest["source_count"] == 40
    assert manifest["case_count"] == 120
    assert len({case["case_id"] for case in cases}) == 120
    assert len({case["cluster_id"] for case in cases}) == 40
    assert Counter(case["variant"] for case in cases) == Counter(
        {"anchored": 40, "drifted": 40, "lost": 40}
    )
    assert Counter(
        case["transformation"]["operation"]
        for case in cases
        if case["variant"] == "anchored"
    ) == Counter({operation: 10 for operation in generator.ANCHORED_OPERATIONS})
    assert Counter(
        case["transformation"]["operation"]
        for case in cases
        if case["variant"] == "drifted"
    ) == Counter({"local_rewrite": 14, "substitution": 13, "paraphrase": 13})


def _case(case_id: str, gold: str, span: dict | None) -> dict:
    return {
        "case_id": case_id,
        "source_anchor_id": case_id.split("-")[0],
        "cluster_id": case_id.split("-")[0],
        "variant": gold,
        "gold_status": gold,
        "gold_span": span,
        "item_input_sha256": "1" * 64,
        "transformed_text": {"sha256": "2" * 64},
    }


def _prediction(case: dict, predicted: str, span: dict | None) -> dict:
    return {
        "schema_version": "reviewer-validation-anchor-prediction/v1",
        "case_id": case["case_id"],
        "source_anchor_id": case["source_anchor_id"],
        "cluster_id": case["cluster_id"],
        "predicted_status": predicted,
        "predicted_span": span,
        "predicted_quote": None if span is None else "located",
        "case_input_sha256": case["item_input_sha256"],
        "transformed_text_sha256": case["transformed_text"]["sha256"],
        "production_callable": "src.argument.anchor.relocate",
    }


def test_metrics_match_hand_calculation_and_count_lost_nonempty_span() -> None:
    cases = [
        _case("a-1", "anchored", {"char_start": 0, "char_end": 10}),
        _case("b-1", "anchored", {"char_start": 0, "char_end": 10}),
        _case("c-1", "drifted", {"char_start": 0, "char_end": 10}),
        _case("d-1", "drifted", {"char_start": 0, "char_end": 10}),
        _case("e-1", "lost", None),
        _case("f-1", "lost", None),
    ]
    predictions = [
        _prediction(cases[0], "anchored", {"char_start": 0, "char_end": 10}),
        _prediction(cases[1], "drifted", {"char_start": 0, "char_end": 5}),
        _prediction(cases[2], "drifted", {"char_start": 5, "char_end": 10}),
        _prediction(cases[3], "drifted", {"char_start": 20, "char_end": 30}),
        _prediction(cases[4], "lost", None),
        _prediction(cases[5], "lost", {"char_start": 3, "char_end": 7}),
    ]
    metrics = scorer.score_records(
        cases,
        predictions,
        cases_sha256="3" * 64,
        predictions_sha256="4" * 64,
        bootstrap_seed=7,
        bootstrap_iterations=100,
    )
    # State F1 is intentionally independent of location correctness.  The
    # non-empty span on the final lost item is counted by false relocation and
    # joint accuracy, while its predicted state remains a true positive.
    assert metrics["state_macro_f1"]["value"] == pytest.approx((2 / 3 + 0.8 + 1.0) / 3)
    assert metrics["correct_location_rate"] == {
        "value": 0.75,
        "numerator": 3,
        "denominator": 4,
        "na": False,
    }
    assert metrics["mean_span_iou"]["value"] == 0.5
    assert metrics["zero_overlap_count"] == {"count": 1, "denominator": 4}
    assert metrics["false_relocation_rate"] == {
        "value": 0.5,
        "numerator": 1,
        "denominator": 2,
        "na": False,
    }
    assert metrics["joint_status_location_accuracy"]["value"] == 0.5
    assert metrics["cluster_bootstrap_95ci"]["cluster_count"] == 6


def test_zero_denominators_are_explicit_na_with_counts() -> None:
    case = _case("a-1", "anchored", {"char_start": 0, "char_end": 4})
    prediction = _prediction(case, "anchored", {"char_start": 0, "char_end": 4})
    metrics = scorer.score_records(
        [case],
        [prediction],
        cases_sha256="3" * 64,
        predictions_sha256="4" * 64,
        bootstrap_seed=None,
    )
    assert metrics["false_relocation_rate"] == {
        "value": None,
        "numerator": 0,
        "denominator": 0,
        "na": True,
    }
    assert metrics["per_state"]["lost"]["f1"]["na"] is True
    assert metrics["state_macro_f1"]["na"] is True


def test_dev_runtime_uses_production_relocate_and_recomputed_metrics_match(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "repo" / "methods" / "reviewer_validation"
    _configure_temp_base(monkeypatch, base)
    source_path = base / "outputs" / "pilot" / "anchor" / "dev_sources.jsonl"
    seed_path = base / "outputs" / "pilot" / "anchor" / "dev_seed.txt"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(DEV_SOURCES.read_bytes())
    seed_path.write_bytes(DEV_SEED.read_bytes())
    generated = source_path.parent / "generated"
    generator.generate_anchor_challenges(
        mode="dev", sources_path=source_path, seed_path=seed_path, output_dir=generated
    )
    before_sources = _sha(source_path.read_bytes())
    before_cases = _sha((generated / "anchor_cases.jsonl").read_bytes())
    run_dir = source_path.parent / "run"

    manifest = runner.run_anchor_cases(
        mode="dev", cases_path=generated / "anchor_cases.jsonl", output_dir=run_dir
    )
    recomputed = scorer.score_files(
        generated / "anchor_cases.jsonl", run_dir / "predictions.jsonl"
    )

    assert all(result["pass"] for result in manifest["probe_results"].values())
    assert {
        record["production_callable"]
        for record in _jsonl(run_dir / "predictions.jsonl")
    } == {"src.argument.anchor.relocate"}
    assert (run_dir / "metrics.json").read_bytes() == scorer.canonical_json_bytes(
        recomputed
    )
    assert _sha(source_path.read_bytes()) == before_sources
    assert _sha((generated / "anchor_cases.jsonl").read_bytes()) == before_cases
    qualitative = json.loads(
        (run_dir / "qualitative_cases.json").read_text(encoding="utf-8")
    )
    assert len(qualitative["cases"]) == 15


def test_formal_runner_checks_strict_freeze_before_case_read(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "repo" / "methods" / "reviewer_validation"
    _configure_temp_base(monkeypatch, base)
    cases = base / "challenges" / "anchor_cases.jsonl"
    output = base / "outputs" / "formal" / "anchor"
    called = {"read": False}

    def blocked(**_kwargs):
        raise runner.VERIFY.FreezeVerificationError("formal run blocked")

    def forbidden_read(_path):
        called["read"] = True
        raise AssertionError("formal case was read before strict verification")

    monkeypatch.setattr(runner.VERIFY, "require_formal_run_ready", blocked)
    monkeypatch.setattr(runner, "_read_jsonl", forbidden_read)
    with pytest.raises(
        runner.VERIFY.FreezeVerificationError, match="formal run blocked"
    ):
        runner.run_anchor_cases(mode="formal", cases_path=cases, output_dir=output)
    assert called["read"] is False
    assert not output.exists()


def test_boundaries_secrets_and_overwrite_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "repo" / "methods" / "reviewer_validation"
    _configure_temp_base(monkeypatch, base)
    source = base / "pilot" / "dev_sources.jsonl"
    seed = base / "pilot" / "dev_seed.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(DEV_SOURCES.read_bytes())
    seed.write_bytes(DEV_SEED.read_bytes())
    out = base / "out"
    generator.generate_anchor_challenges(
        mode="dev", sources_path=source, seed_path=seed, output_dir=out
    )
    with pytest.raises(generator.GenerationError, match="overwrite"):
        generator.generate_anchor_challenges(
            mode="dev", sources_path=source, seed_path=seed, output_dir=out
        )
    secret_record = json.loads(DEV_SOURCES.read_text(encoding="utf-8").splitlines()[0])
    secret_record["transform_inputs"]["api_key"] = "sk-abcdefghijklmnop"
    with pytest.raises(generator.GenerationError):
        generator._validate_source(secret_record, mode="dev")
    with pytest.raises(generator.GenerationError, match="escapes"):
        generator.generate_anchor_challenges(
            mode="dev",
            sources_path=source,
            seed_path=seed,
            output_dir=tmp_path / "outside",
        )
