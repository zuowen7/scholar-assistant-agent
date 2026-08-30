"""Score frozen-format Anchor cases against production relocation predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
STATES = ("anchored", "drifted", "lost")
LOCATION_IOU_THRESHOLD = 0.50


class ScoringError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _read_jsonl(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScoringError(f"input is not UTF-8: {path}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ScoringError(f"invalid JSON at {path}:{line_number}") from exc
        if not isinstance(record, dict):
            raise ScoringError(f"record at {path}:{line_number} must be an object")
        records.append(record)
    return raw, records


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "value": None if denominator == 0 else round(numerator / denominator, 12),
        "numerator": numerator,
        "denominator": denominator,
        "na": denominator == 0,
    }


def _mean(total: float, denominator: int) -> dict[str, Any]:
    return {
        "value": None if denominator == 0 else round(total / denominator, 12),
        "sum": round(total, 12),
        "denominator": denominator,
        "na": denominator == 0,
    }


def span_iou(left: dict[str, int] | None, right: dict[str, int] | None) -> float:
    if left is None or right is None:
        return 0.0
    left_start, left_end = left["char_start"], left["char_end"]
    right_start, right_end = right["char_start"], right["char_end"]
    if not (left_start < left_end and right_start < right_end):
        raise ScoringError("spans must be non-empty half-open intervals")
    intersection = max(0, min(left_end, right_end) - max(left_start, right_start))
    union = max(left_end, right_end) - min(left_start, right_start)
    return intersection / union if union else 0.0


def _validate_prediction(record: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "case_id",
        "source_anchor_id",
        "cluster_id",
        "predicted_status",
        "predicted_span",
        "predicted_quote",
        "case_input_sha256",
        "transformed_text_sha256",
        "production_callable",
    }
    if set(record) != required:
        raise ScoringError(
            f"prediction {record.get('case_id')}: fields do not match contract"
        )
    if record["schema_version"] != "reviewer-validation-anchor-prediction/v1":
        raise ScoringError("unknown prediction schema")
    if record["predicted_status"] not in STATES:
        raise ScoringError(f"prediction {record['case_id']}: invalid state")
    span = record["predicted_span"]
    if span is not None:
        if set(span) != {"char_start", "char_end"}:
            raise ScoringError(f"prediction {record['case_id']}: invalid span fields")
        if not all(isinstance(span[key], int) for key in ("char_start", "char_end")):
            raise ScoringError(
                f"prediction {record['case_id']}: span must contain integers"
            )
        if not 0 <= span["char_start"] < span["char_end"]:
            raise ScoringError(
                f"prediction {record['case_id']}: invalid half-open span"
            )
    if span is None and record["predicted_quote"] is not None:
        raise ScoringError(
            f"prediction {record['case_id']}: null span requires null quote"
        )
    if span is not None and not isinstance(record["predicted_quote"], str):
        raise ScoringError(
            f"prediction {record['case_id']}: located result requires a quote"
        )
    if record["predicted_status"] != "lost" and span is None:
        raise ScoringError(
            f"prediction {record['case_id']}: located state requires span and quote"
        )


def _pair_records(
    cases: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    case_by_id: dict[str, dict[str, Any]] = {}
    prediction_by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in case_by_id:
            raise ScoringError(f"duplicate or invalid case_id: {case_id!r}")
        case_by_id[case_id] = case
    for prediction in predictions:
        _validate_prediction(prediction)
        case_id = prediction["case_id"]
        if case_id in prediction_by_id:
            raise ScoringError(f"duplicate prediction case_id: {case_id}")
        prediction_by_id[case_id] = prediction
    if set(case_by_id) != set(prediction_by_id):
        missing = sorted(set(case_by_id) - set(prediction_by_id))
        extra = sorted(set(prediction_by_id) - set(case_by_id))
        raise ScoringError(
            f"case/prediction identity mismatch: missing={missing}, extra={extra}"
        )
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for case in cases:
        prediction = prediction_by_id[case["case_id"]]
        if prediction["source_anchor_id"] != case["source_anchor_id"]:
            raise ScoringError(
                f"prediction {case['case_id']}: source_anchor_id mismatch"
            )
        if prediction["cluster_id"] != case["cluster_id"]:
            raise ScoringError(f"prediction {case['case_id']}: cluster_id mismatch")
        if prediction["case_input_sha256"] != case["item_input_sha256"]:
            raise ScoringError(
                f"prediction {case['case_id']}: case input hash mismatch"
            )
        if prediction["transformed_text_sha256"] != case["transformed_text"]["sha256"]:
            raise ScoringError(
                f"prediction {case['case_id']}: transformed text hash mismatch"
            )
        pairs.append((case, prediction))
    return pairs


def _core_metrics(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    confusion = {gold: {predicted: 0 for predicted in STATES} for gold in STATES}
    location_ious: list[float] = []
    correct_locations = 0
    zero_overlap = 0
    lost_count = 0
    false_relocations = 0
    joint_correct = 0
    state_correct = 0
    for case, prediction in pairs:
        gold_state = case["gold_status"]
        predicted_state = prediction["predicted_status"]
        confusion[gold_state][predicted_state] += 1
        state_matches = gold_state == predicted_state
        state_correct += int(state_matches)
        predicted_span = prediction["predicted_span"]
        if gold_state == "lost":
            lost_count += 1
            empty_location = predicted_span is None
            false_relocations += int(not empty_location)
            joint_correct += int(state_matches and empty_location)
        else:
            iou = span_iou(case["gold_span"], predicted_span)
            location_ious.append(iou)
            location_matches = iou >= LOCATION_IOU_THRESHOLD
            correct_locations += int(location_matches)
            zero_overlap += int(iou == 0.0)
            joint_correct += int(state_matches and location_matches)

    per_state: dict[str, Any] = {}
    class_f1_values: list[float] = []
    undefined_f1 = 0
    for state in STATES:
        tp = confusion[state][state]
        fp = sum(confusion[other][state] for other in STATES if other != state)
        fn = sum(confusion[state][other] for other in STATES if other != state)
        precision = _rate(tp, tp + fp)
        recall = _rate(tp, tp + fn)
        f1_denominator = 2 * tp + fp + fn
        f1 = _rate(2 * tp, f1_denominator)
        if f1["value"] is None:
            undefined_f1 += 1
        else:
            class_f1_values.append(f1["value"])
        per_state[state] = {
            "support": sum(confusion[state].values()),
            "predicted_count": sum(confusion[other][state] for other in STATES),
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    macro_f1 = {
        "value": None
        if undefined_f1
        else round(sum(class_f1_values) / len(STATES), 12),
        "defined_class_count": len(class_f1_values),
        "na_class_count": undefined_f1,
        "denominator": len(STATES),
        "na": bool(undefined_f1),
    }
    return {
        "confusion_matrix": confusion,
        "per_state": per_state,
        "state_accuracy": _rate(state_correct, len(pairs)),
        "state_macro_f1": macro_f1,
        "correct_location_rate": _rate(correct_locations, len(location_ious)),
        "mean_span_iou": _mean(sum(location_ious), len(location_ious)),
        "zero_overlap_count": {
            "count": zero_overlap,
            "denominator": len(location_ious),
        },
        "false_relocation_rate": _rate(false_relocations, lost_count),
        "joint_status_location_accuracy": _rate(joint_correct, len(pairs)),
    }


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ScoringError("cannot compute percentile of an empty list")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _cluster_bootstrap(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]], *, seed: int, iterations: int
) -> dict[str, Any]:
    by_cluster: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for pair in pairs:
        by_cluster.setdefault(pair[0]["cluster_id"], []).append(pair)
    clusters = sorted(by_cluster)
    if not clusters:
        return {
            "status": "not_computed",
            "reason": "zero clusters",
            "seed": seed,
            "iterations": iterations,
            "cluster_count": 0,
            "confidence_level": 0.95,
            "intervals": {},
        }
    rng = random.Random(seed)
    metric_names = (
        "state_macro_f1",
        "correct_location_rate",
        "false_relocation_rate",
        "joint_status_location_accuracy",
    )
    samples: dict[str, list[float]] = {name: [] for name in metric_names}
    for _ in range(iterations):
        sampled_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for _cluster_index in range(len(clusters)):
            sampled_pairs.extend(by_cluster[rng.choice(clusters)])
        metrics = _core_metrics(sampled_pairs)
        for name in metric_names:
            value = metrics[name]["value"]
            if value is not None:
                samples[name].append(value)
    intervals: dict[str, Any] = {}
    for name in metric_names:
        values = samples[name]
        intervals[name] = {
            "lower": None if not values else round(_percentile(values, 0.025), 12),
            "upper": None if not values else round(_percentile(values, 0.975), 12),
            "defined_replicates": len(values),
            "na_replicates": iterations - len(values),
        }
    return {
        "status": "computed",
        "seed": seed,
        "iterations": iterations,
        "cluster_count": len(clusters),
        "confidence_level": 0.95,
        "intervals": intervals,
    }


def score_records(
    cases: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    cases_sha256: str,
    predictions_sha256: str,
    bootstrap_seed: int | None,
    bootstrap_iterations: int = 10_000,
) -> dict[str, Any]:
    pairs = _pair_records(cases, predictions)
    core = _core_metrics(pairs)
    clusters = {case["cluster_id"] for case, _prediction in pairs}
    variants = Counter(case["variant"] for case, _prediction in pairs)
    if bootstrap_seed is None:
        bootstrap = {
            "status": "not_computed",
            "reason": "protocol bootstrap seed is not frozen",
            "seed": None,
            "iterations": bootstrap_iterations,
            "cluster_count": len(clusters),
            "confidence_level": 0.95,
            "intervals": {},
        }
    else:
        bootstrap = _cluster_bootstrap(
            pairs, seed=bootstrap_seed, iterations=bootstrap_iterations
        )
    return {
        "schema_version": "reviewer-validation-anchor-metrics/v1",
        "cases_sha256": cases_sha256,
        "predictions_sha256": predictions_sha256,
        "case_count": len(pairs),
        "cluster_count": len(clusters),
        "variant_counts": {state: variants[state] for state in STATES},
        "analysis_unit": "source_anchor_id",
        "location_iou_threshold": LOCATION_IOU_THRESHOLD,
        **core,
        "cluster_bootstrap_95ci": bootstrap,
    }


def _bootstrap_settings() -> tuple[int | None, int]:
    protocol = yaml.safe_load((BASE_DIR / "protocol.yaml").read_text(encoding="utf-8"))
    seed = protocol["seeds"]["bootstrap"]
    if seed is not None and (not isinstance(seed, int) or seed < 0):
        raise ScoringError(
            "protocol bootstrap seed must be null or a non-negative integer"
        )
    iterations = protocol["analysis"]["bootstrap_iterations"]
    if not isinstance(iterations, int) or iterations <= 0:
        raise ScoringError("protocol bootstrap iterations must be positive")
    return seed, iterations


def score_files(cases_path: Path, predictions_path: Path) -> dict[str, Any]:
    cases_bytes, cases = _read_jsonl(cases_path)
    predictions_bytes, predictions = _read_jsonl(predictions_path)
    seed, iterations = _bootstrap_settings()
    return score_records(
        cases,
        predictions,
        cases_sha256=_sha(cases_bytes),
        predictions_sha256=_sha(predictions_bytes),
        bootstrap_seed=seed,
        bootstrap_iterations=iterations,
    )


def _ensure_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ScoringError(
            f"{label} escapes reviewer-validation boundary: {resolved}"
        ) from exc
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cases_path = _ensure_within(args.cases, BASE_DIR, "cases")
        predictions_path = _ensure_within(args.predictions, BASE_DIR, "predictions")
        output_path = _ensure_within(args.output, BASE_DIR, "output")
        if output_path.exists():
            raise ScoringError(f"refusing to overwrite existing metrics: {output_path}")
        metrics = score_files(cases_path, predictions_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(canonical_json_bytes(metrics))
    except (OSError, ScoringError, ValueError) as exc:
        print(f"ANCHOR_SCORING: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print(f"ANCHOR_SCORING: PASS ({metrics['case_count']} cases)")
    print(f"METRICS_SHA256: {_sha(canonical_json_bytes(metrics))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
