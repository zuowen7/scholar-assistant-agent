"""Eval runner — loads YAML test cases and runs assertions against mock LLM output."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_CASES_DIR = Path(__file__).parent / "cases"


@dataclass
class EvalCase:
    id: str
    description: str
    input: str
    mock_output: str
    assertions: list[dict] = field(default_factory=list)
    suite: str = ""


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    input: str = ""
    mock_output: str = ""


def load_cases(suite: str, cases_dir: Path | None = None) -> list[EvalCase]:
    """Load all YAML case files from cases/<suite>/ directory."""
    base = cases_dir if cases_dir is not None else _CASES_DIR
    suite_dir = base / suite
    if not suite_dir.exists():
        return []
    cases = []
    for yaml_path in sorted(suite_dir.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        cases.append(EvalCase(
            id=data.get("id", yaml_path.stem),
            description=data.get("description", ""),
            input=data.get("input", ""),
            mock_output=data.get("mock_output", ""),
            assertions=data.get("assertions", []),
            suite=data.get("suite", suite),
        ))
    return cases


def run_assertion(assertion: dict, output: str, input_text: str = "") -> tuple[bool, str]:
    """Run a single assertion on the mock output.

    Returns (passed, failure_message). failure_message is empty string if passed.
    """
    atype = assertion.get("type", "")

    if atype == "contains":
        value = assertion.get("value", "")
        if value in output:
            return True, ""
        return False, (
            f"[contains] expected {value!r} in output\n"
            f"  input:    {input_text!r}\n"
            f"  expected: contains {value!r}\n"
            f"  actual:   {output!r}"
        )

    elif atype == "not_contains":
        value = assertion.get("value", "")
        if value not in output:
            return True, ""
        return False, (
            f"[not_contains] expected {value!r} NOT in output\n"
            f"  input:    {input_text!r}\n"
            f"  expected: does not contain {value!r}\n"
            f"  actual:   {output!r}"
        )

    elif atype == "regex_match":
        pattern = assertion.get("pattern", "")
        if re.search(pattern, output):
            return True, ""
        return False, (
            f"[regex_match] pattern {pattern!r} did not match output\n"
            f"  input:    {input_text!r}\n"
            f"  expected: matches /{pattern}/\n"
            f"  actual:   {output!r}"
        )

    elif atype == "length_range":
        min_len = assertion.get("min", 0)
        max_len = assertion.get("max", math.inf)
        actual_len = len(output)
        if min_len <= actual_len <= max_len:
            return True, ""
        return False, (
            f"[length_range] output length {actual_len} not in [{min_len}, {max_len}]\n"
            f"  input:    {input_text!r}\n"
            f"  expected: length between {min_len} and {max_len}\n"
            f"  actual:   len={actual_len}, output={output!r}"
        )

    else:
        return False, f"[unknown assertion type] {atype!r}"


def run_suite(suite: str, cases_dir: Path | None = None) -> dict[str, Any]:
    """Run all cases in a suite and return a report dict."""
    cases = load_cases(suite, cases_dir)
    results = []
    passed_count = 0

    for case in cases:
        # Use mock_output as the "LLM response" — no real LLM call
        output = case.mock_output
        failures = []
        for assertion in case.assertions:
            ok, msg = run_assertion(assertion, output, case.input)
            if not ok:
                failures.append(msg)
        passed = len(failures) == 0
        if passed:
            passed_count += 1
        results.append(EvalResult(
            case_id=case.id,
            passed=passed,
            failures=failures,
            input=case.input,
            mock_output=output,
        ))

    total = len(cases)
    passrate = (passed_count / total) if total > 0 else 0.0
    return {
        "suite": suite,
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "passrate": passrate,
        "results": results,
    }
