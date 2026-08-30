"""Fail-closed RQ3 venue-profile A/B runner.

The runner calls the serial production ``run_review(..., checks=["llm"])`` path.
It keeps the venue label and every non-profile request field constant, accepts
exactly one logical provider client, and writes append-only audit records.  The
CLI intentionally exposes only a synthetic offline pilot; formal provider
construction belongs to the frozen experiment orchestration.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
VALIDATION_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = VALIDATION_ROOT / "schemas"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from src.argument.companion_models import ReviewSession  # noqa: E402
from src.argument.reviewer import run_review  # noqa: E402
from src.argument.section_utils import build_section_excerpt_envelope  # noqa: E402
from src.utils.json_extract import extract_json_array  # noqa: E402
from verify_freeze import validate_instance  # noqa: E402

LLMCall = Callable[..., Awaitable[str]]
RUN_RECORD_SCHEMA_VERSION = "reviewer-validation-run-record/v1"
MAX_TOKENS = 2048
TEMPERATURE = 0.5
JSON_MODE = True
_CONDITIONS = {"generic", "venue_conditioned"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_PATH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\b(?:api[_-]?key|authorization)\s*[:=]\s*\S+", re.IGNORECASE),
)


class SecretMaterialError(ValueError):
    """Raised before an artifact containing likely credentials is persisted."""


@dataclass(frozen=True)
class ClientSelection:
    kind: str
    client: Any
    provider_name: str
    api_format: str
    model_id: str
    model_snapshot: str | None
    thinking_mode: str


@dataclass(frozen=True)
class InvocationResult:
    record: dict[str, Any]
    prompt: str
    profile: str
    excerpt: str


class _MemoryStore:
    """Minimal ReviewSession store used without changing the production path."""

    def __init__(self) -> None:
        self.sessions: dict[str, ReviewSession] = {}

    def get_review(self, session_id: str) -> ReviewSession | None:
        return self.sessions.get(session_id)

    def save_review(self, session: ReviewSession) -> None:
        self.sessions[session.id] = session


class _OllamaFailureProbe:
    """Expose Ollama errors that the shared helper otherwise converts to ``""``."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.failure: Exception | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def translate(self, prompt: str) -> Any:
        try:
            return self._client.translate(prompt)
        except Exception as exc:
            self.failure = exc
            raise


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_no_secret_material(label: str, value: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise SecretMaterialError(f"secret-like material detected in {label}")


def _safe_error(exc: BaseException) -> dict[str, str]:
    message = str(exc)
    if any(pattern.search(message) for pattern in _SECRET_PATTERNS):
        message = "error message redacted because it contained secret-like material"
    return {"type": type(exc).__name__, "message_redacted": message[:1000]}


def _select_single_client(
    cloud_client: Any = None, ollama_client: Any = None
) -> ClientSelection:
    clients = [("cloud", cloud_client), ("ollama", ollama_client)]
    selected = [(kind, client) for kind, client in clients if client is not None]
    if len(selected) != 1:
        raise ValueError(
            "venue experiment requires exactly one non-null logical client"
        )

    kind, client = selected[0]
    provider_name = str(getattr(client, "provider", kind)).strip()
    configured_api_format = getattr(client, "api_format", None)
    api_format = (
        str(configured_api_format).strip()
        if configured_api_format is not None
        else ("openai" if kind == "cloud" else "ollama-translate")
    )
    model_id = str(getattr(client, "model", "")).strip()
    if not provider_name or not api_format or not model_id:
        raise ValueError(
            "selected client must resolve non-empty provider, API format, and model metadata"
        )
    _assert_no_secret_material("provider name", provider_name)
    _assert_no_secret_material("API format", api_format)
    _assert_no_secret_material("model id", model_id)
    snapshot_value = getattr(client, "model_snapshot", None)
    model_snapshot = str(snapshot_value).strip() if snapshot_value else None
    thinking_mode = str(getattr(client, "thinking_mode", "auto")).strip() or "auto"
    return ClientSelection(
        kind=kind,
        client=client,
        provider_name=provider_name,
        api_format=api_format,
        model_id=model_id,
        model_snapshot=model_snapshot,
        thinking_mode=thinking_mode,
    )


def _validate_frozen_metadata(
    *,
    protocol_sha256: str,
    code_commit: str,
    venue_label: str,
    profile_text: str,
    paper_text: str,
) -> None:
    if not _SHA256_RE.fullmatch(protocol_sha256):
        raise ValueError("protocol_sha256 must be a lowercase SHA-256 digest")
    if not _COMMIT_RE.fullmatch(code_commit):
        raise ValueError("code_commit must be a lowercase 40-character git commit")
    if not venue_label.strip():
        raise ValueError("venue_label must be non-empty in both conditions")
    if not profile_text.strip():
        raise ValueError("profile_text must be non-empty")
    _assert_no_secret_material("venue label", venue_label)
    _assert_no_secret_material("profile", profile_text)
    _assert_no_secret_material("paper text", paper_text)


def _artifact_ref(path: Path, *, output_root: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_relative_to(VALIDATION_ROOT):
        raise ValueError("artifact path must remain under methods/reviewer_validation")
    if not output_root.resolve().is_relative_to(VALIDATION_ROOT):
        raise ValueError("output_root must remain under methods/reviewer_validation")
    data = path.read_bytes()
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_bytes(data),
        "byte_length": len(data),
    }


def _write_artifact(
    path: Path, value: str | bytes, *, output_root: Path
) -> dict[str, Any]:
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return _artifact_ref(path, output_root=output_root)


def _append_manifest(output_root: Path, record: dict[str, Any]) -> None:
    manifest_path = output_root / "run_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _validate_run_record(record: dict[str, Any]) -> None:
    errors = validate_instance(record, RUN_RECORD_SCHEMA_VERSION, SCHEMA_DIR)
    if errors:
        raise ValueError(
            "run record failed final schema/verifier: " + "; ".join(errors)
        )


def _termination_status(raw: str | None, error: BaseException | None) -> str:
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return "timeout"
    if error is not None:
        return "provider_error"
    if raw is None or not raw.strip():
        return "empty_response"
    parsed = extract_json_array(raw)
    if parsed is None:
        return "invalid_json"
    if not parsed:
        return "legal_empty"
    return "success"


def _failure_detail(status: str, error: BaseException | None) -> dict[str, str] | None:
    if status in {"success", "legal_empty"}:
        return None
    if error is not None:
        return _safe_error(error)
    messages = {
        "empty_response": "provider returned an empty response",
        "invalid_json": "provider response did not contain a JSON array",
    }
    return {
        "type": status,
        "message_redacted": messages.get(
            status, "invocation failed without an exception"
        ),
    }


def _prompt_profile_span(prompt: str) -> tuple[int, int]:
    prefix = "投稿要求参考："
    suffix = "\n来源覆盖元数据："
    start = prompt.find(prefix)
    if start < 0:
        raise RuntimeError("production profile prefix is absent from the model prompt")
    value_start = start + len(prefix)
    end = prompt.find(suffix, value_start)
    if end < 0:
        raise RuntimeError("production profile suffix is absent from the model prompt")
    return value_start, end


async def run_venue_invocation(
    *,
    output_root: Path,
    pair_id: str,
    run_id: str,
    condition: str,
    paper_id: str,
    paper_text: str,
    venue_label: str,
    profile_text: str,
    protocol_version: str,
    protocol_sha256: str,
    code_commit: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    llm_call: LLMCall | None = None,
    seed: int | None = None,
) -> InvocationResult:
    """Run one isolated G or V invocation and append one immutable record."""
    if condition not in _CONDITIONS:
        raise ValueError(f"condition must be one of {sorted(_CONDITIONS)}")
    selection = _select_single_client(cloud_client, ollama_client)
    _validate_frozen_metadata(
        protocol_sha256=protocol_sha256,
        code_commit=code_commit,
        venue_label=venue_label,
        profile_text=profile_text,
        paper_text=paper_text,
    )
    if (
        not pair_id.strip()
        or not run_id.strip()
        or not paper_id.strip()
        or not protocol_version
    ):
        raise ValueError(
            "pair_id, run_id, paper_id, and protocol_version must be non-empty"
        )
    if not _PATH_ID_RE.fullmatch(pair_id):
        raise ValueError("pair_id must be a path-safe identifier")
    if seed is not None and seed < 0:
        raise ValueError("seed must be non-negative when provided")

    output_root = output_root.resolve()
    if not output_root.is_relative_to(VALIDATION_ROOT):
        raise ValueError("output_root must remain under methods/reviewer_validation")
    condition_dir = (output_root / pair_id / condition).resolve()
    if not condition_dir.is_relative_to(output_root):
        raise ValueError("condition artifact path escapes output_root")
    condition_dir.mkdir(parents=True, exist_ok=False)
    excerpt = build_section_excerpt_envelope(paper_text, max_chars=24000)
    effective_profile = profile_text
    prompt: str | None = None
    raw: str | None = None
    events: list[dict[str, Any]] = []
    error: BaseException | None = None
    call_count = 0
    attempt_started: str | None = None
    attempt_ended: str | None = None
    actual_generation: dict[str, Any] | None = None
    delegate = llm_call
    ollama_probe = (
        _OllamaFailureProbe(selection.client) if selection.kind == "ollama" else None
    )
    provider_client = ollama_probe or selection.client

    async def audited_call(
        actual_prompt: str,
        actual_cloud_client: Any = None,
        actual_ollama_client: Any = None,
        **kwargs: Any,
    ) -> str:
        nonlocal \
            prompt, \
            raw, \
            call_count, \
            attempt_started, \
            attempt_ended, \
            actual_generation
        call_count += 1
        if call_count != 1:
            raise RuntimeError("venue invocation attempted more than one LLM call")
        if selection.kind == "cloud":
            if (
                actual_cloud_client is not provider_client
                or actual_ollama_client is not None
            ):
                raise RuntimeError(
                    "cloud invocation violated the exactly-one-client contract"
                )
        elif (
            actual_ollama_client is not provider_client
            or actual_cloud_client is not None
        ):
            raise RuntimeError(
                "Ollama invocation violated the exactly-one-client contract"
            )
        prompt = actual_prompt
        if excerpt.text not in actual_prompt:
            raise RuntimeError(
                "production excerpt bytes are absent from the model prompt"
            )
        profile_start, profile_end = _prompt_profile_span(actual_prompt)
        if actual_prompt[profile_start:profile_end] != effective_profile:
            raise RuntimeError(
                "effective profile bytes differ from the production prompt segment"
            )
        actual_generation = {
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
            "thinking_mode": selection.thinking_mode,
            "seed": seed,
            "json_mode": kwargs.get("json_mode", False),
        }
        attempt_started = _utc_now()
        try:
            if delegate is None:
                from src.argument.llm_client import call_llm_chat

                candidate = await call_llm_chat(
                    actual_prompt,
                    actual_cloud_client,
                    actual_ollama_client,
                    **kwargs,
                )
            else:
                candidate = await delegate(
                    actual_prompt,
                    actual_cloud_client,
                    actual_ollama_client,
                    **kwargs,
                )
            if ollama_probe is not None and ollama_probe.failure is not None:
                raise ollama_probe.failure
            _assert_no_secret_material("raw response", candidate)
            raw = candidate
            return raw
        finally:
            attempt_ended = _utc_now()

    started_at = _utc_now()
    try:
        kwargs = {
            "doc_id": paper_id,
            "doc_title": paper_id,
            "text": paper_text,
            "venue": venue_label,
            "persona": "reviewer2",
            "ledger": None,
            "store": _MemoryStore(),
            "checks": ["llm"],
            "cloud_client": provider_client if selection.kind == "cloud" else None,
            "ollama_client": provider_client if selection.kind == "ollama" else None,
            "venue_profile_override": profile_text,
            "llm_call": audited_call,
            "raise_llm_errors": True,
        }
        async for event in run_review(**kwargs):
            events.append(event)
    except Exception as exc:  # preserve invocation failures in the manifest
        error = exc
    ended_at = _utc_now()

    if (
        call_count != 1
        or prompt is None
        or attempt_started is None
        or attempt_ended is None
    ):
        raise RuntimeError(
            "serial llm-only path did not make exactly one auditable LLM call"
        )

    prompt_ref = _write_artifact(
        condition_dir / "prompt.txt", prompt, output_root=output_root
    )
    excerpt_ref = _write_artifact(
        condition_dir / "excerpt.txt", excerpt.text, output_root=output_root
    )
    profile_ref = _write_artifact(
        condition_dir / "profile.txt", effective_profile, output_root=output_root
    )
    request_payload = {
        "provider": selection.provider_name,
        "model": selection.model_id,
        "api_format": selection.api_format,
        "messages": [{"role": "user", "content": prompt}],
        "generation": actual_generation,
    }
    _assert_no_secret_material(
        "request envelope",
        json.dumps(request_payload, ensure_ascii=False, sort_keys=True),
    )
    request_ref = _write_artifact(
        condition_dir / "request.json",
        json.dumps(request_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        output_root=output_root,
    )

    raw_ref: dict[str, Any] | None = None
    parsed_ref: dict[str, Any] | None = None
    parsed_array = extract_json_array(raw) if raw and raw.strip() else None
    if raw is not None:
        raw_ref = _write_artifact(
            condition_dir / "raw_response.txt", raw, output_root=output_root
        )
    if parsed_array is not None:
        review_points = [
            json.loads(event["data"])
            for event in events
            if event.get("event") == "review_point"
        ]
        parsed_payload = {
            "model_array": parsed_array,
            "production_review_points": review_points,
        }
        parsed_ref = _write_artifact(
            condition_dir / "parsed_output.json",
            json.dumps(parsed_payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            output_root=output_root,
        )

    status = _termination_status(raw, error)
    attempt_error = _failure_detail(status, error)
    termination = {
        "status": status,
        "attempt_count": 1,
        "error": attempt_error,
    }
    attempt = {
        "attempt_number": 1,
        "started_at": attempt_started,
        "ended_at": attempt_ended,
        "status": status,
        "prompt": prompt_ref,
        "request": request_ref,
        "raw_response": raw_ref,
        "parsed_output": parsed_ref,
        "error": attempt_error,
    }
    step = {
        "step_id": f"{run_id}-{condition}-venue-review",
        "phase": "venue_review",
        "inputs": {
            "excerpt": excerpt_ref,
            "excerpt_coverage": {
                "source_characters": excerpt.original_chars,
                "visible_characters": excerpt.excerpt_chars,
                "truncated": excerpt.truncated,
            },
            "prompt": prompt_ref,
            "profile": profile_ref,
            "gold_promises": None,
        },
        "attempts": [attempt],
        "termination": termination,
    }
    record = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "record_id": f"{run_id}-{condition}",
        "run_id": run_id,
        "experiment": "rq3_venue",
        "stage": "venue_llm",
        "condition": condition,
        "paper_id": paper_id,
        "pair_id": pair_id,
        "venue_label": venue_label,
        "checks": ["llm"],
        "protocol_version": protocol_version,
        "protocol_sha256": protocol_sha256,
        "code_commit": code_commit,
        "started_at": started_at,
        "ended_at": ended_at,
        "provider": {
            "name": selection.provider_name,
            "api_format": selection.api_format,
            "client_count": 1,
            "fallback_call_count": 0,
        },
        "model": {"id": selection.model_id, "snapshot": selection.model_snapshot},
        "generation": actual_generation
        or {
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "thinking_mode": selection.thinking_mode,
            "seed": seed,
            "json_mode": JSON_MODE,
        },
        "steps": [step],
        "output": parsed_ref,
        "termination": termination,
        "denominators": {
            "planned_invocations": 1,
            "primary_unit": "paper",
            "gold_occurrences": None,
            "prediction_occurrences": None,
            "applicable_criteria": None,
            "critique_units": None,
        },
    }
    _validate_run_record(record)
    _append_manifest(output_root, record)
    return InvocationResult(
        record=record,
        prompt=prompt,
        profile=effective_profile,
        excerpt=excerpt.text,
    )


def _canonicalize_prompt(prompt: str, profile: str) -> str:
    start, end = _prompt_profile_span(prompt)
    if prompt[start:end] != profile:
        raise RuntimeError("profile bytes differ from the canonical request segment")
    return prompt[:start] + "<PROFILE>" + prompt[end:]


def _utf8_sha256(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


async def run_venue_pair(
    *,
    output_root: Path,
    pair_id: str,
    run_id: str,
    paper_id: str,
    paper_text: str,
    venue_label: str,
    generic_profile: str,
    venue_profile: str,
    protocol_version: str,
    protocol_sha256: str,
    code_commit: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    llm_call: LLMCall | None = None,
    seed: int | None = None,
    condition_order: Sequence[str] = ("generic", "venue_conditioned"),
) -> dict[str, Any]:
    """Run a paired G/V comparison and emit a canonical request-diff artifact."""
    if tuple(sorted(condition_order)) != ("generic", "venue_conditioned"):
        raise ValueError(
            "condition_order must contain generic and venue_conditioned exactly once"
        )
    if generic_profile == venue_profile:
        raise ValueError("G and V effective profile text must differ")
    _select_single_client(cloud_client, ollama_client)

    profiles = {"generic": generic_profile, "venue_conditioned": venue_profile}
    results: dict[str, InvocationResult] = {}
    for condition in condition_order:
        results[condition] = await run_venue_invocation(
            output_root=output_root,
            pair_id=pair_id,
            run_id=run_id,
            condition=condition,
            paper_id=paper_id,
            paper_text=paper_text,
            venue_label=venue_label,
            profile_text=profiles[condition],
            protocol_version=protocol_version,
            protocol_sha256=protocol_sha256,
            code_commit=code_commit,
            cloud_client=cloud_client,
            ollama_client=ollama_client,
            llm_call=llm_call,
            seed=seed,
        )

    generic = results["generic"]
    conditioned = results["venue_conditioned"]
    generic_canonical = _canonicalize_prompt(generic.prompt, generic.profile)
    conditioned_canonical = _canonicalize_prompt(
        conditioned.prompt, conditioned.profile
    )
    generic_base_request = {
        "provider": generic.record["provider"],
        "model": generic.record["model"],
        "generation": generic.record["generation"],
        "messages": [{"role": "user", "content": generic_canonical}],
    }
    conditioned_base_request = {
        "provider": conditioned.record["provider"],
        "model": conditioned.record["model"],
        "generation": conditioned.record["generation"],
        "messages": [{"role": "user", "content": conditioned_canonical}],
    }
    generic_base_request_bytes = json.dumps(
        generic_base_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    conditioned_base_request_bytes = json.dumps(
        conditioned_base_request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    generic_venue_offsets = [
        match.start()
        for match in re.finditer(re.escape(venue_label), generic_canonical)
    ]
    conditioned_venue_offsets = [
        match.start()
        for match in re.finditer(re.escape(venue_label), conditioned_canonical)
    ]
    invariant_checks = {
        "canonical_prompt_equal": generic_canonical == conditioned_canonical,
        "base_model_request_equal": generic_base_request_bytes
        == conditioned_base_request_bytes,
        "venue_label_equal": bool(generic_venue_offsets)
        and generic_venue_offsets == conditioned_venue_offsets,
        "excerpt_equal": generic.excerpt == conditioned.excerpt,
        "provider_equal": generic.record["provider"] == conditioned.record["provider"],
        "model_equal": generic.record["model"] == conditioned.record["model"],
        "generation_equal": generic.record["generation"]
        == conditioned.record["generation"],
        "checks_llm_only": generic.record["checks"]
        == conditioned.record["checks"]
        == ["llm"],
    }
    unexpected = [name for name, passed in invariant_checks.items() if not passed]
    diff_payload = {
        "pair_id": pair_id,
        "run_id": run_id,
        "allowed_model_request_differences": [
            "messages[0].content.profile_span",
            "profile.sha256",
        ],
        "invariant_checks": invariant_checks,
        "unexpected_differences": unexpected,
        "profile_sha256": {
            "generic": _utf8_sha256(generic.profile),
            "venue_conditioned": _utf8_sha256(conditioned.profile),
        },
        "base_prompt_sha256": {
            "generic": _utf8_sha256(generic_canonical),
            "venue_conditioned": _utf8_sha256(conditioned_canonical),
        },
        "base_model_request_sha256": {
            "generic": _sha256_bytes(generic_base_request_bytes),
            "venue_conditioned": _sha256_bytes(conditioned_base_request_bytes),
        },
        "venue_label": {
            "utf8_sha256": _utf8_sha256(venue_label),
            "generic_base_prompt_offsets": generic_venue_offsets,
            "venue_conditioned_base_prompt_offsets": conditioned_venue_offsets,
        },
        "excerpt_sha256": {
            "generic": _utf8_sha256(generic.excerpt),
            "venue_conditioned": _utf8_sha256(conditioned.excerpt),
        },
        "condition_order": list(condition_order),
    }
    diff_path = output_root.resolve() / pair_id / "canonical_request_diff.json"
    diff_ref = _write_artifact(
        diff_path,
        json.dumps(diff_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        output_root=output_root.resolve(),
    )
    if unexpected:
        raise RuntimeError(f"single-factor isolation failed: {', '.join(unexpected)}")
    return {
        "records": {condition: result.record for condition, result in results.items()},
        "request_diff": {**diff_payload, "artifact": diff_ref},
    }


@dataclass(frozen=True)
class SyntheticPilotFixture:
    """Single immutable source for the offline Venue pilot inputs."""

    paper_id: str
    paper_text: str
    venue_label: str
    generic_profile: str
    venue_profile: str
    failure_profile: str
    success_pair_id: str
    success_run_id: str
    failure_pair_id: str
    failure_run_id: str
    provider_name: str
    api_format: str
    model_id: str
    model_snapshot: str
    thinking_mode: str
    success_response_json: str


SYNTHETIC_PILOT_FIXTURE = SyntheticPilotFixture(
    paper_id="development-synthetic-paper",
    paper_text=(
        "# Abstract\n\n"
        "A deterministic synthetic paper for request-isolation testing.\n\n"
        "# Method\n\n"
        "The method has one stated limitation.\n"
    ),
    venue_label="NeurIPS",
    generic_profile="GENERIC_SYNTHETIC_PROFILE",
    venue_profile="VENUE_SYNTHETIC_PROFILE",
    failure_profile="INJECT_PROVIDER_FAILURE",
    success_pair_id="synthetic-success-pair",
    success_run_id="synthetic-success-run",
    failure_pair_id="synthetic-provider-failure",
    failure_run_id="synthetic-provider-failure-run",
    provider_name="synthetic",
    api_format="controlled-fixture",
    model_id="fixture-reviewer-v1",
    model_snapshot="offline",
    thinking_mode="disabled",
    success_response_json=json.dumps(
        [
            {
                "category": "methodology",
                "severity": "minor",
                "title": "Synthetic audit point",
                "detail": "The fixture exposes one stated limitation.",
            }
        ]
    ),
)


class _SyntheticClient:
    def __init__(self, fixture: SyntheticPilotFixture) -> None:
        self.provider = fixture.provider_name
        self.api_format = fixture.api_format
        self.model = fixture.model_id
        self.model_snapshot = fixture.model_snapshot
        self.thinking_mode = fixture.thinking_mode


async def _synthetic_llm(prompt: str, *_args: Any, **_kwargs: Any) -> str:
    fixture = SYNTHETIC_PILOT_FIXTURE
    if fixture.failure_profile in prompt:
        raise RuntimeError("injected provider failure")
    return fixture.success_response_json


async def materialize_synthetic_pilot(
    *,
    output_root: Path,
    protocol_version: str,
    protocol_sha256: str,
    code_commit: str,
) -> None:
    """Materialize the one canonical offline success pair and failure probe."""
    fixture = SYNTHETIC_PILOT_FIXTURE
    client = _SyntheticClient(fixture)
    await run_venue_pair(
        output_root=output_root,
        pair_id=fixture.success_pair_id,
        run_id=fixture.success_run_id,
        paper_id=fixture.paper_id,
        paper_text=fixture.paper_text,
        venue_label=fixture.venue_label,
        generic_profile=fixture.generic_profile,
        venue_profile=fixture.venue_profile,
        protocol_version=protocol_version,
        protocol_sha256=protocol_sha256,
        code_commit=code_commit,
        cloud_client=client,
        llm_call=_synthetic_llm,
    )
    await run_venue_invocation(
        output_root=output_root,
        pair_id=fixture.failure_pair_id,
        run_id=fixture.failure_run_id,
        condition="venue_conditioned",
        paper_id=fixture.paper_id,
        paper_text=fixture.paper_text,
        venue_label=fixture.venue_label,
        profile_text=fixture.failure_profile,
        protocol_version=protocol_version,
        protocol_sha256=protocol_sha256,
        code_commit=code_commit,
        cloud_client=client,
        llm_call=_synthetic_llm,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-pilot", action="store_true", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    asyncio.run(
        materialize_synthetic_pilot(
            output_root=args.output_dir,
            protocol_version=args.protocol_version,
            protocol_sha256=args.protocol_sha256,
            code_commit=args.code_commit,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
