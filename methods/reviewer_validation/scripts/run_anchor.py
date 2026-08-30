"""Run production Anchor relocation on development or strictly frozen cases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
SCHEMA_DIR = BASE_DIR / "schemas"
CASE_SCHEMA = "reviewer-validation-anchor-case/v1"


class AnchorRunError(RuntimeError):
    pass


def _load_sibling(filename: str, module_name: str) -> Any:
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).with_name(filename)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling module {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load_sibling(
    "verify_freeze.py", "reviewer_validation_verify_freeze_for_anchor_run"
)
SCORER = _load_sibling("score_anchor.py", "reviewer_validation_score_anchor_for_run")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_line(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_jsonl(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnchorRunError(f"input is not UTF-8: {path}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnchorRunError(f"invalid JSON at {path}:{line_number}") from exc
        if not isinstance(record, dict):
            raise AnchorRunError(f"record at {path}:{line_number} must be an object")
        records.append(record)
    return raw, records


def _ensure_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise AnchorRunError(
            f"{label} escapes reviewer-validation boundary: {resolved}"
        ) from exc
    return resolved


def _source_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for record in records:
        source_id = record.get("source_anchor_id")
        if not isinstance(source_id, str) or source_id in sources:
            raise AnchorRunError(
                f"duplicate or invalid source_anchor_id: {source_id!r}"
            )
        anchor = record.get("anchor")
        if not isinstance(anchor, dict) or anchor.get("id") != source_id:
            raise AnchorRunError(
                f"source {source_id}: invalid production Anchor snapshot"
            )
        sources[source_id] = record
    return sources


def _validate_cases(
    cases: list[dict[str, Any]], case_dir: Path
) -> tuple[dict[str, bytes], dict[str, Path]]:
    artifacts: dict[str, bytes] = {}
    paths: dict[str, Path] = {}
    for case in cases:
        identity = case.get("transformed_text")
        if not isinstance(identity, dict) or not isinstance(
            identity.get("artifact_id"), str
        ):
            raise AnchorRunError(
                f"case {case.get('case_id')}: invalid transformed artifact identity"
            )
        artifact_id = identity["artifact_id"]
        target = _ensure_within(
            case_dir / Path(artifact_id), case_dir, "transformed text"
        )
        data = target.read_bytes()
        artifacts[artifact_id] = data
        paths[artifact_id] = target
    errors: list[str] = []
    for case in cases:
        errors.extend(
            f"{case.get('case_id')}: {error}"
            for error in VERIFY.validate_instance(
                case, CASE_SCHEMA, SCHEMA_DIR, artifacts.__getitem__
            )
        )
    if errors:
        raise AnchorRunError("case validation failed: " + "; ".join(errors[:10]))
    return artifacts, paths


def _bootstrap_settings() -> tuple[int | None, int]:
    import yaml

    protocol = yaml.safe_load((BASE_DIR / "protocol.yaml").read_text(encoding="utf-8"))
    return protocol["seeds"]["bootstrap"], protocol["analysis"]["bootstrap_iterations"]


def run_anchor_cases(
    *, mode: str, cases_path: Path, output_dir: Path
) -> dict[str, Any]:
    cases_path = _ensure_within(cases_path, BASE_DIR, "cases")
    output_dir = _ensure_within(output_dir, BASE_DIR, "output")

    # D6 invariant: strict verification occurs before the first case read and
    # before production Anchor is imported or called.
    if mode == "formal":
        VERIFY.require_formal_run_ready(base_dir=BASE_DIR, repo_root=REPO_ROOT)
        if cases_path != (BASE_DIR / "challenges" / "anchor_cases.jsonl").resolve():
            raise AnchorRunError("formal runner requires canonical frozen case path")
        expected_root = (BASE_DIR / "outputs" / "formal" / "anchor").resolve()
        try:
            output_dir.relative_to(expected_root)
        except ValueError as exc:
            raise AnchorRunError(
                "formal output must remain under outputs/formal/anchor"
            ) from exc
    elif mode == "dev":
        expected_root = (BASE_DIR / "outputs" / "pilot" / "anchor").resolve()
        try:
            cases_path.relative_to(expected_root)
            output_dir.relative_to(expected_root)
        except ValueError as exc:
            raise AnchorRunError(
                "development inputs and outputs must remain under outputs/pilot/anchor"
            ) from exc
    else:
        raise AnchorRunError(f"unknown mode: {mode}")

    targets = [
        output_dir / "predictions.jsonl",
        output_dir / "metrics.json",
        output_dir / "run_manifest.jsonl",
        output_dir / "qualitative_cases.json",
    ]
    if any(target.exists() for target in targets):
        raise AnchorRunError("refusing to overwrite an existing Anchor run artifact")

    cases_bytes, cases = _read_jsonl(cases_path)
    if not cases:
        raise AnchorRunError("case list is empty")
    if mode == "formal":
        clusters = {case.get("cluster_id") for case in cases}
        variants = {case.get("variant") for case in cases}
        if (
            len(cases) != 120
            or len(clusters) != 40
            or variants != {"anchored", "drifted", "lost"}
        ):
            raise AnchorRunError(
                "formal case cardinality is not 40 clusters x 3 variants"
            )
    sources_path = cases_path.parent / "anchor_sources.jsonl"
    source_bytes, source_records = _read_jsonl(sources_path)
    sources = _source_index(source_records)
    artifacts, artifact_paths = _validate_cases(cases, cases_path.parent)
    missing_sources = sorted(
        {case["source_anchor_id"] for case in cases} - set(sources)
    )
    if missing_sources:
        raise AnchorRunError(f"cases reference missing sources: {missing_sources}")
    before_hashes = {
        "cases": _sha(cases_bytes),
        "sources": _sha(source_bytes),
        **{f"text:{key}": _sha(value) for key, value in artifacts.items()},
    }

    if str(PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(PYTHON_ROOT))
    from src.argument.anchor import Anchor, relocate

    predictions: list[dict[str, Any]] = []
    qualitative: list[dict[str, Any]] = []
    for case in cases:
        source = sources[case["source_anchor_id"]]
        anchor = Anchor.model_validate(source["anchor"])
        artifact_id = case["transformed_text"]["artifact_id"]
        transformed_text = artifacts[artifact_id].decode("utf-8")
        relocated = relocate(anchor, transformed_text)
        if relocated.char_start is None or relocated.char_end is None:
            predicted_span = None
            predicted_quote = None
        else:
            predicted_span = {
                "char_start": relocated.char_start,
                "char_end": relocated.char_end,
            }
            predicted_quote = transformed_text[
                relocated.char_start : relocated.char_end
            ]
        prediction = {
            "schema_version": "reviewer-validation-anchor-prediction/v1",
            "case_id": case["case_id"],
            "source_anchor_id": case["source_anchor_id"],
            "cluster_id": case["cluster_id"],
            "predicted_status": relocated.status,
            "predicted_span": predicted_span,
            "predicted_quote": predicted_quote,
            "case_input_sha256": case["item_input_sha256"],
            "transformed_text_sha256": case["transformed_text"]["sha256"],
            "production_callable": "src.argument.anchor.relocate",
        }
        predictions.append(prediction)
        if mode == "dev":
            qualitative.append(
                {
                    "case_id": case["case_id"],
                    "known_probe": source.get("known_probe"),
                    "source_quote": case["source_quote"],
                    "source_context_before": source["anchor"]["context_before"],
                    "source_context_after": source["anchor"]["context_after"],
                    "transformed_text": transformed_text,
                    "gold_status": case["gold_status"],
                    "gold_span": case["gold_span"],
                    "predicted_status": relocated.status,
                    "predicted_span": predicted_span,
                    "predicted_quote": predicted_quote,
                }
            )

    after_hashes = {
        "cases": _sha(cases_path.read_bytes()),
        "sources": _sha(sources_path.read_bytes()),
        **{
            f"text:{artifact_id}": _sha(artifact_paths[artifact_id].read_bytes())
            for artifact_id in artifacts
        },
    }
    if before_hashes != after_hashes:
        raise AnchorRunError("an immutable input changed during execution")
    prediction_bytes = b"".join(_json_line(record) for record in predictions)
    bootstrap_seed, bootstrap_iterations = _bootstrap_settings()
    metrics = SCORER.score_records(
        cases,
        predictions,
        cases_sha256=_sha(cases_bytes),
        predictions_sha256=_sha(prediction_bytes),
        bootstrap_seed=bootstrap_seed,
        bootstrap_iterations=bootstrap_iterations,
    )
    metrics_bytes = SCORER.canonical_json_bytes(metrics)
    qualitative_payload = {
        "schema_version": "reviewer-validation-anchor-qualitative-pilot/v1",
        "development_only": mode == "dev",
        "cases": qualitative,
    }
    qualitative_bytes = SCORER.canonical_json_bytes(qualitative_payload)
    probe_results: dict[str, Any] = {}
    for probe in KNOWN_PROBES:
        relevant_variant = "anchored" if probe == "duplicate_exact_second" else "lost"
        matches = [
            item
            for item in qualitative
            if item["known_probe"] == probe
            and item["case_id"].endswith(f"--{relevant_variant}")
        ]
        if matches:
            item = matches[0]
            probe_results[probe] = {
                "expected_status": item["gold_status"],
                "expected_span": item["gold_span"],
                "actual_status": item["predicted_status"],
                "actual_span": item["predicted_span"],
                "pass": item["gold_status"] == item["predicted_status"]
                and item["gold_span"] == item["predicted_span"],
            }
    if mode == "dev" and set(probe_results) != KNOWN_PROBES:
        raise AnchorRunError("development pilot is missing one or more fixed probes")
    if mode == "dev" and not all(result["pass"] for result in probe_results.values()):
        raise AnchorRunError(f"development probe failed: {probe_results}")

    manifest = {
        "schema_version": "reviewer-validation-anchor-run-manifest/v1",
        "mode": mode,
        "production_callable": "src.argument.anchor.relocate",
        "case_count": len(cases),
        "cluster_count": len({case["cluster_id"] for case in cases}),
        "inputs": before_hashes,
        "outputs": {
            "predictions.jsonl": _sha(prediction_bytes),
            "metrics.json": _sha(metrics_bytes),
            **(
                {"qualitative_cases.json": _sha(qualitative_bytes)}
                if mode == "dev"
                else {}
            ),
        },
        "probe_results": probe_results,
    }
    if VERIFY.find_secret_issues([predictions, metrics, qualitative_payload, manifest]):
        raise AnchorRunError("run artifacts contain secret-like fields")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "predictions.jsonl").write_bytes(prediction_bytes)
    (output_dir / "metrics.json").write_bytes(metrics_bytes)
    if mode == "dev":
        (output_dir / "qualitative_cases.json").write_bytes(qualitative_bytes)
    (output_dir / "run_manifest.jsonl").write_bytes(_json_line(manifest))
    return manifest


KNOWN_PROBES = {"duplicate_exact_second", "deleted_target_similar_distractor"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dev", "formal"), required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = run_anchor_cases(
            mode=args.mode, cases_path=args.cases, output_dir=args.output_dir
        )
    except (AnchorRunError, OSError, ValueError, VERIFY.FreezeVerificationError) as exc:
        print(f"ANCHOR_RUN: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print(f"ANCHOR_RUN: PASS ({manifest['case_count']} cases)")
    for name, result in sorted(manifest["probe_results"].items()):
        print(
            f"PROBE {name}: {'PASS' if result['pass'] else 'FAIL'} "
            f"expected={result['expected_status']}:{result['expected_span']} "
            f"actual={result['actual_status']}:{result['actual_span']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
