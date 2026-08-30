"""Fail-closed validation for the reviewer-validation protocol and freeze manifest.

Draft mode proves only that the scaffold is internally well formed. Formal
runners must call :func:`require_formal_run_ready`, which always performs the
strict checks again and has no bypass flag.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_ID_TO_FILE = {
    "reviewer-validation-protocol/v1": "protocol.schema.json",
    "reviewer-validation-freeze-manifest/v1": "freeze_manifest.schema.json",
    "reviewer-validation-promise-gold/v1": "promise_gold.schema.json",
    "reviewer-validation-anchor-case/v1": "anchor_case.schema.json",
    "reviewer-validation-venue-applicability/v1": "venue_applicability.schema.json",
    "reviewer-validation-venue-review-score/v1": "venue_review_score.schema.json",
    "reviewer-validation-run-record/v1": "run_record.schema.json",
}

TERMINATION_STATUSES = {
    "success",
    "legal_empty",
    "empty_response",
    "invalid_json",
    "timeout",
    "provider_error",
    "classification_incomplete",
    "unknown_status",
}

SENSITIVE_KEY_NAMES = {
    "api_key",
    "apikey",
    "api_token",
    "access_token",
    "authorization",
    "password",
    "passwd",
    "client_secret",
    "secret_key",
    "credentials",
    "proxy_url",
}

SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class FreezeVerificationError(RuntimeError):
    """Raised when a formal run is attempted before strict freeze succeeds."""


@dataclass
class VerificationReport:
    mode: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified_artifacts: list[str] = field(default_factory=list)
    pending_artifacts: list[str] = field(default_factory=list)
    protocol_sha256: str | None = None
    manifest_sha256: str | None = None
    formal_run_authorized: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


ArtifactResolver = Callable[[str], bytes]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _json_path(parts: Iterable[Any]) -> str:
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _is_sensitive_key(key: str) -> bool:
    normalised = _normalise_key(key)
    if normalised in SENSITIVE_KEY_NAMES:
        return True
    return any(
        normalised.endswith(suffix)
        for suffix in (
            "_api_key",
            "_api_token",
            "_access_token",
            "_authorization",
            "_password",
            "_passwd",
            "_client_secret",
            "_secret_key",
            "_credentials",
        )
    )


def find_secret_issues(value: Any, path: str = "$") -> list[str]:
    """Return locations only; never echo a possible credential value."""

    issues: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _is_sensitive_key(str(key)):
                issues.append(f"{child_path}: secret-like field name is forbidden")
            issues.extend(find_secret_issues(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(find_secret_issues(child, f"{path}[{index}]"))
    elif isinstance(value, str) and any(
        pattern.search(value) for pattern in SENSITIVE_VALUE_PATTERNS
    ):
        issues.append(f"{path}: secret-like value is forbidden")
    return issues


def load_schema(schema_dir: Path, schema_id: str) -> dict[str, Any]:
    filename = SCHEMA_ID_TO_FILE.get(schema_id)
    if filename is None:
        raise ValueError(f"unknown schema version: {schema_id}")
    schema = json.loads((schema_dir / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    if schema.get("$id") != schema_id:
        raise ValueError(f"schema ID mismatch for {filename}: {schema.get('$id')!r}")
    return schema


def _schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(instance), key=lambda item: list(item.absolute_path)
    )
    return [f"{_json_path(error.absolute_path)}: {error.message}" for error in errors]


def _resolve_bytes(
    resolver: ArtifactResolver | None, artifact_id: str, path: str, errors: list[str]
) -> bytes | None:
    if resolver is None:
        errors.append(
            f"{path}: semantic validation requires artifact resolver for {artifact_id}"
        )
        return None
    try:
        return resolver(artifact_id)
    except Exception as exc:  # noqa: BLE001 - converted to a non-secret validation error
        errors.append(
            f"{path}: cannot resolve artifact {artifact_id}: {type(exc).__name__}"
        )
        return None


def _validate_artifact_identity(
    identity: dict[str, Any],
    resolver: ArtifactResolver | None,
    path: str,
    errors: list[str],
) -> bytes | None:
    data = _resolve_bytes(resolver, identity["artifact_id"], path, errors)
    if data is not None and sha256_bytes(data) != identity["sha256"]:
        errors.append(f"{path}: referenced artifact hash mismatch")
    return data


def _validate_text_span(
    quote: str,
    span: dict[str, Any],
    resolver: ArtifactResolver | None,
    path: str,
    errors: list[str],
) -> None:
    identity = {"artifact_id": span["artifact_id"], "sha256": span["text_sha256"]}
    data = _validate_artifact_identity(identity, resolver, path, errors)
    if data is None:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"{path}: referenced text is not UTF-8")
        return
    start, end = span["char_start"], span["char_end"]
    if not (0 <= start < end <= len(text)):
        errors.append(
            f"{path}: coordinates must be in-bounds 0-based half-open interval"
        )
        return
    if text[start:end] != quote:
        errors.append(f"{path}: exact_quote does not equal referenced text slice")


def _validate_mapping(
    full_span: dict[str, Any],
    excerpt_span: dict[str, Any],
    mapping_identity: dict[str, Any],
    resolver: ArtifactResolver | None,
    path: str,
    errors: list[str],
) -> None:
    raw = _validate_artifact_identity(mapping_identity, resolver, path, errors)
    if raw is None:
        return
    try:
        mapping = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{path}: mapping is not valid UTF-8 JSON")
        return
    if mapping.get("schema_version") != "reviewer-validation-coordinate-map/v1":
        errors.append(f"{path}: unknown coordinate mapping schema version")
        return
    expected = {
        "full_text_artifact_id": full_span["artifact_id"],
        "full_text_sha256": full_span["text_sha256"],
        "excerpt_artifact_id": excerpt_span["artifact_id"],
        "excerpt_sha256": excerpt_span["text_sha256"],
    }
    for key, value in expected.items():
        if mapping.get(key) != value:
            errors.append(f"{path}: mapping identity mismatch for {key}")
    start, end = excerpt_span["char_start"], excerpt_span["char_end"]
    covering = [
        segment
        for segment in mapping.get("segments", [])
        if isinstance(segment, dict)
        and segment.get("excerpt_start", -1) <= start
        and segment.get("excerpt_end", -1) >= end
    ]
    if len(covering) != 1:
        errors.append(f"{path}: gold excerpt span must map through exactly one segment")
        return
    segment = covering[0]
    if segment.get("kind") == "synthetic":
        errors.append(f"{path}: gold span falls in a synthetic mapping segment")
        return
    if segment.get("kind") != "source":
        errors.append(f"{path}: mapping segment kind must be source or synthetic")
        return
    projected_start = segment.get("full_text_start", -1) + (
        start - segment["excerpt_start"]
    )
    projected_end = segment.get("full_text_start", -1) + (
        end - segment["excerpt_start"]
    )
    if (
        projected_start != full_span["char_start"]
        or projected_end != full_span["char_end"]
    ):
        errors.append(
            f"{path}: excerpt span does not project to declared full-text span"
        )


def _validate_promise_gold(
    instance: dict[str, Any], resolver: ArtifactResolver | None
) -> list[str]:
    errors: list[str] = []
    _validate_text_span(
        instance["exact_quote"], instance["full_text"], resolver, "$.full_text", errors
    )
    _validate_text_span(
        instance["exact_quote"], instance["excerpt"], resolver, "$.excerpt", errors
    )
    _validate_mapping(
        instance["full_text"],
        instance["excerpt"],
        instance["mapping"],
        resolver,
        "$.mapping",
        errors,
    )
    evidence_ids: set[str] = set()
    for index, evidence in enumerate(instance["gold_evidence_spans"]):
        path = f"$.gold_evidence_spans[{index}]"
        if evidence["evidence_id"] in evidence_ids:
            errors.append(f"{path}.evidence_id: duplicate evidence ID")
        evidence_ids.add(evidence["evidence_id"])
        _validate_text_span(
            evidence["exact_quote"],
            evidence["full_text"],
            resolver,
            f"{path}.full_text",
            errors,
        )
        _validate_text_span(
            evidence["exact_quote"],
            evidence["excerpt"],
            resolver,
            f"{path}.excerpt",
            errors,
        )
        _validate_mapping(
            evidence["full_text"],
            evidence["excerpt"],
            evidence["mapping"],
            resolver,
            f"{path}.mapping",
            errors,
        )
    expected_evidence_bearing = bool(instance["gold_evidence_spans"])
    if instance["denominators"]["evidence_bearing"] != expected_evidence_bearing:
        errors.append(
            "$.denominators.evidence_bearing: does not match gold_evidence_spans"
        )
    return errors


def _validate_anchor_case(
    instance: dict[str, Any], resolver: ArtifactResolver | None
) -> list[str]:
    errors: list[str] = []
    if instance["cluster_id"] != instance["source_anchor_id"]:
        errors.append(
            "$.cluster_id: must equal source_anchor_id for source-anchor clustering"
        )
    raw = _validate_artifact_identity(
        instance["transformed_text"], resolver, "$.transformed_text", errors
    )
    if raw is None or instance["gold_span"] is None:
        return errors
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return errors + ["$.transformed_text: transformed text is not UTF-8"]
    start, end = instance["gold_span"]["char_start"], instance["gold_span"]["char_end"]
    if not (0 <= start < end <= len(text)):
        errors.append(
            "$.gold_span: coordinates must be in-bounds 0-based half-open interval"
        )
    elif text[start:end] != instance["gold_quote"]:
        errors.append("$.gold_quote: does not equal transformed text slice")
    if (
        instance["variant"] == "anchored"
        and instance["gold_quote"] != instance["source_quote"]
    ):
        errors.append("$.gold_quote: anchored variant must preserve source_quote bytes")
    if (
        instance["variant"] == "drifted"
        and instance["gold_quote"] == instance["source_quote"]
    ):
        errors.append("$.gold_quote: drifted variant must change source_quote bytes")
    return errors


def _validate_venue_applicability(
    instance: dict[str, Any], resolver: ArtifactResolver | None
) -> list[str]:
    errors: list[str] = []
    if (
        sha256_bytes(instance["criterion_text"].encode("utf-8"))
        != instance["criterion_text_sha256"]
    ):
        errors.append("$.criterion_text_sha256: does not hash criterion_text bytes")
    _validate_artifact_identity(
        instance["official_source"], resolver, "$.official_source", errors
    )
    _validate_artifact_identity(
        {
            "artifact_id": instance["excerpt"]["artifact_id"],
            "sha256": instance["excerpt"]["sha256"],
        },
        resolver,
        "$.excerpt",
        errors,
    )
    return errors


def _validate_venue_score(instance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    denominators = instance["denominators"]
    criterion_pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for index, item in enumerate(instance["criteria"]):
        criterion = criterion_pairs.setdefault(item["criterion_id"], {})
        if item["side"] in criterion:
            errors.append(
                f"$.criteria[{index}]: duplicate criterion-side {item['criterion_id']}/{item['side']}"
            )
        criterion[item["side"]] = item
    for criterion_id, sides in sorted(criterion_pairs.items()):
        if set(sides) != {"A", "B"}:
            errors.append(
                f"$.criteria: {criterion_id} must occur once for each side A and B"
            )
            continue
        if sides["A"]["applicability"] != sides["B"]["applicability"]:
            errors.append(
                f"$.criteria: {criterion_id} applicability must be identical across sides"
            )
    applicable_per_review = sum(
        sides.get("A", {}).get("applicability") == "applicable"
        for sides in criterion_pairs.values()
    )
    labels = [item["label"] for item in instance["critique_units"]]
    expected = {
        "criteria_defined": len(criterion_pairs),
        "review_sides": 2,
        "criterion_rows": len(instance["criteria"]),
        "applicable_criteria_per_review": applicable_per_review,
        "scored_criterion_occurrences": 2 * applicable_per_review,
        "criteria_max_points_per_review": 2 * applicable_per_review,
        "supported_critique_units": labels.count("supported"),
        "unsupported_critique_units": labels.count("unsupported"),
        "not_assessable_critique_units": labels.count("not_assessable"),
        "fact_claim_critique_units": labels.count("supported")
        + labels.count("unsupported"),
    }
    for key, value in expected.items():
        if denominators[key] != value:
            errors.append(
                f"$.denominators.{key}: expected {value}, got {denominators[key]}"
            )
    critique_ids = [item["critique_id"] for item in instance["critique_units"]]
    if len(critique_ids) != len(set(critique_ids)):
        errors.append("$.critique_units: duplicate critique ID")
    return errors


def _parse_time(value: str, path: str, errors: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path}: invalid RFC 3339 timestamp")
        return None


def _validate_run_record(instance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    started = _parse_time(instance["started_at"], "$.started_at", errors)
    ended = _parse_time(instance["ended_at"], "$.ended_at", errors)
    if started and ended and ended < started:
        errors.append("$.ended_at: must not precede started_at")
    total_attempts = 0
    step_ids: set[str] = set()
    for step_index, step in enumerate(instance["steps"]):
        path = f"$.steps[{step_index}]"
        if step["step_id"] in step_ids:
            errors.append(f"{path}.step_id: duplicate step ID")
        step_ids.add(step["step_id"])
        attempts = step["attempts"]
        total_attempts += len(attempts)
        if step["termination"]["attempt_count"] != len(attempts):
            errors.append(
                f"{path}.termination.attempt_count: does not match attempts length"
            )
        numbers = [attempt["attempt_number"] for attempt in attempts]
        if numbers != list(range(1, len(attempts) + 1)):
            errors.append(f"{path}.attempts: attempt_number must be contiguous from 1")
        if attempts[0]["prompt"]["sha256"] != step["inputs"]["prompt"]["sha256"]:
            errors.append(
                f"{path}.attempts[0].prompt: must match the step's initial prompt"
            )
        for attempt_index, attempt in enumerate(attempts):
            attempt_started = _parse_time(
                attempt["started_at"],
                f"{path}.attempts[{attempt_index}].started_at",
                errors,
            )
            attempt_ended = _parse_time(
                attempt["ended_at"],
                f"{path}.attempts[{attempt_index}].ended_at",
                errors,
            )
            if attempt_started and attempt_ended and attempt_ended < attempt_started:
                errors.append(
                    f"{path}.attempts[{attempt_index}].ended_at: must not precede started_at"
                )
        coverage = step["inputs"]["excerpt_coverage"]
        if coverage["visible_characters"] > coverage["source_characters"]:
            errors.append(
                f"{path}.inputs.excerpt_coverage: visible characters exceed source characters"
            )
    if instance["termination"]["attempt_count"] != total_attempts:
        errors.append(
            "$.termination.attempt_count: must equal attempts across all steps"
        )
    if instance["termination"]["status"] not in TERMINATION_STATUSES:
        errors.append("$.termination.status: unknown termination status")
    stage = instance["stage"]
    if instance["experiment"] == "rq1_ledger":
        for index, step in enumerate(instance["steps"]):
            if step["inputs"]["profile"] is not None:
                errors.append(
                    f"$.steps[{index}].inputs.profile: Ledger stages must not supply a venue profile"
                )
        first_gold = instance["steps"][0]["inputs"]["gold_promises"]
        if stage == "gold_conditioned_status" and first_gold is None:
            errors.append(
                "$.steps[0].inputs.gold_promises: required for gold-conditioned status"
            )
        if stage != "gold_conditioned_status" and any(
            step["inputs"]["gold_promises"] is not None for step in instance["steps"]
        ):
            errors.append(
                "$.steps.inputs.gold_promises: forbidden outside gold-conditioned status"
            )
        if (
            stage == "end_to_end"
            and instance["termination"]["status"]
            in {"success", "classification_incomplete", "unknown_status"}
            and len(instance["steps"]) != 2
        ):
            errors.append(
                "$.steps: completed end-to-end records require extraction and classification steps"
            )
    if (
        instance["experiment"] == "rq3_venue"
        and instance["steps"][0]["inputs"]["profile"] is None
    ):
        errors.append("$.steps[0].inputs.profile: required for venue profile isolation")
    return errors


def validate_instance(
    instance: Any,
    schema_id: str,
    schema_dir: Path,
    resolver: ArtifactResolver | None = None,
) -> list[str]:
    """Validate one record, including cross-field semantics where applicable."""

    try:
        schema = load_schema(schema_dir, schema_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    errors = _schema_errors(instance, schema)
    errors.extend(find_secret_issues(instance))
    if errors or not isinstance(instance, dict):
        return errors
    if schema_id == "reviewer-validation-promise-gold/v1":
        errors.extend(_validate_promise_gold(instance, resolver))
    elif schema_id == "reviewer-validation-anchor-case/v1":
        errors.extend(_validate_anchor_case(instance, resolver))
    elif schema_id == "reviewer-validation-venue-applicability/v1":
        errors.extend(_validate_venue_applicability(instance, resolver))
    elif schema_id == "reviewer-validation-venue-review-score/v1":
        errors.extend(_validate_venue_score(instance))
    elif schema_id == "reviewer-validation-run-record/v1":
        errors.extend(_validate_run_record(instance))
    return errors


def validate_repository_relative_path(
    raw_path: str,
    repo_root: Path,
    protocol: dict[str, Any],
) -> tuple[Path | None, str | None]:
    if (
        not raw_path
        or "\\" in raw_path
        or re.match(r"^[A-Za-z]:", raw_path)
        or raw_path.startswith("/")
    ):
        return None, "path must be a normalized repository-relative POSIX path"
    pure = PurePosixPath(raw_path)
    if ".." in pure.parts or "." in pure.parts or str(pure) != raw_path:
        return None, "path must not contain dot segments or non-normalized separators"
    artifact_root = protocol["repository_boundaries"]["artifact_root"]
    allowed_inputs = set(protocol["repository_boundaries"]["allowed_repository_inputs"])
    allowed = (
        raw_path == artifact_root
        or raw_path.startswith(f"{artifact_root}/")
        or raw_path in allowed_inputs
    )
    if not allowed:
        return None, "path is outside protocol-approved repository boundaries"
    resolved_root = repo_root.resolve()
    resolved = (resolved_root / Path(*pure.parts)).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None, "resolved path escapes repository"
    return resolved, None


def verify_detached_hash(target: Path, detached: Path) -> list[str]:
    if not target.is_file():
        return [f"missing target for detached hash: {target.name}"]
    if not detached.is_file():
        return [f"missing detached hash file: {detached.name}"]
    line = detached.read_text(encoding="ascii").strip()
    match = re.fullmatch(r"([0-9a-f]{64})\s+\*?([^\s]+)", line)
    if match is None:
        return [f"invalid detached hash format: {detached.name}"]
    expected, filename = match.groups()
    if filename != target.name:
        return [f"detached hash names {filename}, expected {target.name}"]
    actual = sha256_file(target)
    if actual != expected:
        return [f"detached hash mismatch: {target.name}"]
    return []


def _load_structured_artifact(path: Path, schema_id: str) -> list[Any]:
    if path.suffix.lower() == ".jsonl":
        records: list[Any] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"line {line_number}: invalid JSON") from exc
        return records
    if path.suffix.lower() == ".json":
        return [json.loads(path.read_text(encoding="utf-8"))]
    if path.suffix.lower() in {".yaml", ".yml"}:
        return [yaml.safe_load(path.read_text(encoding="utf-8"))]
    raise ValueError(
        f"schema {schema_id} cannot be applied to unsupported file type {path.suffix}"
    )


def _artifact_record_count(path: Path) -> int | None:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return sum(
            bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
        )
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        return len(value) if isinstance(value, list) else 1
    return None


def _strict_slot_errors(protocol: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if protocol["status"] != "frozen":
        errors.append("protocol status is draft; expected frozen")
    if protocol["protocol_version"].endswith("-draft"):
        errors.append("protocol_version is still a draft version")
    if not protocol["formal_run_authorized"]:
        errors.append("protocol formal_run_authorized is false")
    if protocol["execution"]["code_commit"] is None:
        errors.append("unfrozen execution slot: code_commit")
    for name, value in protocol["seeds"].items():
        if value is None:
            errors.append(f"unfrozen seed slot: {name}")
    for name, value in protocol["execution"]["model"].items():
        if value is None:
            errors.append(f"unfrozen model slot: {name}")
    if protocol["execution"]["retry_policy"]["max_same_provider_attempts"] is None:
        errors.append("unfrozen retry slot: max_same_provider_attempts")
    return errors


def verify_repository(
    *,
    allow_draft: bool,
    base_dir: Path | None = None,
    repo_root: Path | None = None,
) -> VerificationReport:
    base = (base_dir or Path(__file__).resolve().parents[1]).resolve()
    repo = (repo_root or base.parents[1]).resolve()
    schema_dir = base / "schemas"
    report = VerificationReport(mode="draft" if allow_draft else "strict")
    protocol_path = base / "protocol.yaml"
    manifest_path = base / "freeze_manifest.json"

    try:
        protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"cannot load protocol.yaml: {type(exc).__name__}")
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"cannot load freeze_manifest.json: {type(exc).__name__}")
        return report

    report.errors.extend(
        f"protocol {error}"
        for error in validate_instance(
            protocol, "reviewer-validation-protocol/v1", schema_dir
        )
    )
    report.errors.extend(
        f"manifest {error}"
        for error in validate_instance(
            manifest, "reviewer-validation-freeze-manifest/v1", schema_dir
        )
    )
    if report.errors:
        return report

    report.protocol_sha256 = sha256_file(protocol_path)
    report.manifest_sha256 = sha256_file(manifest_path)
    report.errors.extend(verify_detached_hash(protocol_path, base / "protocol.sha256"))
    report.errors.extend(
        verify_detached_hash(manifest_path, base / "freeze_manifest.sha256")
    )
    if manifest["protocol"]["sha256"] != report.protocol_sha256:
        report.errors.append(
            "freeze manifest protocol hash does not match protocol.yaml"
        )
    if manifest["protocol_version"] != protocol["protocol_version"]:
        report.errors.append(
            "freeze manifest protocol_version does not match protocol.yaml"
        )
    if manifest["protocol"]["schema_version"] != protocol["schema_version"]:
        report.errors.append("freeze manifest protocol schema version mismatch")

    artifacts = manifest["artifacts"]
    ids = [artifact["artifact_id"] for artifact in artifacts]
    for artifact_id in sorted({item for item in ids if ids.count(item) > 1}):
        report.errors.append(f"duplicate artifact ID: {artifact_id}")
    paths = [artifact["path"] for artifact in artifacts]
    for artifact_path in sorted({item for item in paths if paths.count(item) > 1}):
        report.errors.append(f"duplicate artifact path: {artifact_path}")

    resolved_by_id: dict[str, Path] = {}
    for artifact in artifacts:
        artifact_id = artifact["artifact_id"]
        resolved, path_error = validate_repository_relative_path(
            artifact["path"], repo, protocol
        )
        if path_error:
            report.errors.append(f"artifact {artifact_id}: {path_error}")
            continue
        assert resolved is not None
        resolved_by_id[artifact_id] = resolved

    def resolver(artifact_id: str) -> bytes:
        return resolved_by_id[artifact_id].read_bytes()

    for artifact in artifacts:
        artifact_id = artifact["artifact_id"]
        path = resolved_by_id.get(artifact_id)
        if path is None:
            continue
        exists = path.is_file()
        supplied_hash = artifact["sha256"]
        supplied_length = artifact["byte_length"]
        if not exists:
            report.pending_artifacts.append(artifact_id)
            message = f"artifact {artifact_id}: missing {artifact['path']}"
            if allow_draft:
                report.warnings.append(message)
            elif artifact["required_for_strict"]:
                report.errors.append(message)
            continue
        actual = path.read_bytes()
        if supplied_hash is None or supplied_length is None:
            report.pending_artifacts.append(artifact_id)
            message = f"artifact {artifact_id}: hash or byte_length is not frozen"
            if allow_draft:
                report.warnings.append(message)
            else:
                report.errors.append(message)
            continue
        if sha256_bytes(actual) != supplied_hash:
            report.errors.append(f"artifact {artifact_id}: SHA-256 mismatch")
            continue
        if len(actual) != supplied_length:
            report.errors.append(f"artifact {artifact_id}: byte_length mismatch")
            continue
        if artifact["record_count"] is not None:
            try:
                actual_record_count = _artifact_record_count(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                report.errors.append(
                    f"artifact {artifact_id}: cannot count records: {type(exc).__name__}"
                )
                continue
            if (
                actual_record_count is not None
                and actual_record_count != artifact["record_count"]
            ):
                report.errors.append(f"artifact {artifact_id}: record_count mismatch")
                continue
        if not allow_draft:
            if artifact["status"] != "verified":
                report.errors.append(f"artifact {artifact_id}: status is not verified")
            if artifact["formal_input"] and not artifact["immutable"]:
                report.errors.append(
                    f"artifact {artifact_id}: formal input is not immutable"
                )
            if artifact["created_at"] is None:
                report.errors.append(
                    f"artifact {artifact_id}: created_at is not frozen"
                )
        schema_id = artifact["schema_id"]
        if schema_id is not None:
            try:
                records = _load_structured_artifact(path, schema_id)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                report.errors.append(f"artifact {artifact_id}: {exc}")
                continue
            if (
                artifact["record_count"] is not None
                and len(records) != artifact["record_count"]
            ):
                report.errors.append(f"artifact {artifact_id}: record_count mismatch")
            for record_index, record in enumerate(records):
                record_errors = validate_instance(
                    record, schema_id, schema_dir, resolver
                )
                report.errors.extend(
                    f"artifact {artifact_id}[{record_index}] {error}"
                    for error in record_errors
                )
        report.verified_artifacts.append(artifact_id)

    required_ids = set(protocol["freeze_contract"]["required_artifact_ids"])
    listed_ids = set(ids)
    for artifact_id in sorted(required_ids - listed_ids):
        message = f"required artifact not listed: {artifact_id}"
        if allow_draft:
            report.warnings.append(message)
        else:
            report.errors.append(message)

    if not allow_draft:
        report.errors.extend(_strict_slot_errors(protocol))
        if manifest["manifest_status"] != "frozen":
            report.errors.append("freeze manifest status is draft; expected frozen")
        if manifest["generated_at"] is None:
            report.errors.append("freeze manifest generated_at is not frozen")
        if not manifest["formal_run_authorized"]:
            report.errors.append("freeze manifest formal_run_authorized is false")
        if "freeze_manifest" in listed_ids or any(
            path.endswith("freeze_manifest.json") for path in paths
        ):
            report.errors.append(
                "freeze manifest must not contain a self-hash artifact"
            )
        category_counts: dict[str, int] = {}
        for artifact in artifacts:
            category_counts[artifact["category"]] = (
                category_counts.get(artifact["category"], 0) + 1
            )
        seen_requirements: set[str] = set()
        for requirement in protocol["freeze_contract"]["category_requirements"]:
            category = requirement["category"]
            if category in seen_requirements:
                report.errors.append(f"duplicate category requirement: {category}")
                continue
            seen_requirements.add(category)
            actual_count = category_counts.get(category, 0)
            if (
                requirement["exact_count"] is not None
                and actual_count != requirement["exact_count"]
            ):
                report.errors.append(
                    f"artifact category {category}: expected exactly {requirement['exact_count']}, found {actual_count}"
                )
            if (
                requirement["minimum_count"] is not None
                and actual_count < requirement["minimum_count"]
            ):
                report.errors.append(
                    f"artifact category {category}: expected at least {requirement['minimum_count']}, found {actual_count}"
                )
        listed_paths = set(paths)
        for raw_root in protocol["freeze_contract"]["formal_input_roots"]:
            root_path, path_error = validate_repository_relative_path(
                raw_root, repo, protocol
            )
            if path_error or root_path is None or not root_path.exists():
                continue
            for file_path in root_path.rglob("*"):
                if not file_path.is_file():
                    continue
                relative = file_path.relative_to(repo).as_posix()
                if relative not in listed_paths:
                    report.errors.append(f"unlisted formal input: {relative}")

    report.formal_run_authorized = (
        not allow_draft
        and report.ok
        and protocol["formal_run_authorized"]
        and manifest["formal_run_authorized"]
        and protocol["status"] == "frozen"
        and manifest["manifest_status"] == "frozen"
    )
    return report


def require_formal_run_ready(
    *, base_dir: Path | None = None, repo_root: Path | None = None
) -> VerificationReport:
    """Strict preflight for formal runners; raises without reading formal inputs."""

    report = verify_repository(
        allow_draft=False, base_dir=base_dir, repo_root=repo_root
    )
    if not report.formal_run_authorized:
        details = "; ".join(report.errors[:20])
        if len(report.errors) > 20:
            details += f"; and {len(report.errors) - 20} more"
        raise FreezeVerificationError(
            f"formal run blocked by G2 freeze gate: {details}"
        )
    return report


def _print_report(report: VerificationReport) -> None:
    print(f"MODE: {report.mode}")
    if report.protocol_sha256:
        print(f"PROTOCOL_SHA256: {report.protocol_sha256}")
    if report.manifest_sha256:
        print(f"FREEZE_MANIFEST_SHA256: {report.manifest_sha256}")
    print(f"VERIFIED_ARTIFACTS: {len(report.verified_artifacts)}")
    print(f"PENDING_ARTIFACTS: {len(report.pending_artifacts)}")
    for artifact_id in report.pending_artifacts:
        print(f"PENDING: {artifact_id}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")
    print(f"FORMAL_RUN: {'AUTHORIZED' if report.formal_run_authorized else 'BLOCKED'}")
    print(f"RESULT: {'PASS' if report.ok else 'FAIL'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="validate scaffold structure while keeping formal runs blocked",
    )
    args = parser.parse_args(argv)
    report = verify_repository(allow_draft=args.allow_draft)
    _print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
