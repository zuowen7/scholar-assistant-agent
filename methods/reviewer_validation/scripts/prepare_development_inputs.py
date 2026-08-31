"""Regenerate development-only parsed text and production excerpts.

Raw PDFs are acquired separately and remain ignored. This command never reads
held-out inputs and never invokes an LLM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
DEVELOPMENT_ROOT = (
    REPO_ROOT / "methods" / "reviewer_validation" / "inputs" / "development"
)
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from src.argument.ledger import (  # noqa: E402
    prepare_ledger_classification,
    prepare_ledger_extraction,
)
from src.argument.section_utils import build_section_excerpt_envelope  # noqa: E402
from src.parser.extractor import extract_pages  # noqa: E402

PAPERS = {
    "dev-chi26-agency-science-journalism": "dev-chi26-agency-science-journalism.pdf",
    "dev-icml25-isolated-causal-effects": "dev-icml25-isolated-causal-effects.pdf",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_derived(path: Path, text: str, *, replace: bool) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if replace else "x"
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    return path.read_bytes()


def _excerpt_record(path: Path, excerpt: Any, data: bytes) -> dict[str, Any]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256(data),
        "byte_length": len(data),
        "character_length": len(excerpt.text),
        "source_sha256": excerpt.source_hash,
        "source_characters": excerpt.original_chars,
        "covered_sections": list(excerpt.covered_sections),
        "truncated": excerpt.truncated,
    }


def prepare(*, replace: bool) -> dict[str, Any]:
    raw_root = DEVELOPMENT_ROOT / "raw"
    parsed_root = DEVELOPMENT_ROOT / "parsed"
    excerpt_root = DEVELOPMENT_ROOT / "excerpts"
    report: dict[str, Any] = {
        "schema_version": "reviewer-validation-development-preparation/v1",
        "development_only": True,
        "llm_invoked": False,
        "papers": {},
    }

    for paper_id, filename in PAPERS.items():
        raw_path = raw_root / filename
        if not raw_path.is_file():
            raise FileNotFoundError(f"missing development PDF: {raw_path}")
        raw_data = raw_path.read_bytes()
        document = extract_pages(raw_path)
        full_text = document.full_text

        parsed_path = parsed_root / f"{paper_id}.txt"
        parsed_data = _write_derived(parsed_path, full_text, replace=replace)

        requests = {
            "ledger_extraction": prepare_ledger_extraction(full_text).excerpt,
            # Gold promises change the prompt but not the production body excerpt.
            "ledger_gold_conditioned_status": prepare_ledger_classification(
                full_text, []
            ).excerpt,
            "reviewer_venue": build_section_excerpt_envelope(
                full_text, max_chars=24000
            ),
        }
        excerpt_records: dict[str, Any] = {}
        for purpose, excerpt in requests.items():
            excerpt_path = excerpt_root / f"{paper_id}.{purpose}.txt"
            excerpt_data = _write_derived(excerpt_path, excerpt.text, replace=replace)
            excerpt_records[purpose] = _excerpt_record(
                excerpt_path, excerpt, excerpt_data
            )

        report["papers"][paper_id] = {
            "raw_pdf": {
                "path": raw_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(raw_data),
                "byte_length": len(raw_data),
            },
            "parsed_full_text": {
                "path": parsed_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(parsed_data),
                "byte_length": len(parsed_data),
                "character_length": len(full_text),
                "page_count": document.page_count,
                "nonempty_pages": sum(
                    bool(page.text.strip()) for page in document.pages
                ),
                "dual_column_pages": sum(
                    page.is_dual_column for page in document.pages
                ),
                "replacement_characters": full_text.count("\ufffd"),
            },
            "production_excerpts": excerpt_records,
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--replace-derived",
        action="store_true",
        help="replace ignored parsed/excerpt outputs from an earlier development iteration",
    )
    args = parser.parse_args()
    report = prepare(replace=args.replace_derived)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
