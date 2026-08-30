"""Production-equivalent Ledger staging and append-only trace writer.

The callable API accepts an explicit single provider client.  The CLI is
deliberately offline-only for the first pilot and consumes controlled response
fixtures; it cannot make a real external LLM request accidentally.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
SCRIPTS_ROOT = Path(__file__).resolve().parent
RUN_RECORD_SCHEMA = (
    REPO_ROOT / "methods" / "reviewer_validation" / "schemas" / "run_record.schema.json"
)
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from src.argument.ledger import (  # noqa: E402
    LedgerLLMCall,
    LedgerStageResult,
    materialize_discharge_classifications,
    run_ledger_classification_stage,
    run_ledger_extraction_stage,
)
from src.argument.llm_client import call_llm_chat  # noqa: E402
from verify_freeze import validate_instance  # noqa: E402

SCHEMA_VERSION = "reviewer-validation-run-record/v1"
_SUCCESS = frozenset({"success", "legal_empty"})
_MODES = frozenset({"extraction", "gold_conditioned_status", "end_to_end"})
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._~+\-/=]{8,}|\bsk-[a-z0-9_-]{8,}|"
    r"(?:api[_ -]?key|authorization)\s*[:=]\s*\S+)"
)


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    if not segment:
        raise ValueError("identifier has no safe path characters")
    return segment[:96]


def _assert_no_secret(value: str, *, label: str) -> None:
    if _SECRET_VALUE_RE.search(value):
        raise ValueError(f"secret-like value rejected in {label}")


def _assert_exactly_one_client(
    cloud_client: Any, ollama_client: Any
) -> tuple[str, Any]:
    clients = [("cloud", cloud_client), ("ollama", ollama_client)]
    present = [(name, client) for name, client in clients if client is not None]
    if len(present) != 1:
        raise ValueError(
            f"Ledger evaluation requires exactly one logical client; got {len(present)}"
        )
    return present[0]


async def call_single_provider(
    prompt: str,
    cloud_client: Any,
    ollama_client: Any,
    **generation: Any,
) -> str:
    """Use one provider and surface its exception instead of falling back."""
    provider_kind, client = _assert_exactly_one_client(cloud_client, ollama_client)
    if provider_kind == "cloud":
        return await call_llm_chat(
            prompt,
            cloud_client=client,
            ollama_client=None,
            **generation,
        )
    result = client.translate(prompt)
    if hasattr(result, "translated"):
        return str(result.translated)
    if hasattr(result, "text"):
        return str(result.text)
    return str(result)


def normalize_gold_promises(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map frozen gold fields to the production classification prompt contract."""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        local_id = str(item.get("local_id") or item.get("promise_id") or "").strip()
        text = str(item.get("text") or item.get("exact_quote") or "").strip()
        if not local_id or not text:
            raise ValueError(
                f"gold promise {index} requires promise_id/local_id and text/exact_quote"
            )
        if local_id in seen:
            raise ValueError(f"duplicate gold promise identifier: {local_id}")
        seen.add(local_id)
        normalized.append(
            {
                "local_id": local_id,
                "kind": item.get("kind", "claim"),
                "text": text,
                "verbatim_quote": item.get("verbatim_quote")
                or item.get("exact_quote")
                or text,
            }
        )
    return normalized


@dataclass(frozen=True)
class LedgerExecution:
    mode: str
    steps: tuple[LedgerStageResult, ...]
    source_promises: tuple[dict[str, Any], ...]
    output: dict[str, Any]
    started_at: float
    ended_at: float

    @property
    def termination_status(self) -> str:
        if not self.steps:
            return "provider_error"
        for step in self.steps:
            if step.termination_status not in _SUCCESS:
                return step.termination_status
        classifications = self.output.get("classifications", [])
        if any(
            item.get("failure_reason") == "missing_classification"
            for item in classifications
        ):
            return "classification_incomplete"
        if any(
            item.get("failure_reason") == "unknown_status" for item in classifications
        ):
            return "unknown_status"
        return self.steps[-1].termination_status


