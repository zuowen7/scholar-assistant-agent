"""Focused offline tests for the RQ3 venue-profile isolation runner."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_venue_ab import (  # noqa: E402
    RUN_RECORD_SCHEMA_VERSION,
    SYNTHETIC_PILOT_FIXTURE,
    materialize_synthetic_pilot,
    run_venue_invocation,
    run_venue_pair,
)
from verify_freeze import validate_instance  # noqa: E402

VALIDATION_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = VALIDATION_ROOT.parents[1]
PROTOCOL_HASH = "1" * 64
CODE_COMMIT = "a" * 40
PAPER_TEXT = """\
# Abstract

We propose a small method and state one limitation.

# Experiments

The method is compared with one baseline.
"""


def _validate_record(record: dict) -> None:
    schema_path = VALIDATION_ROOT / "schemas" / "run_record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    assert (
        validate_instance(record, RUN_RECORD_SCHEMA_VERSION, schema_path.parent) == []
    )


def _artifact_refs(value):
    if isinstance(value, dict):
        if {"path", "sha256", "byte_length"} <= value.keys():
            yield value
        for nested in value.values():
            yield from _artifact_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _artifact_refs(nested)


@pytest.fixture
def output_root(request):
    root = (
        VALIDATION_ROOT
        / "outputs"
        / "pilot"
        / "venue"
        / "_pytest"
        / f"{request.node.name}-{uuid.uuid4().hex}"
    )
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root)


class FakeClient:
    provider = "fixture-provider"
    api_format = "controlled-fixture"
    model = "fixture-model-v1"
    model_snapshot = "offline"
    thinking_mode = "disabled"
    api_key = "must-never-appear-in-artifacts"


class FailingOllamaClient:
    provider = "ollama"
    model = "fixture-ollama-v1"
    thinking_mode = "disabled"

    def __init__(self) -> None:
        self.calls = 0

    def translate(self, _prompt):
        self.calls += 1
        raise RuntimeError("local provider failed")


def _common_kwargs(output_root: Path) -> dict:
    return {
        "output_root": output_root,
        "pair_id": "pair-001",
        "run_id": "run-001",
        "paper_id": "development-paper-001",
        "paper_text": PAPER_TEXT,
        "venue_label": "NeurIPS",
        "protocol_version": "reviewer-validation/v1",
        "protocol_sha256": PROTOCOL_HASH,
        "code_commit": CODE_COMMIT,
    }


@pytest.mark.asyncio
async def test_pair_changes_only_profile_and_uses_serial_llm_check(output_root):
    prompts: list[str] = []

    async def fake_llm(prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return "[]"

    with (
        patch("src.argument.reviewer.ledger_cross_check") as ledger_check,
        patch("src.argument.reviewer.coherence_check", new=AsyncMock()) as coherence,
        patch(
            "src.argument.reviewer.related_work_check", new=AsyncMock()
        ) as related_work,
        patch("src.argument.reviewer.run_review_parallel", create=True) as parallel,
    ):
        result = await run_venue_pair(
            **_common_kwargs(output_root),
            generic_profile="GENERIC_PROFILE_MARKER",
            venue_profile="VENUE_PROFILE_MARKER",
            cloud_client=FakeClient(),
            llm_call=fake_llm,
        )

    assert len(prompts) == 2
    assert all("投稿到 NeurIPS" in prompt for prompt in prompts)
    assert result["request_diff"]["unexpected_differences"] == []
    assert result["request_diff"]["invariant_checks"]["canonical_prompt_equal"] is True
    assert (
        result["request_diff"]["invariant_checks"]["base_model_request_equal"] is True
    )
    assert result["request_diff"]["invariant_checks"]["venue_label_equal"] is True
    assert result["request_diff"]["invariant_checks"]["excerpt_equal"] is True
    assert result["request_diff"]["invariant_checks"]["checks_llm_only"] is True
    ledger_check.assert_not_called()
    coherence.assert_not_awaited()
    related_work.assert_not_awaited()
    parallel.assert_not_called()

    records = result["records"]
    assert set(records) == {"generic", "venue_conditioned"}
    for condition, record in records.items():
        _validate_record(record)
        assert record["schema_version"] == RUN_RECORD_SCHEMA_VERSION
        assert record["condition"] == condition
        assert record["provider"] == {
            "name": "fixture-provider",
            "api_format": "controlled-fixture",
            "client_count": 1,
            "fallback_call_count": 0,
        }
        assert record["pair_id"] == "pair-001"
        assert record["venue_label"] == "NeurIPS"
        assert record["checks"] == ["llm"]
        assert len(record["steps"]) == 1
        assert record["steps"][0]["phase"] == "venue_review"
        assert (
            record["steps"][0]["attempts"][0]["prompt"]
            == record["steps"][0]["inputs"]["prompt"]
        )
        assert record["termination"]["status"] == "legal_empty"
        assert record["termination"]["attempt_count"] == 1

    manifest_text = (output_root / "run_manifest.jsonl").read_text(encoding="utf-8")
    assert "must-never-appear-in-artifacts" not in manifest_text
    assert len(manifest_text.splitlines()) == 2


@pytest.mark.asyncio
async def test_pair_consumes_and_compares_complete_real_long_profile(output_root):
    profiles = yaml.safe_load(
        (REPO_ROOT / "python/src/argument/venue_profiles.yaml").read_text(
            encoding="utf-8"
        )
    )
    venue_profile = profiles["NeurIPS"]
    assert len(venue_profile) > 600
    generic_profile = venue_profile[:-2] + "X" + venue_profile[-1]
    assert generic_profile[:600] == venue_profile[:600]
    assert generic_profile != venue_profile

    prompts: list[str] = []

    async def fake_llm(prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return "[]"

    result = await run_venue_pair(
        **_common_kwargs(output_root),
        generic_profile=generic_profile,
        venue_profile=venue_profile,
        cloud_client=FakeClient(),
        llm_call=fake_llm,
    )

    assert len(prompts) == 2
    assert generic_profile in prompts[0]
    assert venue_profile in prompts[1]
    pair_root = output_root / "pair-001"
    assert (pair_root / "generic" / "profile.txt").read_text(
        encoding="utf-8"
    ) == generic_profile
    assert (pair_root / "venue_conditioned" / "profile.txt").read_text(
        encoding="utf-8"
    ) == venue_profile
    assert result["request_diff"]["profile_sha256"] == {
        "generic": hashlib.sha256(generic_profile.encode("utf-8")).hexdigest(),
        "venue_conditioned": hashlib.sha256(venue_profile.encode("utf-8")).hexdigest(),
    }
    assert result["request_diff"]["unexpected_differences"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cloud,ollama", [(None, None), (FakeClient(), FakeClient())])
async def test_zero_or_two_clients_fail_before_request(output_root, cloud, ollama):
    llm_call = AsyncMock(return_value="[]")

    with pytest.raises(ValueError, match="exactly one"):
        await run_venue_pair(
            **_common_kwargs(output_root),
            generic_profile="GENERIC",
            venue_profile="VENUE",
            cloud_client=cloud,
            ollama_client=ollama,
            llm_call=llm_call,
        )

    llm_call.assert_not_awaited()
    assert not (output_root / "run_manifest.jsonl").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (TimeoutError("timed out"), "timeout"),
        (RuntimeError("provider failed"), "provider_error"),
        ("", "empty_response"),
        ("not json", "invalid_json"),
        ("[]", "legal_empty"),
    ],
)
async def test_failure_taxonomy_is_not_collapsed(
    output_root, response, expected_status
):
    async def fake_llm(*_args, **_kwargs):
        if isinstance(response, BaseException):
            raise response
        return response

    result = await run_venue_invocation(
        **_common_kwargs(output_root),
        condition="generic",
        profile_text="GENERIC PROFILE",
        cloud_client=FakeClient(),
        llm_call=fake_llm,
    )

    record = result.record
    _validate_record(record)
    assert record["termination"]["status"] == expected_status
    assert record["steps"][0]["attempts"][0]["status"] == expected_status
    assert record["provider"]["fallback_call_count"] == 0
    assert record["termination"]["attempt_count"] == 1
    if expected_status in {
        "provider_error",
        "timeout",
        "empty_response",
        "invalid_json",
    }:
        assert record["output"] is None
        assert record["termination"]["error"] is not None
    elif expected_status == "legal_empty":
        assert record["output"] is not None


@pytest.mark.asyncio
async def test_ollama_exception_is_not_silently_reclassified_as_empty(output_root):
    client = FailingOllamaClient()

    result = await run_venue_invocation(
        **_common_kwargs(output_root),
        condition="generic",
        profile_text="GENERIC PROFILE",
        ollama_client=client,
    )

    _validate_record(result.record)
    assert client.calls == 1
    assert result.record["termination"]["status"] == "provider_error"
    assert result.record["provider"]["api_format"] == "ollama-translate"
    assert result.record["provider"]["fallback_call_count"] == 0


@pytest.mark.asyncio
async def test_manifest_artifact_hashes_cover_actual_bytes(output_root):
    async def fake_llm(*_args, **_kwargs):
        return json.dumps(
            [
                {
                    "category": "baseline",
                    "severity": "major",
                    "title": "Weak comparison",
                    "detail": "Only one baseline is visible.",
                }
            ]
        )

    result = await run_venue_invocation(
        **_common_kwargs(output_root),
        condition="venue_conditioned",
        profile_text="VENUE PROFILE",
        cloud_client=FakeClient(),
        llm_call=fake_llm,
    )

    record = result.record
    _validate_record(record)
    step = record["steps"][0]
    refs = [
        step["inputs"]["excerpt"],
        step["inputs"]["prompt"],
        step["inputs"]["profile"],
        step["attempts"][0]["prompt"],
        step["attempts"][0]["request"],
        step["attempts"][0]["raw_response"],
        step["attempts"][0]["parsed_output"],
    ]
    for ref in refs:
        artifact = REPO_ROOT / ref["path"]
        data = artifact.read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref["sha256"]
        assert len(data) == ref["byte_length"]


@pytest.mark.asyncio
async def test_both_pair_conditions_share_exact_request_metadata(output_root):
    async def fake_llm(*_args, **_kwargs):
        return "[]"

    result = await run_venue_pair(
        **_common_kwargs(output_root),
        generic_profile="GENERIC PROFILE",
        venue_profile="VENUE PROFILE",
        cloud_client=FakeClient(),
        llm_call=fake_llm,
        seed=17,
        condition_order=("venue_conditioned", "generic"),
    )

    generic = result["records"]["generic"]
    venue = result["records"]["venue_conditioned"]
    assert generic["run_id"] == venue["run_id"]
    assert generic["paper_id"] == venue["paper_id"]
    assert generic["provider"] == venue["provider"]
    assert generic["model"] == venue["model"]
    assert generic["generation"] == venue["generation"]
    generic_inputs = generic["steps"][0]["inputs"]
    venue_inputs = venue["steps"][0]["inputs"]
    assert generic_inputs["excerpt"]["sha256"] == venue_inputs["excerpt"]["sha256"]
    assert generic_inputs["profile"]["sha256"] != venue_inputs["profile"]["sha256"]
    assert result["request_diff"]["condition_order"] == ["venue_conditioned", "generic"]
    diff = result["request_diff"]
    assert (
        diff["base_prompt_sha256"]["generic"]
        == diff["base_prompt_sha256"]["venue_conditioned"]
    )
    assert (
        diff["base_model_request_sha256"]["generic"]
        == diff["base_model_request_sha256"]["venue_conditioned"]
    )
    assert (
        diff["excerpt_sha256"]["generic"] == diff["excerpt_sha256"]["venue_conditioned"]
    )
    assert (
        diff["venue_label"]["generic_base_prompt_offsets"]
        == diff["venue_label"]["venue_conditioned_base_prompt_offsets"]
    )


@pytest.mark.asyncio
async def test_materializes_offline_synthetic_pilot_artifacts():
    validation_root = Path(__file__).resolve().parents[1]
    protocol_path = validation_root / "protocol.yaml"
    protocol_bytes = protocol_path.read_bytes()
    protocol = yaml.safe_load(protocol_bytes)
    protocol_hash = hashlib.sha256(protocol_bytes).hexdigest()
    detached_protocol_hash = (
        (validation_root / "protocol.sha256").read_text(encoding="utf-8").split()[0]
    )
    assert detached_protocol_hash == protocol_hash
    output_root = (
        validation_root
        / "outputs"
        / "pilot"
        / "venue"
        / f"{protocol_hash[:12]}-canonical-v1"
    )
    code_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=validation_root.parents[1],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    baseline_commit = subprocess.run(
        ["git", "rev-parse", protocol["baseline_commit"]],
        cwd=validation_root.parents[1],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest_path = output_root / "run_manifest.jsonl"

    if not manifest_path.exists():
        await materialize_synthetic_pilot(
            output_root=output_root,
            protocol_version=protocol["protocol_version"],
            protocol_sha256=protocol_hash,
            code_commit=code_commit,
        )

    records = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 3
    fixture = SYNTHETIC_PILOT_FIXTURE
    for record in records:
        _validate_record(record)
        assert record["protocol_sha256"] == protocol_hash
        assert record["code_commit"] in {code_commit, baseline_commit}
        assert record["paper_id"] == fixture.paper_id
        assert record["venue_label"] == fixture.venue_label
        assert record["provider"] == {
            "name": fixture.provider_name,
            "api_format": fixture.api_format,
            "client_count": 1,
            "fallback_call_count": 0,
        }
        assert record["model"] == {
            "id": fixture.model_id,
            "snapshot": fixture.model_snapshot,
        }
        for ref in _artifact_refs(record):
            artifact_bytes = (REPO_ROOT / ref["path"]).read_bytes()
            assert len(artifact_bytes) == ref["byte_length"]
            assert hashlib.sha256(artifact_bytes).hexdigest() == ref["sha256"]
    statuses = {record["termination"]["status"] for record in records}
    assert statuses == {"success", "provider_error"}
    pair_root = output_root / fixture.success_pair_id
    assert (pair_root / "generic" / "excerpt.txt").read_text(encoding="utf-8") == (
        fixture.paper_text
    )
    assert (pair_root / "generic" / "profile.txt").read_text(encoding="utf-8") == (
        fixture.generic_profile
    )
    assert (pair_root / "venue_conditioned" / "profile.txt").read_text(
        encoding="utf-8"
    ) == fixture.venue_profile
    diff_path = pair_root / "canonical_request_diff.json"
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    assert diff["unexpected_differences"] == []
    assert all(diff["invariant_checks"].values())
