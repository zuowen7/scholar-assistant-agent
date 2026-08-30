"""Focused gates for Work Item A; all LLM behavior is controlled and offline."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator

from src.argument.ledger import (
    materialize_discharge_classifications,
    prepare_ledger_classification,
    prepare_ledger_extraction,
    run_ledger_classification_stage,
    run_ledger_extraction_stage,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = (
    REPO_ROOT / "methods" / "reviewer_validation" / "scripts" / "run_ledger.py"
)
SPEC = importlib.util.spec_from_file_location(
    "reviewer_validation_run_ledger", RUNNER_PATH
)
assert SPEC and SPEC.loader
run_ledger = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_ledger
SPEC.loader.exec_module(run_ledger)

PAPER_TEXT = (
    "# Abstract\n\n"
    "We propose Method Z and promise that it improves accuracy.\n\n"
    "# 1 Introduction\n\n"
    "Method Z addresses a documented gap.\n\n"
    "# 3 Method\n\n"
    "Method Z uses a constrained decoder.\n\n"
    "# 4 Experiments\n\n"
    "Table 1 reports a two point accuracy gain.\n"
)
EXTRACTION = json.dumps(
    {
        "promises": [
            {
                "local_id": "p1",
                "kind": "contribution",
                "text": "We propose Method Z.",
                "verbatim_quote": "We propose Method Z",
            }
        ]
    }
)
CLASSIFICATION = json.dumps(
    [
        {
            "promise_local_id": "p1",
            "status": "paid",
            "discharge_quotes": ["Table 1 reports a two point accuracy gain"],
            "note": "Table 1 supplies direct evidence.",
        }
    ]
)


class _Client:
    model = "fixture-model"
    thinking_mode = "disabled"


def _run(coro):
    return asyncio.run(coro)


def test_extraction_and_classification_reuse_exact_production_requests():
    caller = run_ledger.FixtureLLM([EXTRACTION, CLASSIFICATION])
    client = _Client()

    extraction = _run(
        run_ledger_extraction_stage(
            PAPER_TEXT,
            cloud_client=client,
            llm_call=caller,
        )
    )
    classification = _run(
        run_ledger_classification_stage(
            PAPER_TEXT,
            extraction.parsed_output,
            cloud_client=client,
            llm_call=caller,
        )
    )

    expected_extraction = prepare_ledger_extraction(PAPER_TEXT)
    expected_classification = prepare_ledger_classification(
        PAPER_TEXT, extraction.parsed_output
    )
    assert caller.calls[0]["prompt"].encode() == expected_extraction.prompt.encode()
    assert caller.calls[1]["prompt"].encode() == expected_classification.prompt.encode()
    assert (
        caller.calls[0]["generation"]
        == caller.calls[1]["generation"]
        == {
            "max_tokens": 4096,
            "temperature": 0.3,
            "json_mode": True,
        }
    )
    assert (
        extraction.request.excerpt.text.encode()
        == expected_extraction.excerpt.text.encode()
    )
    assert (
        classification.request.excerpt.text.encode()
        == expected_classification.excerpt.text.encode()
    )


def test_gold_conditioned_mode_does_not_call_extraction(monkeypatch):
    extraction_spy = AsyncMock(side_effect=AssertionError("extraction must not run"))
    monkeypatch.setattr(run_ledger, "run_ledger_extraction_stage", extraction_spy)
    caller = run_ledger.FixtureLLM(
        [
            json.dumps(
                [
                    {
                        "promise_local_id": "gold-1",
                        "status": "paid",
                        "discharge_quotes": [],
                    }
                ]
            )
        ]
    )
    gold = [
        {
            "promise_id": "gold-1",
            "kind": "contribution",
            "exact_quote": "We propose Method Z",
        }
    ]

    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="gold_conditioned_status",
            text=PAPER_TEXT,
            gold_promises=gold,
            cloud_client=_Client(),
            llm_call=caller,
        )
    )

    extraction_spy.assert_not_awaited()
    assert len(caller.calls) == 1
    assert "(id=gold-1) We propose Method Z" in caller.calls[0]["prompt"]
    assert execution.output["classifications"][0]["status"] == "paid"
    assert run_ledger.execution_counts(execution)["extracted_promises"] == 0


def test_end_to_end_uses_current_extraction_output():
    caller = run_ledger.FixtureLLM([EXTRACTION, CLASSIFICATION])

    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="end_to_end",
            text=PAPER_TEXT,
            cloud_client=_Client(),
            llm_call=caller,
        )
    )

    assert len(execution.steps) == 2
    assert len(caller.calls) == 2
    assert "(id=p1) We propose Method Z." in caller.calls[1]["prompt"]
    assert execution.output["classifications"][0]["status"] == "paid"


@pytest.mark.parametrize(
    ("cloud", "ollama", "expected_count"),
    [(None, None, 0), (_Client(), _Client(), 2)],
)
def test_runner_rejects_zero_or_two_clients_before_request(
    cloud, ollama, expected_count
):
    caller = run_ledger.FixtureLLM([EXTRACTION])
    with pytest.raises(ValueError, match=f"got {expected_count}"):
        _run(
            run_ledger.execute_ledger_mode(
                mode="extraction",
                text=PAPER_TEXT,
                cloud_client=cloud,
                ollama_client=ollama,
                llm_call=caller,
            )
        )
    assert caller.calls == []


def test_strict_single_ollama_failure_is_provider_error_not_empty_response():
    class FailingOllama:
        def translate(self, prompt):
            raise RuntimeError("ollama unavailable")

    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="extraction",
            text=PAPER_TEXT,
            cloud_client=None,
            ollama_client=FailingOllama(),
        )
    )

    assert execution.termination_status == "provider_error"
    assert execution.steps[0].attempts[0].raw_response is None


def test_valid_empty_array_and_empty_response_are_not_merged():
    client = _Client()
    legal_empty = _run(
        run_ledger_extraction_stage(
            PAPER_TEXT,
            cloud_client=client,
            llm_call=run_ledger.FixtureLLM(['{"promises": []}']),
        )
    )
    empty_response = _run(
        run_ledger_extraction_stage(
            PAPER_TEXT,
            cloud_client=client,
            llm_call=run_ledger.FixtureLLM(["", ""]),
        )
    )

    assert legal_empty.termination_status == "legal_empty"
    assert len(legal_empty.attempts) == 1
    assert empty_response.termination_status == "empty_response"
    assert len(empty_response.attempts) == 2


@pytest.mark.parametrize(
    ("responses", "expected_status"),
    [
        (["not-json", "still-not-json"], "invalid_json"),
        ([TimeoutError("late")], "timeout"),
        ([RuntimeError("provider down")], "provider_error"),
    ],
)
def test_extraction_failure_taxonomy(responses, expected_status):
    result = _run(
        run_ledger_extraction_stage(
            PAPER_TEXT,
            cloud_client=_Client(),
            llm_call=run_ledger.FixtureLLM(responses),
        )
    )
    assert result.termination_status == expected_status
    assert result.attempts[-1].status == expected_status


def test_missing_classification_and_unknown_status_are_distinct():
    promises = [
        {"local_id": "p1", "text": "one"},
        {"local_id": "p2", "text": "two"},
    ]
    parsed = [{"promise_local_id": "p1", "status": "unsupported-new-label"}]

    outcomes = materialize_discharge_classifications(promises, parsed)

    assert outcomes[0]["status"] == "unknown"
    assert outcomes[0]["failure_reason"] == "unknown_status"
    assert outcomes[1]["status"] == "unknown"
    assert outcomes[1]["failure_reason"] == "missing_classification"


def test_attempt_trace_preserves_repair_prompt_and_first_failure():
    result = _run(
        run_ledger_extraction_stage(
            PAPER_TEXT,
            cloud_client=_Client(),
            llm_call=run_ledger.FixtureLLM(["not-json", EXTRACTION]),
        )
    )

    assert [attempt.status for attempt in result.attempts] == [
        "invalid_json",
        "success",
    ]
    assert result.attempts[0].raw_response == "not-json"
    assert result.attempts[1].prompt == "请只输出有效的 JSON 对象：\nnot-json"
    assert (
        result.attempts[0].raw_response_sha256
        == hashlib.sha256(b"not-json").hexdigest()
    )


def test_provider_failure_is_not_legal_empty_and_has_no_fallback():
    caller = run_ledger.FixtureLLM([RuntimeError("primary failed")])
    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="extraction",
            text=PAPER_TEXT,
            cloud_client=_Client(),
            ollama_client=None,
            llm_call=caller,
        )
    )

    assert execution.termination_status == "provider_error"
    assert execution.steps[0].termination_status != "legal_empty"
    assert len(caller.calls) == 1
    assert caller.calls[0]["ollama_client"] is None


def test_classification_preserves_same_provider_retry_attempts():
    caller = run_ledger.FixtureLLM([RuntimeError("transient"), CLASSIFICATION])
    client = _Client()
    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="gold_conditioned_status",
            text=PAPER_TEXT,
            gold_promises=[
                {
                    "promise_id": "p1",
                    "kind": "contribution",
                    "exact_quote": "We propose Method Z",
                }
            ],
            cloud_client=client,
            ollama_client=None,
            llm_call=caller,
        )
    )

    assert [attempt.status for attempt in execution.steps[0].attempts] == [
        "provider_error",
        "success",
    ]
    assert execution.steps[0].attempts[0].raw_response is None
    assert caller.calls[1]["prompt"] == "请只输出有效的 JSON 数组：\n[]"
    assert all(call["cloud_client"] is client for call in caller.calls)
    assert all(call["ollama_client"] is None for call in caller.calls)


def test_trace_is_schema_valid_complete_and_hash_reproducible(tmp_path, monkeypatch):
    caller = run_ledger.FixtureLLM(["not-json", EXTRACTION, CLASSIFICATION])
    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="end_to_end",
            text=PAPER_TEXT,
            cloud_client=_Client(),
            llm_call=caller,
        )
    )
    monkeypatch.setattr(run_ledger, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_ledger, "_git_commit", lambda: "a" * 40)
    output_dir = (
        tmp_path / "methods" / "reviewer_validation" / "outputs" / "pilot" / "ledger"
    )

    record_path, record = run_ledger.write_execution_record(
        execution,
        output_dir=output_dir,
        paper_id="synthetic-paper",
        run_id="run-1",
        protocol_version="draft-1",
        protocol_sha256="b" * 64,
        provider_name="controlled-fixture",
        model_id="fixture-model",
    )

    schema = json.loads(
        (
            REPO_ROOT
            / "methods"
            / "reviewer_validation"
            / "schemas"
            / "run_record.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(record)
    assert json.loads(record_path.read_text(encoding="utf-8")) == record
    assert len(record["steps"]) == 2
    assert record["provider"] == {
        "name": "controlled-fixture",
        "api_format": "controlled-fixture",
        "client_count": 1,
        "fallback_call_count": 0,
    }
    assert [step["phase"] for step in record["steps"]] == [
        "extraction",
        "discharge_classification",
    ]
    assert [attempt["status"] for attempt in record["steps"][0]["attempts"]] == [
        "invalid_json",
        "success",
    ]
    assert record["steps"][0]["attempts"][0]["error"] == {
        "type": "InvalidJSONResponse",
        "message_redacted": "LLM response was not valid JSON",
    }
    for step in record["steps"]:
        excerpt_ref = step["inputs"]["excerpt"]
        excerpt_bytes = (tmp_path / excerpt_ref["path"]).read_bytes()
        assert hashlib.sha256(excerpt_bytes).hexdigest() == excerpt_ref["sha256"]
        assert len(excerpt_bytes) == excerpt_ref["byte_length"]
        for attempt in step["attempts"]:
            prompt = (tmp_path / attempt["prompt"]["path"]).read_text(encoding="utf-8")
            request = json.loads(
                (tmp_path / attempt["request"]["path"]).read_text(encoding="utf-8")
            )
            assert request["prompt"] == prompt
            if attempt["raw_response"] is not None:
                raw_ref = attempt["raw_response"]
                raw_bytes = (tmp_path / raw_ref["path"]).read_bytes()
                assert hashlib.sha256(raw_bytes).hexdigest() == raw_ref["sha256"]


def test_trace_writer_fails_closed_on_secret_like_content(tmp_path, monkeypatch):
    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="extraction",
            text=PAPER_TEXT,
            cloud_client=_Client(),
            llm_call=run_ledger.FixtureLLM([EXTRACTION]),
        )
    )
    monkeypatch.setattr(run_ledger, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_ledger, "_git_commit", lambda: "a" * 40)
    output_dir = (
        tmp_path / "methods" / "reviewer_validation" / "outputs" / "pilot" / "ledger"
    )

    with pytest.raises(ValueError, match="secret-like"):
        run_ledger.write_execution_record(
            execution,
            output_dir=output_dir,
            paper_id="synthetic-paper",
            run_id="secret-run",
            protocol_version="draft-1",
            protocol_sha256="b" * 64,
            provider_name="controlled-fixture",
            model_id="sk-super-secret-value",
        )
    assert not output_dir.exists()


def test_trace_writer_never_overwrites_first_failure_record(tmp_path, monkeypatch):
    execution = _run(
        run_ledger.execute_ledger_mode(
            mode="extraction",
            text=PAPER_TEXT,
            cloud_client=_Client(),
            llm_call=run_ledger.FixtureLLM([RuntimeError("provider down")]),
        )
    )
    monkeypatch.setattr(run_ledger, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_ledger, "_git_commit", lambda: "a" * 40)
    output_dir = (
        tmp_path / "methods" / "reviewer_validation" / "outputs" / "pilot" / "ledger"
    )
    kwargs = {
        "output_dir": output_dir,
        "paper_id": "synthetic-paper",
        "run_id": "provider-error",
        "protocol_version": "draft-1",
        "protocol_sha256": "b" * 64,
        "provider_name": "controlled-fixture",
        "model_id": "fixture-model",
    }

    record_path, _record = run_ledger.write_execution_record(execution, **kwargs)
    first_bytes = record_path.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_ledger.write_execution_record(execution, **kwargs)
    assert record_path.read_bytes() == first_bytes


@pytest.mark.parametrize(
    ("mode", "responses", "gold_promises", "expected_status"),
    [
        ("extraction", ['{"promises": []}'], None, "legal_empty"),
        ("extraction", ["", ""], None, "empty_response"),
        ("extraction", ["not-json", "still-not-json"], None, "invalid_json"),
        ("extraction", [TimeoutError("late")], None, "timeout"),
        ("extraction", [RuntimeError("provider down")], None, "provider_error"),
        (
            "gold_conditioned_status",
            ['[{"promise_local_id":"p1","status":"paid"}]'],
            [
                {"promise_id": "p1", "exact_quote": "one"},
                {"promise_id": "p2", "exact_quote": "two"},
            ],
            "classification_incomplete",
        ),
        (
            "gold_conditioned_status",
            ['[{"promise_local_id":"p1","status":"new-label"}]'],
            [{"promise_id": "p1", "exact_quote": "one"}],
            "unknown_status",
        ),
    ],
)
def test_schema_records_preserve_each_failure_class(
    tmp_path,
    monkeypatch,
    mode,
    responses,
    gold_promises,
    expected_status,
):
    execution = _run(
        run_ledger.execute_ledger_mode(
            mode=mode,
            text=PAPER_TEXT,
            gold_promises=gold_promises,
            cloud_client=_Client(),
            llm_call=run_ledger.FixtureLLM(responses),
        )
    )
    monkeypatch.setattr(run_ledger, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_ledger, "_git_commit", lambda: "a" * 40)
    output_dir = (
        tmp_path / "methods" / "reviewer_validation" / "outputs" / "pilot" / "ledger"
    )

    record_path, record = run_ledger.write_execution_record(
        execution,
        output_dir=output_dir,
        paper_id="synthetic-paper",
        run_id=expected_status,
        protocol_version="draft-1",
        protocol_sha256="b" * 64,
        provider_name="controlled-fixture",
        model_id="fixture-model",
        api_format="fixture-chat",
    )

    assert record_path.is_file()
    assert record["termination"]["status"] == expected_status
    if expected_status in {"success", "legal_empty"}:
        assert record["termination"]["error"] is None
    else:
        assert record["termination"]["error"] is not None
    if mode == "gold_conditioned_status":
        assert record["denominators"]["prediction_occurrences"] is None