async def execute_ledger_mode(
    *,
    mode: str,
    text: str,
    gold_promises: list[dict[str, Any]] | None = None,
    cloud_client: Any = None,
    ollama_client: Any = None,
    llm_call: LedgerLLMCall | None = None,
) -> LedgerExecution:
    """Execute exactly one of the three protocol Ledger modes."""
    if mode not in _MODES:
        raise ValueError(f"unsupported Ledger mode: {mode}")
    _assert_exactly_one_client(cloud_client, ollama_client)
    effective_llm_call = llm_call or call_single_provider
    started_at = datetime.now(tz=UTC).timestamp()
    steps: list[LedgerStageResult] = []
    source_promises: list[dict[str, Any]] = []

    if mode in {"extraction", "end_to_end"}:
        extraction = await run_ledger_extraction_stage(
            text,
            cloud_client,
            ollama_client,
            llm_call=effective_llm_call,
        )
        steps.append(extraction)
        source_promises = [dict(item) for item in extraction.parsed_output]
        if mode == "extraction" or extraction.termination_status not in _SUCCESS:
            return LedgerExecution(
                mode=mode,
                steps=tuple(steps),
                source_promises=tuple(source_promises),
                output={"promises": source_promises},
                started_at=started_at,
                ended_at=datetime.now(tz=UTC).timestamp(),
            )
        if not source_promises:
            return LedgerExecution(
                mode=mode,
                steps=tuple(steps),
                source_promises=(),
                output={"promises": [], "classifications": []},
                started_at=started_at,
                ended_at=datetime.now(tz=UTC).timestamp(),
            )
    else:
        source_promises = normalize_gold_promises(gold_promises or [])

    classification = await run_ledger_classification_stage(
        text,
        source_promises,
        cloud_client,
        ollama_client,
        llm_call=effective_llm_call,
    )
    steps.append(classification)
    classifications = materialize_discharge_classifications(
        source_promises,
        classification.parsed_output,
    )
    return LedgerExecution(
        mode=mode,
        steps=tuple(steps),
        source_promises=tuple(source_promises),
        output={
            "promises": source_promises,
            "classifications": classifications,
        },
        started_at=started_at,
        ended_at=datetime.now(tz=UTC).timestamp(),
    )


def execution_counts(execution: LedgerExecution) -> dict[str, int]:
    classifications = execution.output.get("classifications", [])
    attempts = [attempt for step in execution.steps for attempt in step.attempts]
    return {
        "actual_llm_call_count": len(attempts),
        "extracted_promises": (
            0
            if execution.mode == "gold_conditioned_status"
            else len(execution.output.get("promises", []))
        ),
        "classified_promises": sum(
            1 for item in classifications if item.get("failure_reason") is None
        ),
        "unknown": sum(
            1 for item in classifications if item.get("status") == "unknown"
        ),
        "missing_classification": sum(
            1
            for item in classifications
            if item.get("failure_reason") == "missing_classification"
        ),
        "legal_empty_attempts": sum(
            1 for attempt in attempts if attempt.status == "legal_empty"
        ),
        "empty_response_attempts": sum(
            1 for attempt in attempts if attempt.status == "empty_response"
        ),
        "invalid_json_attempts": sum(
            1 for attempt in attempts if attempt.status == "invalid_json"
        ),
        "timeout_attempts": sum(
            1 for attempt in attempts if attempt.status == "timeout"
        ),
        "provider_failure_attempts": sum(
            1 for attempt in attempts if attempt.status == "provider_error"
        ),
    }


