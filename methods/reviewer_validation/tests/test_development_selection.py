from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
DEVELOPMENT_ROOT = ROOT / "methods" / "reviewer_validation" / "inputs" / "development"
SCRIPTS_ROOT = ROOT / "methods" / "reviewer_validation" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import run_model_selection as model_runner  # noqa: E402
from run_model_selection import (  # noqa: E402
    _aggregate_preference,
    _audit_pair_request_parity,
    _materialize_blind_package,
    _validate_request_before_send,
    build_preflight_report,
    build_run_plan,
    execute_paid_run,
    verify_development_inventory,
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load(name: str) -> dict:
    return yaml.safe_load((DEVELOPMENT_ROOT / name).read_text(encoding="utf-8"))


def test_development_manifest_is_nonformal_and_traceable() -> None:
    manifest = _load("manifest.yaml")

    assert manifest["status"] == "selected_parse_checked_human_audit_pending"
    assert manifest["development_only"] is True
    assert manifest["formal_denominator_eligible"] is False
    assert manifest["formal_run_authorized"] is False
    assert manifest["external_model_output_seen_before_selection"] is False
    assert manifest["selection"]["strategy"] == "purposive_maximum_variation"
    assert manifest["preparation"]["deterministic_repeat_check"] == "pass"
    assert SHA256_RE.fullmatch(
        manifest["preparation"]["deterministic_repeat_report_sha256"]
    )
    assert len(manifest["papers"]) == 2
    assert {paper["venue"] for paper in manifest["papers"]} == {"ICML", "CHI"}

    for paper in manifest["papers"]:
        assert paper["group"] == "development"
        assert SHA256_RE.fullmatch(paper["local_source"]["sha256"])
        assert SHA256_RE.fullmatch(paper["parsed_full_text"]["sha256"])
        assert paper["parsed_full_text"]["replacement_characters"] == 0
        assert (
            paper["eligibility"]["main_body_readability"] == "pending_two_human_audit"
        )
        for excerpt in paper["production_excerpts"].values():
            assert SHA256_RE.fullmatch(excerpt["sha256"])
            assert excerpt["character_length"] > 0
            assert excerpt["covered_sections"]

    assert set(manifest["gate_state"].values()) == {"blocked"}


def test_model_selection_keeps_preference_separate_from_result() -> None:
    config = _load("model_selection.yaml")

    assert config["status"] == "preregistered_not_run"
    assert config["decision_state"]["user_preference_prior"] == "deepseek-v4-pro"
    assert config["decision_state"]["selected_model"] is None
    assert {item["model_id"] for item in config["candidates"]} == {
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    }
    assert config["common_request_controls"]["thinking"]["requested"] == "enabled"
    assert (
        config["common_request_controls"]["reasoning_effort"][
            "emitted_by_current_argument_path"
        ]
        is True
    )
    assert (
        config["common_request_controls"]["reasoning_effort"]["effective_source"]
        == "explicit_request"
    )


def test_execution_state_accepts_ancestor_base_commit(monkeypatch) -> None:
    config = _load("model_selection.yaml")
    base_commit = config["execution_code_state"]["base_commit"]
    current_commit = "c" * 40
    monkeypatch.setattr(model_runner, "_git_commit", lambda: current_commit)
    monkeypatch.setattr(
        model_runner,
        "_git_commit_is_ancestor",
        lambda ancestor, descendant: (
            (ancestor, descendant) == (base_commit, current_commit)
        ),
    )

    result = model_runner.verify_model_execution_state(config)

    assert result["base_commit"] == base_commit
    assert result["current_commit"] == current_commit


def test_execution_state_rejects_unrelated_base_commit(monkeypatch) -> None:
    config = _load("model_selection.yaml")
    monkeypatch.setattr(model_runner, "_git_commit", lambda: "c" * 40)
    monkeypatch.setattr(model_runner, "_git_commit_is_ancestor", lambda *_: False)

    with pytest.raises(ValueError, match="not an ancestor"):
        model_runner.verify_model_execution_state(config)
    assert (
        config["common_request_controls"]["outbound_http_audit"][
            "records_actual_payload_retry_and_usage"
        ]
        is True
    )
    assert config["provider"]["cross_provider_fallback_allowed"] is False
    assert config["screen_design"]["total_invocations"] == 16
    assert config["common_request_controls"]["client_configured_max_tokens"] == 16384
    assert [
        workflow["maximum_production_llm_attempts"] for workflow in config["workflows"]
    ] == [2, 1]
    assert config["human_rating"]["paired_validity"]["minimum_common_valid_pairs"] == 7
    assert config["selection_rule"]["multi_model_screen_counts_as_g1"] is False
    assert config["gate_state"]["model_screen"] == "not_run"
    assert {config["gate_state"][gate] for gate in ("G1", "G2", "G3", "G4")} == {
        "blocked"
    }


def test_development_configs_do_not_persist_credentials() -> None:
    text = "\n".join(
        (DEVELOPMENT_ROOT / name).read_text(encoding="utf-8")
        for name in ("manifest.yaml", "model_selection.yaml")
    )

    assert "Bearer " not in text
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{12,}", text)
    assert "api_key:" not in text.lower()


def test_model_selection_preflight_is_deterministic_and_zero_network() -> None:
    manifest = _load("manifest.yaml")
    config = _load("model_selection.yaml")
    secret = "sk-preflight-secret-value"
    runtime_cloud = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": secret,
    }

    first_plan = build_run_plan(config)
    second_plan = build_run_plan(config)
    assert first_plan == second_plan
    assert len(first_plan["slots"]) == 16
    assert set(first_plan["counts"].values()) == {8}
    assert all("deepseek" not in slot["pair_id"] for slot in first_plan["slots"])
    model_mapping_bytes = json.dumps(
        first_plan["model_to_label"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    inverse_mapping_bytes = json.dumps(
        first_plan["label_to_model"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert (
        hashlib.sha256(model_mapping_bytes).hexdigest()
        == first_plan["blind_mapping_sha256"]
    )
    assert (
        hashlib.sha256(inverse_mapping_bytes).hexdigest()
        == first_plan["inverse_blind_mapping_sha256"]
    )

    report = build_preflight_report(
        manifest=manifest,
        model_config=config,
        runtime_cloud=runtime_cloud,
    )
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    assert report["network_calls"] == 0
    assert report["credential_present"] is True
    assert report["ready_for_paid_execution"] is False
    assert secret not in serialized
    assert report["run_plan"]["invocation_count"] == 16
    assert all(
        probe["thinking"] == {"type": "enabled"}
        and probe["reasoning_effort"] == "high"
        and probe["effective_initial_max_tokens"] == 16384
        for probe in report["request_control_probes"]
    )


def test_preflight_rejects_non_development_input_path() -> None:
    manifest = copy.deepcopy(_load("manifest.yaml"))
    manifest["papers"][0]["parsed_full_text"]["path"] = (
        "methods/reviewer_validation/inputs/held_out/forbidden.txt"
    )

    with pytest.raises(ValueError, match="development inputs only"):
        verify_development_inventory(manifest)


def test_paid_run_stops_before_writes_when_preflight_is_blocked() -> None:
    manifest = _load("manifest.yaml")
    config = _load("model_selection.yaml")
    runtime_cloud = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-preflight-secret-value",
    }
    report = build_preflight_report(
        manifest=manifest,
        model_config=config,
        runtime_cloud=runtime_cloud,
    )

    with pytest.raises(RuntimeError, match="paid execution blocked"):
        import asyncio

        asyncio.run(
            execute_paid_run(
                run_id="must-not-be-created",
                preflight=report,
                manifest=manifest,
                model_config=config,
                runtime_cloud=runtime_cloud,
            )
        )


def test_blind_package_removes_model_identity(tmp_path: Path) -> None:
    manifest = _load("manifest.yaml")
    config = _load("model_selection.yaml")
    run_root = tmp_path / "run"
    coordinator_root = tmp_path / "coordinator"
    run_root.mkdir()
    coordinator_root.mkdir()
    paper_id = manifest["papers"][0]["paper_id"]
    results = [
        {
            "slot": {
                "pair_id": "pair-01",
                "slot_id": "pair-01-m1",
                "blind_label": "M1",
                "model_id": "deepseek-v4-pro",
                "paper_id": paper_id,
                "workflow": "ledger_extraction",
                "repetition": 1,
            },
            "termination": "success",
            "valid": True,
            "pair_request_parity_pass": True,
            "excerpt": "A model-visible development excerpt.",
            "raw_response": "I am the V4 Pro model.",
            "parsed_output": {"note": "deepseek-v4-pro"},
        },
        {
            "slot": {
                "pair_id": "pair-01",
                "slot_id": "pair-01-m2",
                "blind_label": "M2",
                "model_id": "deepseek-v4-flash",
                "paper_id": paper_id,
                "workflow": "ledger_extraction",
                "repetition": 1,
            },
            "termination": "success",
            "valid": True,
            "pair_request_parity_pass": True,
            "excerpt": "A model-visible development excerpt.",
            "raw_response": "I am the DeepSeek Flash model.",
            "parsed_output": {"note": "deepseek-v4-flash"},
        },
    ]

    blind_index, audit = _materialize_blind_package(
        run_root=run_root,
        coordinator_root=coordinator_root,
        results=results,
        manifest=manifest,
        model_config=config,
    )

    blind_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (run_root / "blind").rglob("*")
        if path.is_file()
    ).lower()
    assert blind_index["pairs"][0]["eligible_for_rating"] is True
    assert sum(item["raw_identity_redactions"] for item in audit["records"]) == 2
    assert "deepseek-v4-pro" not in blind_text
    assert "deepseek-v4-flash" not in blind_text
    assert "deepseek-v4-pro-0813" not in blind_text
    assert "deepseek-v4-flash-0731" not in blind_text
    assert (run_root / "rating_forms" / "A" / "pair-01.json").is_file()
    assert (run_root / "rating_forms" / "B" / "pair-01.json").is_file()


def test_request_validator_rejects_drift_before_send() -> None:
    config = _load("model_selection.yaml")
    workflow = config["workflows"][0]
    slot = {"model_id": "deepseek-v4-pro"}
    event = {
        "event": "request_started",
        "sequence": 1,
        "payload": {
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "json prompt"}],
            "temperature": workflow["production_temperature"],
            "max_tokens": 16384,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        },
    }
    _validate_request_before_send(
        event,
        slot=slot,
        workflow=workflow,
        credential="secret-value",
    )
    drifted = copy.deepcopy(event)
    drifted["payload"]["temperature"] = 0.9
    with pytest.raises(RuntimeError, match="temperature"):
        _validate_request_before_send(
            drifted,
            slot=slot,
            workflow=workflow,
            credential="secret-value",
        )


