#!/usr/bin/env python
"""CI test quality gate — ensures edge/fault/property tests are not skipped.

This script runs at CI time and verifies:
1. Edge tests exist and pass
2. Fault injection tests exist and pass
3. Property-based tests exist and pass
4. Stress/concurrency tests exist and pass

Exit code 1 if any category is missing or fails.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "tests" / "unit"

CATEGORIES = {
    "edge": {
        "description": "Edge case tests (malformed input, boundary, extreme values)",
        "required": True,
    },
    "fault": {
        "description": "Fault injection tests (DB failure, corruption, race conditions)",
        "required": True,
    },
    "property": {
        "description": "Property-based tests (Hypothesis random input invariants)",
        "required": False,  # Optional until hypothesis is in requirements.txt
    },
    "stress": {
        "description": "Stress tests (concurrency, large payloads, resource limits)",
        "required": True,
    },
}


def find_files_with_marker(marker: str) -> list[Path]:
    """Find test files containing pytest.mark.<marker> in their pytestmark."""
    files = []
    for f in sorted(TEST_DIR.glob("test_*.py")):
        content = f.read_text(encoding="utf-8", errors="replace")
        # Handle both: pytestmark = pytest.mark.xxx and pytestmark = [pytest.mark.xxx, ...]
        if f"pytest.mark.{marker}" in content:
            files.append(f)
    return files


def run_category(marker: str) -> tuple[int, str]:
    """Run pytest for a specific marker. Returns (exit_code, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_DIR), "-m", marker,
         "-q", "--tb=line", "--no-header"],
        capture_output=True, text=True, timeout=600, cwd=str(ROOT),
    )
    return result.returncode, result.stdout.strip() + "\n" + result.stderr.strip()


def main() -> int:
    errors = []

    for marker, info in CATEGORIES.items():
        files = find_files_with_marker(marker)
        print(f"\n[{marker}] {info['description']}")
        print(f"  Files: {len(files)}")

        if not files:
            if info["required"]:
                errors.append(f"{marker}: NO test files found (required)")
                print(f"  FAIL: No test files with @pytest.mark.{marker}")
            else:
                print(f"  SKIP: No test files (optional)")
            continue

        exit_code, output = run_category(marker)
        if exit_code != 0:
            errors.append(f"{marker}: tests FAILED (exit {exit_code})")
            print(f"  FAIL:")
            for line in output.split("\n")[-10:]:
                print(f"    {line}")
        else:
            # Parse test count
            for line in output.split("\n"):
                if "passed" in line or "failed" in line:
                    print(f"  {line.strip()}")
                    break

    if errors:
        print(f"\n{'='*50}")
        print(f"TEST QUALITY GATE FAILED ({len(errors)} failures):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n{'='*50}")
    print("TEST QUALITY GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