class FixtureLLM:
    """Controlled response sequence used by tests and the offline pilot CLI."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        prompt: str,
        cloud_client: Any,
        ollama_client: Any,
        **generation: Any,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "cloud_client": cloud_client,
                "ollama_client": ollama_client,
                "generation": generation,
            }
        )
        try:
            response = next(self._responses)
        except StopIteration as exc:
            raise RuntimeError("fixture response sequence exhausted") from exc
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, dict) and "raise" in response:
            kind = str(response["raise"])
            if kind == "timeout":
                raise TimeoutError(str(response.get("message", "fixture timeout")))
            raise RuntimeError(str(response.get("message", kind)))
        return str(response)


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _artifact_ref(path: Path, content: str) -> dict[str, Any]:
    data = content.encode("utf-8")
    if path.exists():
        raise FileExistsError(f"refusing to overwrite pilot artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_bytes(data),
        "byte_length": len(data),
    }


def _validate_run_record(record: dict[str, Any]) -> None:
    errors = validate_instance(
        record,
        SCHEMA_VERSION,
        RUN_RECORD_SCHEMA.parent,
    )
    if errors:
        summary = "; ".join(errors[:8])
        raise ValueError(f"run record schema validation failed: {summary}")


def write_execution_record(
    execution: LedgerExecution,
    *,
    output_dir: Path,
    paper_id: str,
    run_id: str,
    protocol_version: str,
    protocol_sha256: str,
    provider_name: str,
    model_id: str,
    model_snapshot: str | None = None,
    api_format: str = "controlled-fixture",
    thinking_mode: str = "disabled",
    seed: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write exact per-attempt artifacts and one schema-oriented run record."""
    if not re.fullmatch(r"[0-9a-f]{64}", protocol_sha256):
        raise ValueError("protocol_sha256 must be 64 lowercase hexadecimal characters")
    record_id = "-".join(
        (_safe_segment(paper_id), _safe_segment(run_id), _safe_segment(execution.mode))
    )
    record_dir = output_dir.resolve() / record_id
    try:
        record_dir.relative_to(
            (
                REPO_ROOT
                / "methods"
                / "reviewer_validation"
                / "outputs"
                / "pilot"
                / "ledger"
            ).resolve()
        )
    except ValueError as exc:
        raise ValueError("pilot output must stay under outputs/pilot/ledger") from exc
    if record_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {record_dir}")

    all_sensitive_text = [provider_name, model_id, model_snapshot or "", api_format]
    for step in execution.steps:
        all_sensitive_text.extend([step.request.excerpt.text, step.request.prompt])
        for attempt in step.attempts:
            all_sensitive_text.append(attempt.prompt)
            if attempt.raw_response is not None:
                all_sensitive_text.append(attempt.raw_response)
            if attempt.error:
                all_sensitive_text.extend(attempt.error.values())
    for index, value in enumerate(all_sensitive_text):
        _assert_no_secret(str(value), label=f"trace value {index}")

    steps: list[dict[str, Any]] = []
    for step_index, step in enumerate(execution.steps, start=1):
        step_dir = (
            record_dir / f"step-{step_index:02d}-{_safe_segment(step.request.stage)}"
        )
        excerpt_ref = _artifact_ref(step_dir / "excerpt.txt", step.request.excerpt.text)
        prompt_ref = _artifact_ref(step_dir / "prompt.txt", step.request.prompt)
        gold_ref = None
        if execution.mode == "gold_conditioned_status" and step_index == 1:
            gold_ref = _artifact_ref(
                step_dir / "gold_promises.json",
                _canonical_json(list(execution.source_promises)),
            )
        attempts: list[dict[str, Any]] = []
        for attempt in step.attempts:
            attempt_dir = step_dir / f"attempt-{attempt.attempt_number:02d}"
            serialized_request = {
                "stage": step.request.stage,
                "prompt": attempt.prompt,
                "excerpt": {
                    "sha256": step.request.excerpt_sha256,
                    "source_sha256": step.request.excerpt.source_hash,
                    "source_characters": step.request.excerpt.original_chars,
                    "visible_characters": step.request.excerpt.excerpt_chars,
                    "covered_sections": list(step.request.excerpt.covered_sections),
                    "truncated": step.request.excerpt.truncated,
                },
                "provider": provider_name,
                "model": model_id,
                "api_format": api_format,
                "generation": {
                    "temperature": step.request.temperature,
                    "max_tokens": step.request.max_tokens,
                    "thinking_mode": thinking_mode,
                    "seed": seed,
                    "json_mode": step.request.json_mode,
                },
            }
            raw_response_ref = (
                _artifact_ref(attempt_dir / "raw_response.txt", attempt.raw_response)
                if attempt.raw_response is not None
                else None
            )
            parsed_output_ref = (
                _artifact_ref(
                    attempt_dir / "parsed_output.json",
                    _canonical_json(attempt.parsed_output),
                )
                if attempt.parsed_output is not None
                else None
            )
            attempts.append(
                {
                    "attempt_number": attempt.attempt_number,
                    "started_at": _utc_iso(attempt.started_at),
                    "ended_at": _utc_iso(attempt.ended_at),
                    "status": attempt.status,
                    "prompt": _artifact_ref(attempt_dir / "prompt.txt", attempt.prompt),
                    "request": _artifact_ref(
                        attempt_dir / "request.json",
                        _canonical_json(serialized_request),
                    ),
                    "raw_response": raw_response_ref,
                    "parsed_output": parsed_output_ref,
                    "error": (
                        {
                            "type": attempt.error["type"],
                            "message_redacted": attempt.error["message"],
                        }
                        if attempt.error
                        else None
                    ),
                }
            )
        step_status = step.termination_status
        if step.request.stage == "gold_conditioned_status" and step_status in _SUCCESS:
            step_outcomes = materialize_discharge_classifications(
                list(execution.source_promises), step.parsed_output
            )
            if any(
                item.get("failure_reason") == "missing_classification"
                for item in step_outcomes
            ):
                step_status = "classification_incomplete"
            elif any(
                item.get("failure_reason") == "unknown_status" for item in step_outcomes
            ):
                step_status = "unknown_status"
        steps.append(
            {
                "step_id": f"step-{step_index:02d}",
                "phase": (
                    "discharge_classification"
                    if step.request.stage == "gold_conditioned_status"
                    else step.request.stage
                ),
                "inputs": {
                    "excerpt": excerpt_ref,
                    "prompt": prompt_ref,
                    "profile": None,
                    "gold_promises": gold_ref,
                    "excerpt_coverage": {
                        "source_characters": step.request.excerpt.original_chars,
                        "visible_characters": step.request.excerpt.excerpt_chars,
                        "truncated": step.request.excerpt.truncated,
                    },
                },
                "attempts": attempts,
                "termination": {
                    "status": step_status,
                    "attempt_count": len(step.attempts),
                    "error": (
                        {
                            "type": step_status,
                            "message_redacted": step.error_message or step_status,
                        }
                        if step_status not in _SUCCESS
                        else None
                    ),
                },
            }
        )

    counts = execution_counts(execution)
    result_ref = _artifact_ref(
        record_dir / "result.json",
        _canonical_json({"result": execution.output, "counts": counts}),
    )
    first_request = execution.steps[0].request
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "run_id": run_id,
        "experiment": "rq1_ledger",
        "stage": execution.mode,
        "condition": "not_applicable",
        "paper_id": paper_id,
        "pair_id": None,
        "venue_label": None,
        "checks": (
            ["extraction", "discharge_classification"]
            if execution.mode == "end_to_end"
            else ["extraction"]
            if execution.mode == "extraction"
            else ["discharge_classification"]
        ),
        "protocol_version": protocol_version,
        "protocol_sha256": protocol_sha256,
        "code_commit": _git_commit(),
        "started_at": _utc_iso(execution.started_at),
        "ended_at": _utc_iso(execution.ended_at),
        "provider": {
            "name": provider_name,
            "api_format": api_format,
            "client_count": 1,
            "fallback_call_count": 0,
        },
        "model": {"id": model_id, "snapshot": model_snapshot},
        "generation": {
            "temperature": first_request.temperature,
            "max_tokens": first_request.max_tokens,
            "thinking_mode": thinking_mode,
            "seed": seed,
            "json_mode": first_request.json_mode,
        },
        "steps": steps,
        "output": result_ref,
        "termination": {
            "status": execution.termination_status,
            "attempt_count": sum(len(step.attempts) for step in execution.steps),
            "error": (
                {
                    "type": execution.termination_status,
                    "message_redacted": next(
                        (
                            step.error_message
                            for step in execution.steps
                            if step.error_message
                        ),
                        execution.termination_status,
                    ),
                }
                if execution.termination_status not in _SUCCESS
                else None
            ),
        },
        "denominators": {
            "planned_invocations": 1,
            "primary_unit": "paper",
            "gold_occurrences": (
                len(execution.source_promises)
                if execution.mode == "gold_conditioned_status"
                else None
            ),
            "prediction_occurrences": (
                None
                if execution.mode == "gold_conditioned_status"
                else len(execution.output.get("promises", []))
            ),
            "applicable_criteria": None,
            "critique_units": None,
        },
    }
    record_path = record_dir / "run_record.json"
    _validate_run_record(record)
    _artifact_ref(record_path, _canonical_json(record))
    return record_path, record


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture must be a JSON object")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(_MODES), required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--provider-name", default="controlled-fixture")
    parser.add_argument("--model-id", default="fixture-model")
    parser.add_argument("--api-format", default="controlled-fixture")
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    fixture = _load_fixture(args.fixture)
    responses = fixture.get("responses", [])
    if isinstance(responses, dict):
        responses = responses.get(args.mode, [])
    caller = FixtureLLM(list(responses))
    fake_client = object()
    execution = await execute_ledger_mode(
        mode=args.mode,
        text=str(fixture.get("text", "")),
        gold_promises=fixture.get("gold_promises"),
        cloud_client=fake_client,
        ollama_client=None,
        llm_call=caller,
    )
    path, record = write_execution_record(
        execution,
        output_dir=args.output_dir,
        paper_id=args.paper_id,
        run_id=args.run_id,
        protocol_version=args.protocol_version,
        protocol_sha256=args.protocol_sha256,
        provider_name=args.provider_name,
        model_id=args.model_id,
        api_format=args.api_format,
    )
    print(
        json.dumps(
            {
                "record": path.relative_to(REPO_ROOT).as_posix(),
                "termination": record["termination"],
                "counts": execution_counts(execution),
            },
            ensure_ascii=False,
        )
    )
    return 0 if execution.termination_status in _SUCCESS else 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