def test_pair_request_parity_compares_complete_initial_payload(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir()
    base_payload = {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "same exact prompt"}],
        "temperature": 0.3,
        "max_tokens": 16384,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
    results = [
        {
            "slot": {"pair_id": "pair-01"},
            "initial_request_payload": base_payload,
        },
        {
            "slot": {"pair_id": "pair-01"},
            "initial_request_payload": {**base_payload, "model": "deepseek-v4-flash"},
        },
    ]
    passing = _audit_pair_request_parity(run_root=root, results=results)
    assert passing["all_pairs_pass"] is True

    second_root = tmp_path / "private-drifted"
    second_root.mkdir()
    results[1]["initial_request_payload"] = copy.deepcopy(
        results[1]["initial_request_payload"]
    )
    results[1]["initial_request_payload"]["messages"][0]["content"] = "drifted"
    failing = _audit_pair_request_parity(run_root=second_root, results=results)
    assert failing["all_pairs_pass"] is False


def test_preference_aggregation_is_deterministic() -> None:
    assert _aggregate_preference("M1", "M1") == "M1"
    assert _aggregate_preference("M1", "tie") == "M1"
    assert _aggregate_preference("M1", "M2") == "tie"


def test_separate_rating_locks_produce_one_mechanical_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_base = tmp_path / "public"
    private_base = tmp_path / "private"
    monkeypatch.setattr(model_runner, "MODEL_OUTPUT_ROOT", public_base)
    monkeypatch.setattr(model_runner, "MODEL_PRIVATE_ROOT", private_base)
    monkeypatch.setattr(Path, "chmod", lambda _self, _mode: None)
    run_id = "synthetic-lock-test"
    public_root = public_base / run_id
    private_root = private_base / run_id
    public_root.mkdir(parents=True)
    private_root.mkdir(parents=True)
    manifest = _load("manifest.yaml")
    config = _load("model_selection.yaml")
    paper_id = manifest["papers"][0]["paper_id"]
    results = []
    for index in range(1, 9):
        pair_id = f"pair-{index:02d}"
        for label, model_id in (
            ("M1", "deepseek-v4-pro"),
            ("M2", "deepseek-v4-flash"),
        ):
            results.append(
                {
                    "slot": {
                        "pair_id": pair_id,
                        "slot_id": f"{pair_id}-{label.lower()}",
                        "blind_label": label,
                        "model_id": model_id,
                        "paper_id": paper_id,
                        "workflow": "ledger_extraction",
                        "repetition": index,
                    },
                    "termination": "success",
                    "valid": True,
                    "pair_request_parity_pass": True,
                    "excerpt": f"Development excerpt {index}.",
                    "raw_response": f"Anonymous response {label} for pair {index}.",
                    "parsed_output": {"items": []},
                }
            )
    _materialize_blind_package(
        run_root=public_root,
        coordinator_root=private_root,
        results=results,
        manifest=manifest,
        model_config=config,
    )

    frozen_root = private_root / "frozen_inputs"
    frozen_root.mkdir()
    config_bytes = (DEVELOPMENT_ROOT / "model_selection.yaml").read_bytes()
    (frozen_root / "model_selection.yaml").write_bytes(config_bytes)
    frozen_manifest = {
        "model_selection": {
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
        }
    }
    (frozen_root / "development_manifest.yaml").write_text(
        yaml.safe_dump(frozen_manifest), encoding="utf-8"
    )
    model_to_label = {
        "deepseek-v4-pro": "M1",
        "deepseek-v4-flash": "M2",
    }
    label_to_model = {label: model for model, label in model_to_label.items()}
    mapping = {
        "model_to_label": model_to_label,
        "model_to_label_sha256": hashlib.sha256(
            json.dumps(model_to_label, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
        "label_to_model": label_to_model,
        "label_to_model_sha256": hashlib.sha256(
            json.dumps(label_to_model, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
    }
    (private_root / "blind_mapping.json").write_text(
        json.dumps(mapping), encoding="utf-8"
    )

    for rater in ("A", "B"):
        for form_path in (public_root / "rating_forms" / rater).glob("*.json"):
            form = json.loads(form_path.read_text(encoding="utf-8"))
            for dimension in config["human_rating"]["dimensions"]:
                form["ratings"]["M1"][dimension] = (
                    0 if dimension == "unsupported_or_invented_content" else 2
                )
                form["ratings"]["M2"][dimension] = 1
            form["pair_preference"] = "M1"
            form_path.write_text(
                json.dumps(form, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        model_runner.lock_ratings(run_id=run_id, rater_id=rater)

    result = model_runner.select_model_from_locked_ratings(run_id=run_id)
    assert result["status"] == "selected"
    assert result["selected_model"] == "deepseek-v4-pro"
    assert result["pairwise_wins"] == {"M1": 8, "M2": 0}


def test_full_run_orchestration_can_complete_with_offline_slot_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_base = tmp_path / "public"
    private_base = tmp_path / "private"
    ledger_base = tmp_path / "ledger"
    monkeypatch.setattr(model_runner, "MODEL_OUTPUT_ROOT", public_base)
    monkeypatch.setattr(model_runner, "MODEL_PRIVATE_ROOT", private_base)
    monkeypatch.setattr(model_runner, "LEDGER_OUTPUT_ROOT", ledger_base)
    manifest = _load("manifest.yaml")
    config = _load("model_selection.yaml")
    calls: list[str] = []

    async def fake_slot_executor(**kwargs):
        slot = kwargs["slot"]
        workflow = kwargs["workflow_by_id"][slot["workflow"]]
        calls.append(slot["slot_id"])
        response_model = (
            "DeepSeek-V4-Pro-0813"
            if slot["model_id"] == "deepseek-v4-pro"
            else "DeepSeek-V4-Flash-0731"
        )
        payload = {
            "model": slot["model_id"],
            "messages": [
                {"role": "user", "content": f"paired prompt {slot['pair_id']}"}
            ],
            "temperature": workflow["production_temperature"],
            "max_tokens": 16384,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        }
        model_runner._append_jsonl(
            kwargs["run_root"] / "coordinator" / "outbound_http_attempts.jsonl",
            {"slot_id": slot["slot_id"], "event": "offline_fixture"},
            root=kwargs["run_root"],
        )
        return {
            "slot": slot,
            "termination": "success",
            "valid": True,
            "excerpt": f"Shared excerpt {slot['pair_id']}.",
            "raw_response": f"Anonymous result for {slot['blind_label']}.",
            "parsed_output": {"items": []},
            "slot_record": {"path": f"{slot['slot_id']}.json"},
            "initial_request_payload": payload,
            "provider_reported_models": [response_model],
            "outbound_http_attempts": 1,
        }

    summary = asyncio.run(
        model_runner.execute_paid_run(
            run_id="offline-orchestration",
            preflight={
                "ready_for_paid_execution": True,
                "blockers": [],
                "execution_code_state": config["execution_code_state"],
            },
            manifest=manifest,
            model_config=config,
            runtime_cloud={"api_key": "sk-offline-not-used"},
            slot_executor=fake_slot_executor,
        )
    )

    assert len(calls) == 16
    assert summary["technically_eligible_for_blind_rating"] is True
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (public_base / "offline-orchestration").rglob("*")
        if path.is_file()
    ).lower()
    assert "deepseek-v4-pro" not in public_text
    assert "deepseek-v4-flash" not in public_text
    assert (private_base / "offline-orchestration" / "blind_mapping.json").is_file()
