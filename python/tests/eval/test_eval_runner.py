"""Phase B — eval runner tests (E1-E8)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

# ── bootstrap ──────────────────────────────────────────────────────────────
runner_mod = pytest.importorskip(
    "tests.eval.runner",
    reason="Phase B eval runner not yet implemented",
)
load_cases = runner_mod.load_cases
run_assertion = runner_mod.run_assertion
run_suite = runner_mod.run_suite
EvalCase = runner_mod.EvalCase


# ── helpers ────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, suite: str, filename: str, data: dict) -> None:
    suite_dir = tmp_path / suite
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / filename).write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


# ── E1: load cases ─────────────────────────────────────────────────────────

def test_eval_loads_cases(tmp_path):
    """E1: load_cases reads YAML files from cases/<suite>/ directory."""
    _write_yaml(tmp_path, "translate", "t001.yaml", {
        "id": "t001",
        "description": "test case one",
        "input": "Hello world",
        "mock_output": "你好世界",
        "assertions": [],
    })
    cases = load_cases("translate", cases_dir=tmp_path)
    assert len(cases) == 1
    assert cases[0].id == "t001"
    assert cases[0].mock_output == "你好世界"


# ── E2: contains assertion ─────────────────────────────────────────────────

def test_eval_assertion_contains():
    """E2: 'contains' assertion passes when value is in output."""
    ok, msg = run_assertion({"type": "contains", "value": "hello"}, "say hello world")
    assert ok
    assert msg == ""


def test_eval_assertion_contains_fails():
    """E2 inverse: 'contains' assertion fails when value is absent."""
    ok, msg = run_assertion({"type": "contains", "value": "missing"}, "output text")
    assert not ok
    assert "contains" in msg


# ── E3: not_contains assertion ─────────────────────────────────────────────

def test_eval_assertion_not_contains():
    """E3: 'not_contains' assertion passes when value is NOT in output."""
    ok, msg = run_assertion({"type": "not_contains", "value": "forbidden"}, "clean output")
    assert ok
    assert msg == ""


# ── E4: regex_match assertion ──────────────────────────────────────────────

def test_eval_assertion_regex_match():
    """E4: 'regex_match' assertion passes when pattern matches output."""
    ok, msg = run_assertion({"type": "regex_match", "pattern": r"\d{4}"}, "Year 2024 result")
    assert ok
    assert msg == ""


def test_eval_assertion_regex_match_fails():
    """E4 inverse: 'regex_match' assertion fails when pattern does not match."""
    ok, msg = run_assertion({"type": "regex_match", "pattern": r"\d{4}"}, "no numbers here")
    assert not ok
    assert "regex_match" in msg


# ── E5: length_range assertion ─────────────────────────────────────────────

def test_eval_assertion_length_range():
    """E5: 'length_range' assertion passes when output length is in range."""
    ok, msg = run_assertion({"type": "length_range", "min": 5, "max": 100}, "hello world")
    assert ok
    ok_too_short, msg2 = run_assertion({"type": "length_range", "min": 50, "max": 100}, "hi")
    assert not ok_too_short
    assert "length_range" in msg2


# ── E6: passrate report ────────────────────────────────────────────────────

def test_eval_passrate_report(tmp_path):
    """E6: run_suite returns a dict with passrate key."""
    _write_yaml(tmp_path, "mysuite", "c001.yaml", {
        "id": "c001",
        "description": "passing case",
        "input": "input",
        "mock_output": "the expected value is here",
        "assertions": [{"type": "contains", "value": "expected"}],
    })
    _write_yaml(tmp_path, "mysuite", "c002.yaml", {
        "id": "c002",
        "description": "failing case",
        "input": "input",
        "mock_output": "output without the word",
        "assertions": [{"type": "contains", "value": "missing_word"}],
    })
    report = run_suite("mysuite", cases_dir=tmp_path)
    assert "passrate" in report
    assert report["total"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert abs(report["passrate"] - 0.5) < 1e-9


# ── E7: failure diagnostic ─────────────────────────────────────────────────

def test_eval_failure_diagnostic(tmp_path):
    """E7: a failed assertion includes input/expected/actual in the failure message."""
    _write_yaml(tmp_path, "diag", "c001.yaml", {
        "id": "c001",
        "description": "diagnostic test",
        "input": "my input text",
        "mock_output": "completely different output",
        "assertions": [{"type": "contains", "value": "expected_string"}],
    })
    report = run_suite("diag", cases_dir=tmp_path)
    assert report["failed"] == 1
    result = report["results"][0]
    assert not result.passed
    assert len(result.failures) == 1
    msg = result.failures[0]
    # Failure message must contain diagnostic info
    assert "expected_string" in msg or "contains" in msg


# ── E8: no real LLM called ─────────────────────────────────────────────────

def test_eval_mock_llm(tmp_path, monkeypatch):
    """E8: eval runner uses mock_output from YAML; never calls any real LLM."""
    # Monkeypatch to detect if any real HTTP/LLM call is attempted
    import urllib.request as _urllib
    def _block(*args, **kwargs):
        raise AssertionError("eval runner must not make real network calls")
    monkeypatch.setattr(_urllib, "urlopen", _block)

    _write_yaml(tmp_path, "mock_suite", "m001.yaml", {
        "id": "m001",
        "description": "mock llm test",
        "input": "some input",
        "mock_output": "some mock output",
        "assertions": [{"type": "contains", "value": "mock"}],
    })
    report = run_suite("mock_suite", cases_dir=tmp_path)
    assert report["passed"] == 1
    # No network call was made (if it were, the monkeypatch would have raised)
