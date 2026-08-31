"""Fail-closed development-only DeepSeek model-screen entrypoint.

The current command is a zero-network preflight. Paid execution stays blocked
until the two-human paper audit is locked and the run writer is implemented.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import random
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
VALIDATION_ROOT = REPO_ROOT / "methods" / "reviewer_validation"
DEVELOPMENT_ROOT = VALIDATION_ROOT / "inputs" / "development"
MANIFEST_PATH = DEVELOPMENT_ROOT / "manifest.yaml"
MODEL_SELECTION_PATH = DEVELOPMENT_ROOT / "model_selection.yaml"
MODEL_OUTPUT_ROOT = VALIDATION_ROOT / "outputs" / "pilot" / "model_selection"
MODEL_PRIVATE_ROOT = VALIDATION_ROOT / "outputs" / "pilot" / "model_selection_private"
LEDGER_OUTPUT_ROOT = (
    VALIDATION_ROOT / "outputs" / "pilot" / "ledger" / "model-selection"
)
RUNTIME_CONFIG_PATH = PYTHON_ROOT / "config" / "default.yaml"
RUNTIME_LOCAL_CONFIG_PATH = PYTHON_ROOT / "config" / "default.local.yaml"
PROVIDER_PRESETS_PATH = REPO_ROOT / "config" / "providers.yaml"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from run_ledger import execute_ledger_mode, write_execution_record  # noqa: E402
from run_venue_ab import run_venue_invocation  # noqa: E402

from src.argument.llm_client import _initial_token_budget  # noqa: E402
from src.argument.reviewer import _load_venue_profile  # noqa: E402
from src.llm_request_policy import (  # noqa: E402
    apply_reasoning_effort_policy,
    apply_thinking_policy,
)
from src.translator.cloud_client import CloudClient  # noqa: E402

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_VALID_TERMINATIONS = frozenset({"success", "legal_empty"})


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    return value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _repo_path(value: str) -> Path:
    path = (REPO_ROOT / value).resolve()
    if not path.is_relative_to(REPO_ROOT.resolve()):
        raise ValueError(f"path escapes repository: {value}")
    return path


def _development_path(value: str) -> Path:
    path = _repo_path(value)
    if not path.is_relative_to(DEVELOPMENT_ROOT.resolve()):
        raise ValueError(f"model screen may read development inputs only: {value}")
    return path


def _verify_file(path: Path, record: dict[str, Any]) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing preflight input: {path}")
    data = path.read_bytes()
    expected_hash = str(record.get("sha256", ""))
    if _sha256_bytes(data) != expected_hash:
        raise ValueError(f"hash drift detected: {path.relative_to(REPO_ROOT)}")
    if "byte_length" in record and len(data) != int(record["byte_length"]):
        raise ValueError(f"byte-length drift detected: {path.relative_to(REPO_ROOT)}")


def verify_development_inventory(manifest: dict[str, Any]) -> int:
    if manifest.get("development_only") is not True:
        raise ValueError("development manifest must be development_only")
    if manifest.get("formal_run_authorized") is not False:
        raise ValueError("development preflight refuses formal authorization")
    if manifest.get("external_model_output_seen_before_selection") is not False:
        raise ValueError("paper selection was not isolated from external model output")

    verified = 0
    protocol = manifest["protocol"]
    protocol_path = _repo_path(protocol["path"])
    _verify_file(protocol_path, protocol)
    verified += 1

    model_selection_record = manifest.get("model_selection")
    if not isinstance(model_selection_record, dict):
        raise ValueError("development manifest must bind model_selection.yaml")
    model_selection_path = _development_path(model_selection_record["path"])
    _verify_file(model_selection_path, model_selection_record)
    verified += 1

    for source in manifest["code_state"]["source_files"]:
        source_path = _repo_path(source["path"])
        _verify_file(source_path, source)
        verified += 1

    papers = manifest.get("papers", [])
    if len(papers) != 2:
        raise ValueError("development model screen requires exactly two papers")
    for paper in papers:
        if paper.get("group") != "development":
            raise ValueError(f"non-development paper rejected: {paper.get('paper_id')}")
        source = paper["local_source"]
        _verify_file(_development_path(source["path"]), source)
        verified += 1
        parsed = paper["parsed_full_text"]
        _verify_file(_development_path(parsed["path"]), parsed)
        verified += 1
        for excerpt in paper["production_excerpts"].values():
            _verify_file(_development_path(excerpt["path"]), excerpt)
            verified += 1
    return verified


def verify_model_execution_state(config: dict[str, Any]) -> dict[str, Any]:
    state = config.get("execution_code_state")
    if not isinstance(state, dict):
        raise ValueError("model-selection execution_code_state is missing")
    current_commit = _git_commit()
    if state.get("base_commit") != current_commit:
        raise ValueError("model-selection base commit drifted")
    records: list[dict[str, Any]] = []
    for source in state.get("source_files", []):
        path = _repo_path(source["path"])
        _verify_file(path, source)
        records.append(
            {
                "path": source["path"],
                "sha256": source["sha256"],
                "byte_length": path.stat().st_size,
            }
        )
    if not records:
        raise ValueError("model-selection execution closure is empty")
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return {
        "base_commit": current_commit,
        "working_tree_clean_required": bool(
            state.get("working_tree_clean_required", False)
        ),
        "verified_source_files": len(records),
        "closure_sha256": _sha256_bytes(canonical.encode("utf-8")),
        "source_files": records,
    }


def _strip_empty_strings(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = _strip_empty_strings(item)
            if nested:
                result[key] = nested
        elif item != "":
            result[key] = item
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_runtime_cloud_config() -> dict[str, Any]:
    config = _load_yaml(RUNTIME_CONFIG_PATH)
    if RUNTIME_LOCAL_CONFIG_PATH.is_file():
        local = _strip_empty_strings(_load_yaml(RUNTIME_LOCAL_CONFIG_PATH))
        config = _deep_merge(config, local)
    environment_key = os.environ.get("SCHOLAR_CLOUD_API_KEY", "").strip()
    cloud = copy.deepcopy(config.get("translator", {}).get("cloud", {}))
    if environment_key:
        cloud["api_key"] = environment_key
    return cloud


def build_run_plan(config: dict[str, Any]) -> dict[str, Any]:
    design = config["screen_design"]
    models = [item["model_id"] for item in config["candidates"]]
    labels = list(design["blind_model_labels"])
    if (
        len(models) != 2
        or len(set(models)) != 2
        or len(labels) != 2
        or len(set(labels)) != 2
    ):
        raise ValueError(
            "model screen requires two unique models and two unique labels"
        )

    label_rng = random.Random(int(design["blind_label_seed"]))
    shuffled_models = list(models)
    label_rng.shuffle(shuffled_models)
    model_to_label = dict(zip(shuffled_models, labels, strict=True))

    blocks = [
        {
            "paper_id": paper_id,
            "workflow": workflow["id"],
            "repetition": repetition,
        }
        for workflow in config["workflows"]
        for paper_id in workflow["papers"]
        for repetition in range(
            1, int(design["repetitions_per_model_paper_workflow"]) + 1
        )
    ]
    order_rng = random.Random(int(design["run_order_seed"]))
    order_rng.shuffle(blocks)

    slots: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks, start=1):
        model_order = list(models)
        order_rng.shuffle(model_order)
        pair_id = f"pair-{block_index:02d}"
        for position, model_id in enumerate(model_order, start=1):
            blind_label = model_to_label[model_id]
            slots.append(
                {
                    **block,
                    "pair_id": pair_id,
                    "slot_id": f"{pair_id}-{blind_label.lower()}",
                    "position": position,
                    "model_id": model_id,
                    "blind_label": blind_label,
                }
            )

    expected_total = int(design["total_invocations"])
    if len(slots) != expected_total:
        raise ValueError(f"run plan has {len(slots)} slots, expected {expected_total}")
    counts = {
        model: sum(slot["model_id"] == model for slot in slots) for model in models
    }
    expected_per_model = int(design["invocations_per_model"])
    if set(counts.values()) != {expected_per_model}:
        raise ValueError(f"unbalanced model plan: {counts}")

    canonical = json.dumps(
        slots, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    label_to_model = {label: model for model, label in model_to_label.items()}
    mapping = json.dumps(model_to_label, sort_keys=True, separators=(",", ":"))
    inverse_mapping = json.dumps(label_to_model, sort_keys=True, separators=(",", ":"))
    return {
        "slots": slots,
        "counts": counts,
        "model_to_label": model_to_label,
        "label_to_model": label_to_model,
        "plan_sha256": _sha256_bytes(canonical.encode("utf-8")),
        "blind_mapping_sha256": _sha256_bytes(mapping.encode("utf-8")),
        "inverse_blind_mapping_sha256": _sha256_bytes(inverse_mapping.encode("utf-8")),
    }


def _request_control_probe(
    *,
    model_id: str,
    workflow: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    common = config["common_request_controls"]
    base_url = config["provider"]["official_base_url"]
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": "json preflight probe"}],
        "temperature": workflow["production_temperature"],
        "max_tokens": workflow["production_requested_max_tokens"],
    }
    if workflow["json_mode"]:
        payload["response_format"] = {"type": "json_object"}
    thinking = apply_thinking_policy(
        payload,
        base_url=base_url,
        model=model_id,
        configured=common["thinking"]["requested"],
    )
    effort = apply_reasoning_effort_policy(
        payload,
        base_url=base_url,
        model=model_id,
        configured=common["reasoning_effort"]["intended"],
    )
    client = type(
        "PreflightClient",
        (),
        {"max_tokens": int(common["client_configured_max_tokens"])},
    )()
    effective_tokens = _initial_token_budget(
        client,
        model_id,
        int(workflow["production_requested_max_tokens"]),
    )
    if thinking != "enabled" or effort != "high":
        raise ValueError(f"required DeepSeek controls were not emitted for {model_id}")
    return {
        "model_id": model_id,
        "workflow": workflow["id"],
        "thinking": payload["thinking"],
        "reasoning_effort": payload["reasoning_effort"],
        "requested_max_tokens": workflow["production_requested_max_tokens"],
        "effective_initial_max_tokens": effective_tokens,
        "json_mode": "response_format" in payload,
    }


def _human_blockers(manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for paper in manifest["papers"]:
        paper_id = paper["paper_id"]
        eligibility = paper["eligibility"]
        if eligibility.get("team_authorship_conflict") != "pass":
            blockers.append(
                f"{paper_id}: team authorship conflict needs human confirmation"
            )
        if eligibility.get("main_body_readability") != "pass":
            blockers.append(
                f"{paper_id}: two-human parser/excerpt readability audit is pending"
            )
    audit = manifest.get("human_audit", {})
    records = audit.get("corpus_eligibility_records", {})
    expected_papers = {paper["paper_id"] for paper in manifest["papers"]}
    required_checks = {
        "team_authorship_conflict_absent",
        "raw_pdf_opened",
        "parsed_main_body_readable",
        "ledger_extraction_excerpt_readable",
        "ledger_status_excerpt_readable",
        "reviewer_excerpt_readable",
    }
    for annotator in audit.get("required_annotators", []):
        record = records.get(annotator)
        if not isinstance(record, dict) or record.get("status") != "pass":
            blockers.append(
                f"annotator {annotator}: corpus eligibility audit is not locked PASS"
            )
            continue
        path = _development_path(record["path"])
        _verify_file(path, record)
        payload = _load_yaml(path)
        papers = payload.get("papers", [])
        if (
            payload.get("annotator_id") != annotator
            or payload.get("independent_review_complete") is not True
            or payload.get("overall_decision") != "pass"
            or {item.get("paper_id") for item in papers} != expected_papers
            or not payload.get("signed_name_or_initials")
            or not payload.get("signed_on")
        ):
            blockers.append(
                f"annotator {annotator}: locked audit content is incomplete"
            )
            continue
        if any(
            any(item.get(check) is not True for check in required_checks)
            or item.get("material_issues")
            for item in papers
        ):
            blockers.append(
                f"annotator {annotator}: locked audit contains a failed check"
            )
    return blockers


def build_preflight_report(
    *,
    manifest: dict[str, Any] | None = None,
    model_config: dict[str, Any] | None = None,
    runtime_cloud: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = manifest or _load_yaml(MANIFEST_PATH)
    model_config = model_config or _load_yaml(MODEL_SELECTION_PATH)
    runtime_cloud = runtime_cloud or load_runtime_cloud_config()

    verified_files = verify_development_inventory(manifest)
    execution_state = verify_model_execution_state(model_config)
    if model_config.get("development_only") is not True:
        raise ValueError("model-selection config must be development_only")
    if model_config.get("formal_run_authorized") is not False:
        raise ValueError("preflight refuses a formal-run authorization")

    provider = model_config["provider"]
    if (
        provider["name"] != "deepseek"
        or provider["official_base_url"].rstrip("/") != "https://api.deepseek.com/v1"
    ):
        raise ValueError("model screen requires the official DeepSeek endpoint")
    presets = _load_yaml(PROVIDER_PRESETS_PATH)
    preset = presets.get("deepseek", {})
    candidate_ids = [item["model_id"] for item in model_config["candidates"]]
    if not set(candidate_ids).issubset(set(preset.get("models", []))):
        raise ValueError("candidate model is absent from the DeepSeek provider preset")
    if set(candidate_ids) != {"deepseek-v4-pro", "deepseek-v4-flash"}:
        raise ValueError("only the preregistered Pro/Flash candidates are allowed")

    runtime_provider = str(runtime_cloud.get("provider", "")).strip().lower()
    runtime_base = str(runtime_cloud.get("base_url", "")).rstrip("/").lower()
    credential = str(runtime_cloud.get("api_key", "")).strip()
    blockers = _human_blockers(manifest)
    if runtime_provider != "deepseek" or runtime_base != "https://api.deepseek.com/v1":
        blockers.append(
            "local runtime cloud provider must target the official DeepSeek endpoint"
        )
    if not credential:
        blockers.append(
            "DeepSeek credential is absent from local runtime configuration/environment"
        )

    plan = build_run_plan(model_config)
    probes = [
        _request_control_probe(
            model_id=model_id, workflow=workflow, config=model_config
        )
        for workflow in model_config["workflows"]
        for model_id in candidate_ids
    ]
    report = {
        "schema_version": "reviewer-validation-model-selection-preflight/v1",
        "development_only": True,
        "network_calls": 0,
        "verified_file_count": verified_files,
        "execution_code_state": execution_state,
        "credential_present": bool(credential),
        "provider": {
            "name": provider["name"],
            "base_url": provider["official_base_url"],
            "api_format": provider["api_format"],
        },
        "run_plan": {
            "pair_count": len(plan["slots"]) // 2,
            "invocation_count": len(plan["slots"]),
            "counts": plan["counts"],
            "plan_sha256": plan["plan_sha256"],
            "blind_mapping_sha256": plan["blind_mapping_sha256"],
            "inverse_blind_mapping_sha256": plan["inverse_blind_mapping_sha256"],
        },
        "request_control_probes": probes,
        "outbound_http_audit": {
            "supported": True,
            "headers_excluded": True,
            "actual_payload_retry_and_usage_recordable": True,
        },
        "ready_for_paid_execution": not blockers,
        "blockers": blockers,
        "formal_gate_state": copy.deepcopy(model_config["gate_state"]),
    }
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if credential and credential in serialized:
        raise RuntimeError("credential leaked into preflight report")
    return report


def _write_new(path: Path, data: bytes, *, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"artifact path escapes run root: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return {
        "path": resolved.relative_to(resolved_root).as_posix(),
        "sha256": _sha256_bytes(data),
        "byte_length": len(data),
    }


def _write_new_text(path: Path, value: str, *, root: Path) -> dict[str, Any]:
    return _write_new(path, value.encode("utf-8"), root=root)


def _write_new_json(path: Path, value: Any, *, root: Path) -> dict[str, Any]:
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return _write_new_text(path, serialized, root=root)


def _append_jsonl(path: Path, value: Any, *, root: Path) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"append-only path escapes run root: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("git HEAD is not a full commit hash")
    return commit


def _read_artifact(reference: dict[str, Any] | None) -> str:
    if reference is None:
        return ""
    path = _repo_path(reference["path"])
    data = path.read_bytes()
    if _sha256_bytes(data) != reference["sha256"]:
        raise ValueError(f"artifact hash drift after write: {reference['path']}")
    return data.decode("utf-8")


def _identity_patterns(model_config: dict[str, Any]) -> list[re.Pattern[str]]:
    values: set[str] = set()
    for candidate in model_config["candidates"]:
        model_id = str(candidate["model_id"])
        version = str(candidate["documented_provider_version"])
        values.update(
            {
                model_id,
                version,
                model_id.replace("-", " "),
                version.replace("-", " "),
            }
        )
    patterns = [
        re.compile(re.escape(value), re.IGNORECASE)
        for value in sorted(values, key=len, reverse=True)
    ]
    patterns.extend(
        [
            re.compile(
                r"\bdeepseek[\s_-]*v4[\s_-]*(?:pro|flash)(?:[\s_-]*(?:0813|0731))?\b",
                re.IGNORECASE,
            ),
            re.compile(r"\bv4[\s_-]*(?:pro|flash)\b", re.IGNORECASE),
            re.compile(r"\bdeepseek[\s_-]*(?:pro|flash)\b", re.IGNORECASE),
            re.compile(r"\b(?:pro|flash)[\s_-]+model\b", re.IGNORECASE),
        ]
    )
    return patterns


def _blind_response(value: str, patterns: list[re.Pattern[str]]) -> tuple[str, int]:
    total = 0
    result = value
    for pattern in patterns:
        result, count = pattern.subn("[MODEL]", result)
        total += count
    return result, total


def _assert_outbound_controls(
    events: list[dict[str, Any]],
    *,
    model_id: str,
    credential: str,
) -> None:
    requests = [event for event in events if event.get("event") == "request_started"]
    if not requests:
        raise RuntimeError("logical invocation produced no auditable outbound request")
    for event in requests:
        serialized = json.dumps(event, ensure_ascii=False, sort_keys=True)
        if credential and credential in serialized:
            raise RuntimeError("credential leaked into outbound request audit")
        payload = event["payload"]
        if payload.get("model") != model_id:
            raise RuntimeError("outbound model differs from frozen slot")
        if payload.get("thinking") != {"type": "enabled"}:
            raise RuntimeError("outbound request did not enable thinking")
        if payload.get("reasoning_effort") != "high":
            raise RuntimeError("outbound request did not emit reasoning_effort=high")
        if payload.get("max_tokens") not in {16384, 32768}:
            raise RuntimeError(
                "outbound token budget differs from preregistered policy"
            )


def _validate_request_before_send(
    event: dict[str, Any],
    *,
    slot: dict[str, Any],
    workflow: dict[str, Any],
    credential: str,
) -> None:
    """Reject a drifted request inside the audit hook, before ``http.post``."""
    if event.get("event") != "request_started":
        return
    serialized = json.dumps(event, ensure_ascii=False, sort_keys=True)
    if credential and credential in serialized:
        raise RuntimeError("credential leaked into outbound request audit")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError("outbound request payload is missing")
    expected_keys = {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "response_format",
        "thinking",
        "reasoning_effort",
    }
    if set(payload) != expected_keys:
        raise RuntimeError(
            f"outbound request fields drifted: {sorted(set(payload) ^ expected_keys)}"
        )
    if payload["model"] != slot["model_id"]:
        raise RuntimeError("outbound model differs from frozen slot")
    messages = payload["messages"]
    if (
        not isinstance(messages, list)
        or len(messages) != 1
        or messages[0].get("role") != "user"
        or not isinstance(messages[0].get("content"), str)
        or not messages[0]["content"]
    ):
        raise RuntimeError(
            "outbound message envelope differs from the production contract"
        )
    if payload["temperature"] != workflow["production_temperature"]:
        raise RuntimeError(
            "outbound temperature differs from the preregistered workflow"
        )
    if payload["response_format"] != {"type": "json_object"}:
        raise RuntimeError("outbound JSON mode differs from the preregistered workflow")
    if payload["thinking"] != {"type": "enabled"}:
        raise RuntimeError("outbound request did not enable thinking")
    if payload["reasoning_effort"] != "high":
        raise RuntimeError("outbound request did not emit reasoning_effort=high")
    sequence = int(event.get("sequence", 0))
    expected_tokens = 16384 if sequence == 1 else 32768 if sequence == 2 else None
    if payload["max_tokens"] != expected_tokens:
        raise RuntimeError(
            "outbound token budget differs from the preregistered policy"
        )


async def _execute_slot(
    *,
    slot: dict[str, Any],
    run_root: Path,
    ledger_root: Path,
    manifest: dict[str, Any],
    model_config: dict[str, Any],
    runtime_cloud: dict[str, Any],
    paper_by_id: dict[str, dict[str, Any]],
    workflow_by_id: dict[str, dict[str, Any]],
    code_commit: str,
) -> dict[str, Any]:
    paper = paper_by_id[slot["paper_id"]]
    workflow = workflow_by_id[slot["workflow"]]
    paper_text = _development_path(paper["parsed_full_text"]["path"]).read_text(
        encoding="utf-8"
    )
    candidate = next(
        item
        for item in model_config["candidates"]
        if item["model_id"] == slot["model_id"]
    )
    credential = str(runtime_cloud["api_key"]).strip()
    client = CloudClient(
        provider="deepseek",
        base_url=model_config["provider"]["official_base_url"],
        api_key=credential,
        model=slot["model_id"],
        max_tokens=int(
            model_config["common_request_controls"]["client_configured_max_tokens"]
        ),
        timeout=float(model_config["common_request_controls"]["timeout_seconds"]),
        thinking_mode="enabled",
        reasoning_effort="high",
    )
    outbound_events: list[dict[str, Any]] = []
    outbound_path = run_root / "coordinator" / "outbound_http_attempts.jsonl"
    current_http_attempt = 0

    def audit_hook(event: dict[str, Any]) -> None:
        nonlocal current_http_attempt
        if event.get("event") == "request_started":
            _validate_request_before_send(
                event,
                slot=slot,
                workflow=workflow,
                credential=credential,
            )
            current_http_attempt += 1
        envelope = {
            "slot_id": slot["slot_id"],
            "pair_id": slot["pair_id"],
            "workflow": slot["workflow"],
            "paper_id": slot["paper_id"],
            "blind_label": slot["blind_label"],
            "model_id": slot["model_id"],
            "http_attempt_index": current_http_attempt,
            **event,
        }
        serialized = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        if credential in serialized:
            raise RuntimeError("credential leaked into outbound audit event")
        outbound_events.append(copy.deepcopy(envelope))
        _append_jsonl(outbound_path, envelope, root=run_root)

    client.request_audit_hook = audit_hook
    protocol = manifest["protocol"]
    coordinator_record: dict[str, Any]
    raw_response: str
    parsed_output: Any
    excerpt: str
    termination: str
    try:
        if workflow["id"] == "ledger_extraction":
            execution = await execute_ledger_mode(
                mode="extraction",
                text=paper_text,
                cloud_client=client,
            )
            record_path, record = write_execution_record(
                execution,
                output_dir=ledger_root,
                paper_id=paper["paper_id"],
                run_id=slot["slot_id"],
                protocol_version=protocol["version"],
                protocol_sha256=protocol["sha256"],
                provider_name="deepseek",
                model_id=slot["model_id"],
                model_snapshot=None,
                api_format="openai",
                thinking_mode="enabled",
            )
            coordinator_record = {
                "record_path": record_path.relative_to(REPO_ROOT).as_posix(),
                "record": record,
            }
            step = execution.steps[-1]
            raw_response = step.raw_response
            parsed_output = execution.output
            excerpt = step.request.excerpt.text
            termination = execution.termination_status
        elif workflow["id"] == "venue_conditioned_reviewer":
            result = await run_venue_invocation(
                output_root=run_root / "coordinator" / "reviewer",
                pair_id=slot["slot_id"],
                run_id=slot["slot_id"],
                condition="venue_conditioned",
                paper_id=paper["paper_id"],
                paper_text=paper_text,
                venue_label=paper["venue"],
                profile_text=_load_venue_profile(paper["venue"]),
                protocol_version=protocol["version"],
                protocol_sha256=protocol["sha256"],
                code_commit=code_commit,
                cloud_client=client,
            )
            record = result.record
            coordinator_record = {"record": record}
            attempt = record["steps"][0]["attempts"][0]
            raw_response = _read_artifact(attempt["raw_response"])
            parsed_text = _read_artifact(attempt["parsed_output"])
            parsed_output = json.loads(parsed_text) if parsed_text else None
            excerpt = result.excerpt
            termination = record["termination"]["status"]
        else:
            raise ValueError(f"unsupported model-screen workflow: {workflow['id']}")
    finally:
        client.close()

    _assert_outbound_controls(
        outbound_events,
        model_id=slot["model_id"],
        credential=credential,
    )
    request_events = [
        event for event in outbound_events if event.get("event") == "request_started"
    ]
    response_models = [
        str(event.get("response_model") or "").strip()
        for event in outbound_events
        if event.get("event") == "response_received"
    ]
    response_model_ok = (
        bool(response_models)
        and all(response_models)
        and len(set(response_models)) == 1
    )
    valid_for_pair_rating = termination in _VALID_TERMINATIONS and response_model_ok
    slot_record = {
        "schema_version": "reviewer-validation-model-selection-slot/v1",
        "slot": slot,
        "documented_provider_version": candidate["documented_provider_version"],
        "reasoning_effort": "high",
        "thinking_mode": "enabled",
        "termination": termination,
        "provider_reported_models": response_models,
        "provider_reported_model_consistent": response_model_ok,
        "valid_for_pair_rating": valid_for_pair_rating,
        "outbound_http_attempts": sum(
            event.get("event") == "request_started" for event in outbound_events
        ),
        "execution_code_state": model_config["execution_code_state"],
        "production_record": coordinator_record,
    }
    slot_ref = _write_new_json(
        run_root / "coordinator" / "slot_records" / f"{slot['slot_id']}.json",
        slot_record,
        root=run_root,
    )
    event = {
        "event": "logical_slot_completed",
        "slot_id": slot["slot_id"],
        "pair_id": slot["pair_id"],
        "model_id": slot["model_id"],
        "termination": termination,
        "slot_record": slot_ref,
    }
    _append_jsonl(run_root / "events.jsonl", event, root=run_root)
    return {
        "slot": slot,
        "termination": termination,
        "valid": valid_for_pair_rating,
        "excerpt": excerpt,
        "raw_response": raw_response,
        "parsed_output": parsed_output,
        "slot_record": slot_ref,
        "initial_request_payload": copy.deepcopy(request_events[0]["payload"]),
        "provider_reported_models": response_models,
        "outbound_http_attempts": slot_record["outbound_http_attempts"],
    }


def _canonical_pair_payload(payload: dict[str, Any]) -> bytes:
    canonical = copy.deepcopy(payload)
    canonical["model"] = "<MODEL>"
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _audit_pair_request_parity(
    *,
    run_root: Path,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(result["slot"]["pair_id"], []).append(result)
    records: list[dict[str, Any]] = []
    for pair_id in sorted(grouped):
        pair_results = grouped[pair_id]
        if len(pair_results) != 2:
            raise RuntimeError(f"request parity pair is incomplete: {pair_id}")
        canonical_payloads = [
            _canonical_pair_payload(result["initial_request_payload"])
            for result in pair_results
        ]
        passed = canonical_payloads[0] == canonical_payloads[1]
        record = {
            "pair_id": pair_id,
            "allowed_difference": "model",
            "canonical_request_equal": passed,
            "canonical_request_sha256": [
                _sha256_bytes(payload) for payload in canonical_payloads
            ],
            "actual_model": [
                result["initial_request_payload"]["model"] for result in pair_results
            ],
        }
        records.append(record)
        for result in pair_results:
            result["pair_request_parity_pass"] = passed
    audit = {
        "schema_version": "reviewer-validation-model-selection-request-parity/v1",
        "all_pairs_pass": all(record["canonical_request_equal"] for record in records),
        "records": records,
    }
    _write_new_json(
        run_root / "coordinator" / "request_parity.json", audit, root=run_root
    )
    return audit


def _materialize_blind_package(
    *,
    run_root: Path,
    coordinator_root: Path,
    results: list[dict[str, Any]],
    manifest: dict[str, Any],
    model_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    patterns = _identity_patterns(model_config)
    paper_codes = {
        paper["paper_id"]: f"P{index:02d}"
        for index, paper in enumerate(manifest["papers"], start=1)
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(result["slot"]["pair_id"], []).append(result)

    index_records: list[dict[str, Any]] = []
    redaction_records: list[dict[str, Any]] = []
    for pair_id in sorted(grouped):
        pair_results = grouped[pair_id]
        if len(pair_results) != 2:
            raise RuntimeError(f"blind pair does not have two sides: {pair_id}")
        labels = {item["slot"]["blind_label"] for item in pair_results}
        if labels != set(model_config["screen_design"]["blind_model_labels"]):
            raise RuntimeError(f"blind pair labels are incomplete: {pair_id}")
        excerpts = {item["excerpt"] for item in pair_results}
        if len(excerpts) != 1:
            raise RuntimeError(f"paired model-visible excerpts differ: {pair_id}")
        excerpt = next(iter(excerpts))
        for pattern in patterns:
            if pattern.search(excerpt):
                raise RuntimeError(
                    f"model identity appears in source excerpt; cannot blind {pair_id}"
                )

        pair_root = run_root / "blind" / pair_id
        excerpt_ref = _write_new_text(
            pair_root / "source_excerpt.txt", excerpt, root=run_root
        )
        side_records: list[dict[str, Any]] = []
        for result in sorted(
            pair_results, key=lambda item: item["slot"]["blind_label"]
        ):
            label = result["slot"]["blind_label"]
            blinded_raw, raw_redactions = _blind_response(
                result["raw_response"], patterns
            )
            parsed_serialized = json.dumps(
                result["parsed_output"], ensure_ascii=False, indent=2, sort_keys=True
            )
            blinded_parsed, parsed_redactions = _blind_response(
                parsed_serialized, patterns
            )
            raw_ref = _write_new_text(
                pair_root / f"{label}.response.txt", blinded_raw, root=run_root
            )
            parsed_ref = _write_new_text(
                pair_root / f"{label}.parsed.json", blinded_parsed + "\n", root=run_root
            )
            side_records.append(
                {
                    "label": label,
                    "termination": result["termination"],
                    "valid_for_rating": result["valid"],
                    "response": raw_ref,
                    "parsed_output": parsed_ref,
                }
            )
            redaction_records.append(
                {
                    "pair_id": pair_id,
                    "label": label,
                    "raw_identity_redactions": raw_redactions,
                    "parsed_identity_redactions": parsed_redactions,
                }
            )
        slot = pair_results[0]["slot"]
        both_valid = all(item["valid"] for item in pair_results) and all(
            item.get("pair_request_parity_pass") is True for item in pair_results
        )
        rating_refs: dict[str, dict[str, Any]] = {}
        for rater_id in model_config["human_rating"]["raters"]:
            rating_template = {
                "schema_version": "reviewer-validation-model-selection-rating/v1",
                "rater_id": rater_id,
                "pair_id": pair_id,
                "paper_code": paper_codes[slot["paper_id"]],
                "workflow": slot["workflow"],
                "repetition": slot["repetition"],
                "eligible_for_rating": both_valid,
                "dimension_scale": model_config["human_rating"]["dimension_scale"],
                "ratings": {
                    label: dict.fromkeys(model_config["human_rating"]["dimensions"])
                    for label in sorted(labels)
                },
                "pair_preference": None,
                "notes": None,
            }
            rating_refs[rater_id] = _write_new_json(
                run_root / "rating_forms" / rater_id / f"{pair_id}.json",
                rating_template,
                root=run_root,
            )
        index_records.append(
            {
                "pair_id": pair_id,
                "paper_code": paper_codes[slot["paper_id"]],
                "workflow": slot["workflow"],
                "repetition": slot["repetition"],
                "eligible_for_rating": both_valid,
                "source_excerpt": excerpt_ref,
                "sides": side_records,
                "rating_forms": rating_refs,
            }
        )

    blind_index = {
        "schema_version": "reviewer-validation-model-selection-blind-index/v1",
        "model_identity_present": False,
        "pairs": index_records,
    }
    redaction_audit = {
        "schema_version": "reviewer-validation-model-selection-redaction/v1",
        "records": redaction_records,
    }
    _write_new_json(run_root / "blind" / "index.json", blind_index, root=run_root)
    _write_new_json(
        coordinator_root / "redaction_audit.json",
        redaction_audit,
        root=coordinator_root,
    )
    blind_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (run_root / "blind").rglob("*")
        if path.is_file()
    )
    if any(pattern.search(blind_text) for pattern in patterns):
        raise RuntimeError("model identity leaked into blind package")
    blind_records = []
    for path in sorted(
        (path for path in (run_root / "blind").rglob("*") if path.is_file()),
        key=lambda item: item.as_posix(),
    ):
        data = path.read_bytes()
        blind_records.append(
            {
                "path": path.relative_to(run_root).as_posix(),
                "sha256": _sha256_bytes(data),
                "byte_length": len(data),
            }
        )
    canonical_records = json.dumps(blind_records, sort_keys=True, separators=(",", ":"))
    _write_new_json(
        coordinator_root / "blind_package_manifest.json",
        {
            "schema_version": "reviewer-validation-model-selection-blind-manifest/v1",
            "records": blind_records,
            "record_set_sha256": _sha256_bytes(canonical_records.encode("utf-8")),
        },
        root=coordinator_root,
    )
    return blind_index, redaction_audit


async def execute_paid_run(
    *,
    run_id: str,
    preflight: dict[str, Any],
    manifest: dict[str, Any],
    model_config: dict[str, Any],
    runtime_cloud: dict[str, Any],
    slot_executor: Any = None,
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run-id must be a path-safe identifier")
    if not preflight["ready_for_paid_execution"]:
        raise RuntimeError(
            "paid execution blocked: " + "; ".join(preflight["blockers"])
        )
    run_root = (MODEL_OUTPUT_ROOT / run_id).resolve()
    private_root = (MODEL_PRIVATE_ROOT / run_id).resolve()
    ledger_root = (LEDGER_OUTPUT_ROOT / run_id).resolve()
    if run_root.exists() or private_root.exists() or ledger_root.exists():
        raise FileExistsError(
            "refusing to overwrite or resume an existing model-screen run"
        )
    if not run_root.is_relative_to(MODEL_OUTPUT_ROOT.resolve()):
        raise ValueError("run output escapes model-selection root")
    if not ledger_root.is_relative_to(LEDGER_OUTPUT_ROOT.resolve()):
        raise ValueError("ledger output escapes model-selection ledger root")
    if not private_root.is_relative_to(MODEL_PRIVATE_ROOT.resolve()):
        raise ValueError("private output escapes model-selection coordinator root")
    run_root.mkdir(parents=True, exist_ok=False)
    private_root.mkdir(parents=True, exist_ok=False)
    ledger_root.mkdir(parents=True, exist_ok=False)

    plan = build_run_plan(model_config)
    frozen_config_ref = _write_new(
        private_root / "frozen_inputs" / "model_selection.yaml",
        MODEL_SELECTION_PATH.read_bytes(),
        root=private_root,
    )
    frozen_manifest_ref = _write_new(
        private_root / "frozen_inputs" / "development_manifest.yaml",
        MANIFEST_PATH.read_bytes(),
        root=private_root,
    )
    _write_new_json(private_root / "preflight.json", preflight, root=private_root)
    _write_new_json(
        private_root / "run_plan.json",
        {
            **plan,
            "frozen_model_selection": frozen_config_ref,
            "frozen_development_manifest": frozen_manifest_ref,
            "execution_code_state": preflight["execution_code_state"],
        },
        root=private_root,
    )
    _write_new_json(
        private_root / "blind_mapping.json",
        {
            "model_to_label": plan["model_to_label"],
            "model_to_label_sha256": plan["blind_mapping_sha256"],
            "label_to_model": plan["label_to_model"],
            "label_to_model_sha256": plan["inverse_blind_mapping_sha256"],
        },
        root=private_root,
    )

    paper_by_id = {paper["paper_id"]: paper for paper in manifest["papers"]}
    workflow_by_id = {
        workflow["id"]: workflow for workflow in model_config["workflows"]
    }
    code_commit = _git_commit()
    results: list[dict[str, Any]] = []
    effective_slot_executor = slot_executor or _execute_slot
    for slot in plan["slots"]:
        result = await effective_slot_executor(
            slot=slot,
            run_root=private_root,
            ledger_root=ledger_root,
            manifest=manifest,
            model_config=model_config,
            runtime_cloud=runtime_cloud,
            paper_by_id=paper_by_id,
            workflow_by_id=workflow_by_id,
            code_commit=code_commit,
        )
        results.append(result)

    parity_audit = _audit_pair_request_parity(run_root=private_root, results=results)
    blind_index, _ = _materialize_blind_package(
        run_root=run_root,
        coordinator_root=private_root,
        results=results,
        manifest=manifest,
        model_config=model_config,
    )
    valid_counts = {
        model_id: sum(
            result["valid"] and result["slot"]["model_id"] == model_id
            for result in results
        )
        for model_id in plan["counts"]
    }
    common_valid_pairs = sum(
        record["eligible_for_rating"] for record in blind_index["pairs"]
    )
    provider_models_by_candidate = {
        model_id: sorted(
            {
                response_model
                for result in results
                if result["slot"]["model_id"] == model_id
                for response_model in result["provider_reported_models"]
                if response_model
            }
        )
        for model_id in plan["counts"]
    }
    provider_model_consistency = all(
        len(values) == 1 for values in provider_models_by_candidate.values()
    )
    required_cells = {
        (paper_id, workflow["id"])
        for workflow in model_config["workflows"]
        for paper_id in workflow["papers"]
    }
    valid_cells_by_candidate = {
        model_id: sorted(
            {
                (result["slot"]["paper_id"], result["slot"]["workflow"])
                for result in results
                if result["slot"]["model_id"] == model_id and result["valid"]
            }
        )
        for model_id in plan["counts"]
    }
    required_cell_coverage = all(
        set(cells) == required_cells for cells in valid_cells_by_candidate.values()
    )
    minimum_common = int(
        model_config["human_rating"]["paired_validity"]["minimum_common_valid_pairs"]
    )
    minimum_model = int(
        model_config["technical_eligibility"]["minimum_valid_invocations_per_model"]
    )
    technically_eligible = (
        min(valid_counts.values()) >= minimum_model
        and common_valid_pairs >= minimum_common
        and parity_audit["all_pairs_pass"]
        and provider_model_consistency
        and required_cell_coverage
    )
    outbound_path = private_root / "coordinator" / "outbound_http_attempts.jsonl"
    summary = {
        "schema_version": "reviewer-validation-model-selection-summary/v1",
        "run_id": run_id,
        "development_only": True,
        "logical_invocations": len(results),
        "outbound_http_attempts": sum(
            result["outbound_http_attempts"] for result in results
        ),
        "valid_invocations_by_model": valid_counts,
        "common_valid_pairs": common_valid_pairs,
        "request_parity_all_pairs_pass": parity_audit["all_pairs_pass"],
        "provider_reported_models_by_candidate": provider_models_by_candidate,
        "provider_reported_model_consistent": provider_model_consistency,
        "valid_paper_workflow_cells_by_candidate": valid_cells_by_candidate,
        "required_paper_workflow_coverage": required_cell_coverage,
        "technically_eligible_for_blind_rating": technically_eligible,
        "status": (
            "awaiting_locked_A_and_B_ratings"
            if technically_eligible
            else "technical_eligibility_failed"
        ),
        "selected_model": None,
        "outbound_audit": {
            "path": outbound_path.relative_to(private_root).as_posix(),
            "sha256": _sha256_file(outbound_path),
            "byte_length": outbound_path.stat().st_size,
        },
    }
    _write_new_json(private_root / "final_summary.json", summary, root=private_root)
    public_status = {
        "schema_version": "reviewer-validation-model-selection-public-status/v1",
        "run_id": run_id,
        "development_only": True,
        "common_valid_pairs": common_valid_pairs,
        "technically_eligible_for_blind_rating": technically_eligible,
        "status": summary["status"],
        "model_identity_present": False,
    }
    _write_new_json(run_root / "run_status.json", public_status, root=run_root)
    return summary


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _rating_context(run_id: str) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run-id must be a path-safe identifier")
    public_root = (MODEL_OUTPUT_ROOT / run_id).resolve()
    private_root = (MODEL_PRIVATE_ROOT / run_id).resolve()
    if not public_root.is_dir() or not private_root.is_dir():
        raise FileNotFoundError("model-screen public/private run roots are incomplete")
    frozen_config_path = private_root / "frozen_inputs" / "model_selection.yaml"
    frozen_manifest = _load_yaml(
        private_root / "frozen_inputs" / "development_manifest.yaml"
    )
    config_record = frozen_manifest["model_selection"]
    if _sha256_file(frozen_config_path) != config_record["sha256"]:
        raise ValueError("frozen model-selection config drifted")
    model_config = _load_yaml(frozen_config_path)
    blind_manifest = _load_json(private_root / "blind_package_manifest.json")
    for record in blind_manifest["records"]:
        path = (public_root / record["path"]).resolve()
        if not path.is_relative_to(public_root):
            raise ValueError("blind manifest path escapes public run root")
        data = path.read_bytes()
        if (
            len(data) != record["byte_length"]
            or _sha256_bytes(data) != record["sha256"]
        ):
            raise ValueError(f"blind package drifted: {record['path']}")
    canonical_records = json.dumps(
        blind_manifest["records"], sort_keys=True, separators=(",", ":")
    )
    if (
        _sha256_bytes(canonical_records.encode("utf-8"))
        != blind_manifest["record_set_sha256"]
    ):
        raise ValueError("blind package manifest drifted")
    blind_index = _load_json(public_root / "blind" / "index.json")
    return public_root, private_root, model_config, blind_index


def _validate_rating_form(
    form: dict[str, Any],
    *,
    rater_id: str,
    pair_record: dict[str, Any],
    model_config: dict[str, Any],
) -> None:
    if (
        form.get("rater_id") != rater_id
        or form.get("pair_id") != pair_record["pair_id"]
    ):
        raise ValueError("rating form identity fields drifted")
    if form.get("eligible_for_rating") is not pair_record["eligible_for_rating"]:
        raise ValueError("rating form eligibility differs from blind index")
    if not pair_record["eligible_for_rating"]:
        return
    labels = set(model_config["screen_design"]["blind_model_labels"])
    dimensions = set(model_config["human_rating"]["dimensions"])
    ratings = form.get("ratings")
    if not isinstance(ratings, dict) or set(ratings) != labels:
        raise ValueError("rating form labels are incomplete")
    allowed_scores = set(model_config["human_rating"]["dimension_scale"])
    for label, values in ratings.items():
        if not isinstance(values, dict) or set(values) != dimensions:
            raise ValueError(f"rating dimensions are incomplete for {label}")
        if any(
            isinstance(score, bool) or score not in allowed_scores
            for score in values.values()
        ):
            raise ValueError(f"rating scores are incomplete or invalid for {label}")
    if (
        form.get("pair_preference")
        not in model_config["human_rating"]["pair_preference"]
    ):
        raise ValueError("pair preference is incomplete or invalid")


def lock_ratings(*, run_id: str, rater_id: str) -> dict[str, Any]:
    public_root, private_root, model_config, blind_index = _rating_context(run_id)
    if rater_id not in model_config["human_rating"]["raters"]:
        raise ValueError("unknown rater id")
    lock_path = private_root / "rating_locks" / f"{rater_id}.json"
    if lock_path.exists():
        raise FileExistsError(f"rating set is already locked for {rater_id}")
    records: list[dict[str, Any]] = []
    for pair in blind_index["pairs"]:
        form_path = public_root / "rating_forms" / rater_id / f"{pair['pair_id']}.json"
        form = _load_json(form_path)
        _validate_rating_form(
            form,
            rater_id=rater_id,
            pair_record=pair,
            model_config=model_config,
        )
        data = form_path.read_bytes()
        records.append(
            {
                "pair_id": pair["pair_id"],
                "eligible_for_rating": pair["eligible_for_rating"],
                "path": form_path.relative_to(public_root).as_posix(),
                "sha256": _sha256_bytes(data),
                "byte_length": len(data),
            }
        )
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    lock = {
        "schema_version": "reviewer-validation-model-selection-rating-lock/v1",
        "run_id": run_id,
        "rater_id": rater_id,
        "records": records,
        "record_set_sha256": _sha256_bytes(canonical.encode("utf-8")),
    }
    _write_new_json(lock_path, lock, root=private_root)
    for record in records:
        (public_root / record["path"]).chmod(stat.S_IREAD)
    return lock


def _load_and_verify_rating_lock(
    *,
    public_root: Path,
    private_root: Path,
    rater_id: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    lock = _load_json(private_root / "rating_locks" / f"{rater_id}.json")
    forms: dict[str, dict[str, Any]] = {}
    for record in lock["records"]:
        path = (public_root / record["path"]).resolve()
        if not path.is_relative_to(public_root.resolve()):
            raise ValueError("rating lock path escapes public run root")
        data = path.read_bytes()
        if (
            len(data) != record["byte_length"]
            or _sha256_bytes(data) != record["sha256"]
        ):
            raise ValueError(f"locked rating file drifted: {record['path']}")
        forms[record["pair_id"]] = json.loads(data.decode("utf-8"))
    canonical_records = json.dumps(
        lock["records"], sort_keys=True, separators=(",", ":")
    )
    if _sha256_bytes(canonical_records.encode("utf-8")) != lock["record_set_sha256"]:
        raise ValueError("rating lock record set drifted")
    return lock, forms


def _aggregate_preference(left: str, right: str) -> str:
    if left == right:
        return left
    if left == "tie":
        return right
    if right == "tie":
        return left
    return "tie"


def select_model_from_locked_ratings(*, run_id: str) -> dict[str, Any]:
    public_root, private_root, model_config, blind_index = _rating_context(run_id)
    output_path = private_root / "selection_result.json"
    if output_path.exists():
        raise FileExistsError("selection result already exists")
    forms_by_rater: dict[str, dict[str, dict[str, Any]]] = {}
    lock_hashes: dict[str, str] = {}
    for rater_id in model_config["human_rating"]["raters"]:
        lock, forms = _load_and_verify_rating_lock(
            public_root=public_root,
            private_root=private_root,
            rater_id=rater_id,
        )
        forms_by_rater[rater_id] = forms
        lock_hashes[rater_id] = lock["record_set_sha256"]

    labels = list(model_config["screen_design"]["blind_model_labels"])
    wins = dict.fromkeys(labels, 0)
    unsupported = dict.fromkeys(labels, 0)
    aggregate_pairs: list[dict[str, Any]] = []
    eligible_pairs = [
        pair for pair in blind_index["pairs"] if pair["eligible_for_rating"]
    ]
    minimum_pairs = int(
        model_config["human_rating"]["paired_validity"]["minimum_common_valid_pairs"]
    )
    if len(eligible_pairs) < minimum_pairs:
        raise ValueError("insufficient common valid pairs for selection")
    raters = list(model_config["human_rating"]["raters"])
    for pair in eligible_pairs:
        pair_id = pair["pair_id"]
        left_form = forms_by_rater[raters[0]][pair_id]
        right_form = forms_by_rater[raters[1]][pair_id]
        aggregate = _aggregate_preference(
            left_form["pair_preference"], right_form["pair_preference"]
        )
        if aggregate in wins:
            wins[aggregate] += 1
        for label in labels:
            unsupported[label] += int(
                left_form["ratings"][label]["unsupported_or_invented_content"]
            ) + int(right_form["ratings"][label]["unsupported_or_invented_content"])
        aggregate_pairs.append(
            {
                "pair_id": pair_id,
                "rater_preferences": {
                    raters[0]: left_form["pair_preference"],
                    raters[1]: right_form["pair_preference"],
                },
                "aggregate_preference": aggregate,
            }
        )

    mapping = _load_json(private_root / "blind_mapping.json")
    label_to_model = mapping["label_to_model"]
    model_to_label_bytes = json.dumps(
        mapping["model_to_label"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    label_to_model_bytes = json.dumps(
        label_to_model, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if _sha256_bytes(model_to_label_bytes) != mapping["model_to_label_sha256"]:
        raise ValueError("model-to-label mapping hash drifted")
    if _sha256_bytes(label_to_model_bytes) != mapping["label_to_model_sha256"]:
        raise ValueError("label-to-model mapping hash drifted")
    if wins[labels[0]] > wins[labels[1]]:
        preferred_label = labels[0]
    elif wins[labels[1]] > wins[labels[0]]:
        preferred_label = labels[1]
    elif unsupported[labels[0]] < unsupported[labels[1]]:
        preferred_label = labels[0]
    elif unsupported[labels[1]] < unsupported[labels[0]]:
        preferred_label = labels[1]
    else:
        preferred_label = next(
            label
            for label, model_id in label_to_model.items()
            if model_id == model_config["decision_state"]["user_preference_prior"]
        )

    other_label = next(label for label in labels if label != preferred_label)
    more_wins = wins[preferred_label] > wins[other_label]
    safety_conflict = (
        more_wins and unsupported[preferred_label] > unsupported[other_label]
    )
    selected_model = None if safety_conflict else label_to_model[preferred_label]
    result = {
        "schema_version": "reviewer-validation-model-selection-result/v1",
        "run_id": run_id,
        "rating_lock_hashes": lock_hashes,
        "eligible_pairs": len(eligible_pairs),
        "aggregate_pairs": aggregate_pairs,
        "pairwise_wins": wins,
        "unsupported_content_totals": unsupported,
        "status": "blocked_safety_conflict" if safety_conflict else "selected",
        "selected_blind_label": None if safety_conflict else preferred_label,
        "selected_model": selected_model,
    }
    _write_new_json(output_path, result, root=private_root)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("preflight", "run", "lock-ratings", "select-model"),
        default="preflight",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--rater", choices=("A", "B"))
    parser.add_argument("--ack-development-only", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command in {"lock-ratings", "select-model"}:
        if not args.run_id:
            raise SystemExit(f"{args.command} requires --run-id")
        if args.command == "lock-ratings":
            if not args.rater:
                raise SystemExit("lock-ratings requires --rater A or B")
            result = lock_ratings(run_id=args.run_id, rater_id=args.rater)
        else:
            result = select_model_from_locked_ratings(run_id=args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    manifest = _load_yaml(MANIFEST_PATH)
    model_config = _load_yaml(MODEL_SELECTION_PATH)
    runtime_cloud = load_runtime_cloud_config()
    report = build_preflight_report(
        manifest=manifest,
        model_config=model_config,
        runtime_cloud=runtime_cloud,
    )
    if args.command == "preflight":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ready_for_paid_execution"] else 2
    if not args.ack_development_only:
        raise SystemExit("run requires --ack-development-only")
    if not args.run_id:
        raise SystemExit("run requires --run-id")
    summary = asyncio.run(
        execute_paid_run(
            run_id=args.run_id,
            preflight=report,
            manifest=manifest,
            model_config=model_config,
            runtime_cloud=runtime_cloud,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
