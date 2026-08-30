"""Deterministically generate Anchor challenge cases without running Anchor.

Formal generation is intentionally separate from formal execution: this script
only transforms coordinator-reviewed source anchors and validates the resulting
case records against Work C's frozen schema.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
SCHEMA_DIR = BASE_DIR / "schemas"
GENERATOR_PATH = Path(__file__).resolve()
CONTEXT_CHARS = 48
SOURCE_SCHEMA = "reviewer-validation-anchor-source/v1"
CASE_SCHEMA = "reviewer-validation-anchor-case/v1"
PRIMARY_STRATA = {
    "short_quote",
    "long_quote",
    "duplicated_exact_quote",
    "heading_boundary",
    "similar_distractor",
}
ANCHORED_OPERATIONS = (
    "insert_before",
    "delete_before",
    "move_before",
    "whitespace_change",
)
DRIFTED_OPERATIONS = ("local_rewrite", "substitution", "paraphrase")
KNOWN_PROBES = {"duplicate_exact_second", "deleted_target_similar_distractor"}


def _load_verify() -> Any:
    path = Path(__file__).with_name("verify_freeze.py")
    name = "reviewer_validation_verify_freeze_for_anchor_generation"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Work C freeze verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load_verify()


class GenerationError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_jsonl(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GenerationError(f"source file is not UTF-8: {path}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GenerationError(f"invalid JSON at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise GenerationError(
                f"source record must be an object at {path}:{line_number}"
            )
        records.append(value)
    if not records:
        raise GenerationError("source list is empty")
    return raw, records


def _read_seed(path: Path) -> tuple[bytes, int]:
    raw = path.read_bytes()
    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise GenerationError("seed file must be ASCII") from exc
    if not re.fullmatch(r"[0-9]+", value):
        raise GenerationError("seed file must contain one non-negative base-10 integer")
    return raw, int(value)


def _ensure_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise GenerationError(
            f"{label} escapes reviewer-validation boundary: {resolved}"
        ) from exc
    return resolved


def _validate_source(source: dict[str, Any], *, mode: str) -> None:
    allowed = {
        "schema_version",
        "source_anchor_id",
        "doc_id",
        "primary_stratum",
        "cross_tags",
        "boundary_tags",
        "source_text",
        "source_text_sha256",
        "anchor",
        "transform_inputs",
        "development_only",
        "operation_overrides",
        "known_probe",
    }
    required = {
        "schema_version",
        "source_anchor_id",
        "doc_id",
        "primary_stratum",
        "cross_tags",
        "boundary_tags",
        "source_text",
        "source_text_sha256",
        "anchor",
        "transform_inputs",
        "development_only",
    }
    missing = sorted(required - source.keys())
    unknown = sorted(source.keys() - allowed)
    if missing or unknown:
        raise GenerationError(
            f"source {source.get('source_anchor_id', '<unknown>')}: missing={missing}, unknown={unknown}"
        )
    if source["schema_version"] != SOURCE_SCHEMA:
        raise GenerationError("unknown anchor source schema")
    source_id = source["source_anchor_id"]
    if not isinstance(source_id, str) or not re.fullmatch(
        r"[A-Za-z0-9._-]+", source_id
    ):
        raise GenerationError("source_anchor_id must be path-safe ASCII")
    if source["primary_stratum"] not in PRIMARY_STRATA:
        raise GenerationError(f"source {source_id}: unknown primary_stratum")
    if not isinstance(source["cross_tags"], list) or not all(
        isinstance(item, str) and item for item in source["cross_tags"]
    ):
        raise GenerationError(
            f"source {source_id}: cross_tags must be non-empty strings"
        )
    if not isinstance(source["boundary_tags"], list) or not all(
        item in {"near_heading", "document_start", "document_end"}
        for item in source["boundary_tags"]
    ):
        raise GenerationError(f"source {source_id}: invalid boundary_tags")
    if bool(source["development_only"]) != (mode == "dev"):
        raise GenerationError(
            f"source {source_id}: development_only does not match mode"
        )
    if mode == "formal" and (
        source.get("operation_overrides") or source.get("known_probe")
    ):
        raise GenerationError(
            f"source {source_id}: development-only controls are forbidden formally"
        )
    if source.get("known_probe") not in {None, *KNOWN_PROBES}:
        raise GenerationError(f"source {source_id}: unknown development probe")

    text = source["source_text"]
    if not isinstance(text, str) or not text:
        raise GenerationError(f"source {source_id}: source_text must be non-empty")
    if source["source_text_sha256"] != _sha(text.encode("utf-8")):
        raise GenerationError(f"source {source_id}: source_text_sha256 mismatch")
    anchor = source["anchor"]
    if not isinstance(anchor, dict):
        raise GenerationError(f"source {source_id}: anchor must be an object")
    anchor_allowed = {
        "id",
        "doc_id",
        "char_start",
        "char_end",
        "quote",
        "context_before",
        "context_after",
        "section_path",
        "status",
    }
    if set(anchor) != anchor_allowed:
        raise GenerationError(
            f"source {source_id}: anchor fields do not match production Anchor"
        )
    start, end, quote = anchor["char_start"], anchor["char_end"], anchor["quote"]
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or not (0 <= start < end <= len(text))
    ):
        raise GenerationError(f"source {source_id}: invalid half-open source span")
    if text[start:end] != quote:
        raise GenerationError(f"source {source_id}: quote does not equal source span")
    if anchor["doc_id"] != source["doc_id"] or anchor["id"] != source_id:
        raise GenerationError(f"source {source_id}: anchor identity mismatch")
    if anchor["status"] != "anchored":
        raise GenerationError(f"source {source_id}: source anchor must be anchored")
    expected_before = text[max(0, start - CONTEXT_CHARS) : start]
    expected_after = text[end : end + CONTEXT_CHARS]
    if (
        anchor["context_before"] != expected_before
        or anchor["context_after"] != expected_after
    ):
        raise GenerationError(
            f"source {source_id}: stored context does not match production window"
        )

    inputs = source["transform_inputs"]
    if not isinstance(inputs, dict):
        raise GenerationError(f"source {source_id}: transform_inputs must be an object")
    drifted = inputs.get("drifted_quotes")
    if not isinstance(drifted, dict) or set(drifted) != set(DRIFTED_OPERATIONS):
        raise GenerationError(
            f"source {source_id}: all drifted quote variants are required"
        )
    for operation, replacement in drifted.items():
        if not isinstance(replacement, str) or not replacement or replacement == quote:
            raise GenerationError(
                f"source {source_id}: invalid {operation} replacement"
            )
    distractor = inputs.get("similar_distractor")
    if not isinstance(distractor, str) or not distractor:
        raise GenerationError(f"source {source_id}: similar_distractor is required")
    if quote in distractor:
        raise GenerationError(
            f"source {source_id}: distractor must not contain the exact quote"
        )
    override = source.get("operation_overrides") or {}
    if not isinstance(override, dict) or set(override) - {"anchored", "drifted"}:
        raise GenerationError(f"source {source_id}: invalid operation_overrides")
    if override.get("anchored") not in {None, *ANCHORED_OPERATIONS}:
        raise GenerationError(f"source {source_id}: invalid anchored override")
    if override.get("drifted") not in {None, *DRIFTED_OPERATIONS}:
        raise GenerationError(f"source {source_id}: invalid drifted override")
    if inputs.get("lost_text_override") is not None:
        if mode != "dev" or not isinstance(inputs["lost_text_override"], str):
            raise GenerationError(
                f"source {source_id}: lost_text_override is development-only"
            )
        if quote in inputs["lost_text_override"]:
            raise GenerationError(
                f"source {source_id}: lost_text_override retains exact source quote"
            )

    secret_issues = VERIFY.find_secret_issues(source)
    if secret_issues:
        raise GenerationError(
            f"source {source_id}: secret-like content rejected: {secret_issues[0]}"
        )


def _operation_assignments(
    sources: list[dict[str, Any]], seed: int, *, mode: str
) -> dict[str, tuple[str, str]]:
    source_ids = [item["source_anchor_id"] for item in sources]
    if mode == "formal":
        anchored = [operation for operation in ANCHORED_OPERATIONS for _ in range(10)]
        drifted = ["local_rewrite"] * 14 + ["substitution"] * 13 + ["paraphrase"] * 13
        random.Random(seed ^ 0xA11CE).shuffle(anchored)
        random.Random(seed ^ 0xD21F7).shuffle(drifted)
    else:
        anchored = [
            ANCHORED_OPERATIONS[index % len(ANCHORED_OPERATIONS)]
            for index in range(len(sources))
        ]
        drifted = [
            DRIFTED_OPERATIONS[index % len(DRIFTED_OPERATIONS)]
            for index in range(len(sources))
        ]
        random.Random(seed ^ 0xA11CE).shuffle(anchored)
        random.Random(seed ^ 0xD21F7).shuffle(drifted)
    assignments: dict[str, tuple[str, str]] = {}
    for index, source_id in enumerate(source_ids):
        overrides = sources[index].get("operation_overrides") or {}
        assignments[source_id] = (
            overrides.get("anchored", anchored[index]),
            overrides.get("drifted", drifted[index]),
        )
    return assignments


def _anchored_transform(
    source: dict[str, Any], operation: str
) -> tuple[str, str, int, int]:
    text = source["source_text"]
    anchor = source["anchor"]
    start, _end, quote = anchor["char_start"], anchor["char_end"], anchor["quote"]
    inputs = source["transform_inputs"]
    if operation == "insert_before":
        insertion = inputs.get("insert_text", "Development preface. ")
        if not isinstance(insertion, str) or not insertion:
            raise GenerationError("insert_text must be non-empty")
        transformed = insertion + text
        new_start = start + len(insertion)
    elif operation == "delete_before":
        count = inputs.get("delete_before_chars", min(8, start))
        if not isinstance(count, int) or not (1 <= count <= start):
            raise GenerationError(
                f"source {source['source_anchor_id']}: delete_before is infeasible"
            )
        transformed = text[: start - count] + text[start:]
        new_start = start - count
    elif operation == "move_before":
        if start <= 0:
            raise GenerationError(
                f"source {source['source_anchor_id']}: move_before is infeasible"
            )
        separator = inputs.get("move_separator", "\n")
        if not isinstance(separator, str):
            raise GenerationError("move_separator must be a string")
        transformed = text[start:] + separator + text[:start]
        new_start = 0
    elif operation == "whitespace_change":
        prefix = text[:start]
        match = re.search(r"\s", prefix)
        if match:
            offset = match.start()
            transformed = text[:offset] + text[offset] + text[offset:]
            new_start = start + 1
        else:
            transformed = "\n" + text
            new_start = start + 1
    else:
        raise GenerationError(f"unknown anchored operation: {operation}")
    new_end = new_start + len(quote)
    if transformed[new_start:new_end] != quote:
        raise GenerationError(
            "anchored transformation did not preserve the exact source quote"
        )
    return transformed, quote, new_start, new_end


def _drifted_transform(
    source: dict[str, Any], operation: str
) -> tuple[str, str, int, int]:
    text = source["source_text"]
    anchor = source["anchor"]
    start, end = anchor["char_start"], anchor["char_end"]
    replacement = source["transform_inputs"]["drifted_quotes"][operation]
    transformed = text[:start] + replacement + text[end:]
    return transformed, replacement, start, start + len(replacement)


def _lost_transform(source: dict[str, Any]) -> str:
    inputs = source["transform_inputs"]
    override = inputs.get("lost_text_override")
    if override is not None:
        return override
    text = source["source_text"]
    start, end = source["anchor"]["char_start"], source["anchor"]["char_end"]
    without_target = text[:start] + text[end:]
    return without_target.rstrip() + "\n" + inputs["similar_distractor"]


def _case_record(
    source: dict[str, Any],
    *,
    variant: str,
    operation: str,
    seed: int,
    generator_sha256: str,
    sources_sha256: str,
    seed_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    source_id = source["source_anchor_id"]
    case_id = f"{source_id}--{variant}"
    if variant == "anchored":
        text, gold_quote, start, end = _anchored_transform(source, operation)
        gold_span: dict[str, int] | None = {"char_start": start, "char_end": end}
    elif variant == "drifted":
        text, gold_quote, start, end = _drifted_transform(source, operation)
        gold_span = {"char_start": start, "char_end": end}
    elif variant == "lost":
        text = _lost_transform(source)
        gold_quote = None
        gold_span = None
    else:
        raise GenerationError(f"unknown variant: {variant}")
    text_bytes = text.encode("utf-8")
    artifact_id = f"anchor_texts/{case_id}.txt"
    transformation = {
        "operation": operation,
        "description": f"deterministic {operation} transformation for {source_id}",
    }
    input_identity = {
        "generator_sha256": generator_sha256,
        "sources_sha256": sources_sha256,
        "seed_sha256": seed_sha256,
        "seed": seed,
        "source": source,
        "variant": variant,
        "transformation": transformation,
        "transformed_text_sha256": _sha(text_bytes),
        "gold_quote": gold_quote,
        "gold_span": gold_span,
    }
    record = {
        "schema_version": CASE_SCHEMA,
        "case_id": case_id,
        "source_anchor_id": source_id,
        "cluster_id": source_id,
        "variant": variant,
        "gold_status": variant,
        "source_quote": source["anchor"]["quote"],
        "transformed_text": {"artifact_id": artifact_id, "sha256": _sha(text_bytes)},
        "gold_quote": gold_quote,
        "gold_span": gold_span,
        "transformation": transformation,
        "generator_seed": seed,
        "item_input_sha256": _sha(_json_bytes(input_identity)),
        "denominators": {"variant_occurrence": 1, "source_anchor_cluster": 1},
    }
    return record, text_bytes


def _tree_digest(files: dict[str, bytes]) -> str:
    payload = b"".join(
        relative.encode("utf-8")
        + b"\0"
        + _sha(data).encode("ascii")
        + b"\0"
        + str(len(data)).encode("ascii")
        + b"\n"
        for relative, data in sorted(files.items())
    )
    return _sha(payload)


def _validate_formal_sources(sources: list[dict[str, Any]]) -> None:
    if len(sources) != 40:
        raise GenerationError("formal staging requires exactly 40 source anchors")
    strata = Counter(item["primary_stratum"] for item in sources)
    if strata != Counter({name: 8 for name in PRIMARY_STRATA}):
        raise GenerationError(f"formal primary-stratum quota mismatch: {dict(strata)}")
    boundary_sources = [
        item for item in sources if item["primary_stratum"] == "heading_boundary"
    ]
    boundary_counts = Counter(
        tag for item in boundary_sources for tag in item["boundary_tags"]
    )
    for tag in ("near_heading", "document_start", "document_end"):
        if boundary_counts[tag] < 2:
            raise GenerationError(
                f"formal heading/boundary sources need at least two {tag} tags"
            )


def generate_anchor_challenges(
    *, mode: str, sources_path: Path, seed_path: Path, output_dir: Path
) -> dict[str, Any]:
    sources_path = _ensure_within(sources_path, BASE_DIR, "sources")
    seed_path = _ensure_within(seed_path, BASE_DIR, "seed")
    output_dir = _ensure_within(output_dir, BASE_DIR, "output")
    if mode == "formal":
        expected_sources = (BASE_DIR / "challenges" / "anchor_sources.jsonl").resolve()
        expected_seed = (
            BASE_DIR / "configs" / "seeds" / "anchor_challenge.txt"
        ).resolve()
        expected_output = (BASE_DIR / "challenges").resolve()
        if (
            sources_path != expected_sources
            or seed_path != expected_seed
            or output_dir != expected_output
        ):
            raise GenerationError(
                "formal generation requires canonical sources, seed, and output paths"
            )
    elif mode != "dev":
        raise GenerationError(f"unknown mode: {mode}")

    source_bytes, sources = _read_jsonl(sources_path)
    seed_bytes, seed = _read_seed(seed_path)
    ids = [item.get("source_anchor_id") for item in sources]
    if len(ids) != len(set(ids)):
        raise GenerationError("duplicate source_anchor_id")
    for source in sources:
        _validate_source(source, mode=mode)
    if mode == "formal":
        _validate_formal_sources(sources)

    targets = [
        output_dir / "anchor_cases.jsonl",
        output_dir / "anchor_texts",
        output_dir / "anchor_generation_manifest.json",
        output_dir / "anchor_generation_manifest.sha256",
    ]
    for target in targets:
        if target.exists():
            raise GenerationError(
                f"refusing to overwrite existing generation target: {target}"
            )
    snapshot_path = output_dir / "anchor_sources.jsonl"
    if snapshot_path.exists() and snapshot_path.resolve() != sources_path:
        raise GenerationError(
            f"refusing to overwrite existing source snapshot: {snapshot_path}"
        )

    generator_sha = _sha(GENERATOR_PATH.read_bytes())
    sources_sha = _sha(source_bytes)
    seed_sha = _sha(seed_bytes)
    assignments = _operation_assignments(sources, seed, mode=mode)
    cases: list[dict[str, Any]] = []
    text_files: dict[str, bytes] = {}
    for source in sources:
        anchored_operation, drifted_operation = assignments[source["source_anchor_id"]]
        for variant, operation in (
            ("anchored", anchored_operation),
            ("drifted", drifted_operation),
            ("lost", "delete_target_with_distractor"),
        ):
            record, text_bytes = _case_record(
                source,
                variant=variant,
                operation=operation,
                seed=seed,
                generator_sha256=generator_sha,
                sources_sha256=sources_sha,
                seed_sha256=seed_sha,
            )
            cases.append(record)
            text_files[record["transformed_text"]["artifact_id"]] = text_bytes

    resolver = text_files.__getitem__
    errors: list[str] = []
    for record in cases:
        errors.extend(
            f"{record['case_id']}: {error}"
            for error in VERIFY.validate_instance(
                record, CASE_SCHEMA, SCHEMA_DIR, resolver
            )
        )
    if errors:
        raise GenerationError(
            "generated case schema validation failed: " + "; ".join(errors[:10])
        )
    expected_count = len(sources) * 3
    variants = Counter(record["variant"] for record in cases)
    if len(cases) != expected_count or variants != Counter(
        {name: len(sources) for name in ("anchored", "drifted", "lost")}
    ):
        raise GenerationError(
            "generator did not produce exactly one case per source and variant"
        )
    if mode == "formal":
        anchored_ops = Counter(
            record["transformation"]["operation"]
            for record in cases
            if record["variant"] == "anchored"
        )
        drifted_ops = Counter(
            record["transformation"]["operation"]
            for record in cases
            if record["variant"] == "drifted"
        )
        if anchored_ops != Counter(
            {operation: 10 for operation in ANCHORED_OPERATIONS}
        ):
            raise GenerationError(
                f"formal anchored operation quota mismatch: {dict(anchored_ops)}"
            )
        if drifted_ops != Counter(
            {"local_rewrite": 14, "substitution": 13, "paraphrase": 13}
        ):
            raise GenerationError(
                f"formal drifted operation quota mismatch: {dict(drifted_ops)}"
            )

    cases_bytes = b"".join(_json_bytes(record) for record in cases)
    tree_files = {
        "anchor_cases.jsonl": cases_bytes,
        "anchor_sources.jsonl": source_bytes,
        **text_files,
    }
    tree_sha = _tree_digest(tree_files)
    manifest = {
        "schema_version": "reviewer-validation-anchor-generation/v1",
        "mode": mode,
        "generator_sha256": generator_sha,
        "sources_sha256": sources_sha,
        "seed_file_sha256": seed_sha,
        "generator_seed": seed,
        "source_count": len(sources),
        "case_count": len(cases),
        "variant_counts": dict(sorted(variants.items())),
        "operation_counts": dict(
            sorted(
                Counter(
                    record["transformation"]["operation"] for record in cases
                ).items()
            )
        ),
        "artifact_tree_sha256": tree_sha,
        "files": [
            {"path": path, "sha256": _sha(data), "byte_length": len(data)}
            for path, data in sorted(tree_files.items())
        ],
    }
    if VERIFY.find_secret_issues(manifest):
        raise GenerationError("generation manifest contains secret-like fields")

    output_dir.mkdir(parents=True, exist_ok=True)
    text_dir = output_dir / "anchor_texts"
    text_dir.mkdir()
    if snapshot_path.resolve() != sources_path:
        snapshot_path.write_bytes(source_bytes)
    for relative, data in sorted(text_files.items()):
        target = output_dir / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output_dir / "anchor_cases.jsonl").write_bytes(cases_bytes)
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    (output_dir / "anchor_generation_manifest.json").write_bytes(manifest_bytes)
    (output_dir / "anchor_generation_manifest.sha256").write_text(
        f"{_sha(manifest_bytes)}  anchor_generation_manifest.json\n", encoding="ascii"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    anchor = subparsers.add_parser("anchor")
    anchor.add_argument("--mode", choices=("dev", "formal"), required=True)
    anchor.add_argument("--sources", type=Path, required=True)
    anchor.add_argument("--seed-file", type=Path, required=True)
    anchor.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = generate_anchor_challenges(
            mode=args.mode,
            sources_path=args.sources,
            seed_path=args.seed_file,
            output_dir=args.output_dir,
        )
    except (GenerationError, OSError, ValueError) as exc:
        print(f"ANCHOR_GENERATION: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print(f"ANCHOR_GENERATION: PASS ({manifest['case_count']} cases)")
    print(f"ARTIFACT_TREE_SHA256: {manifest['artifact_tree_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
