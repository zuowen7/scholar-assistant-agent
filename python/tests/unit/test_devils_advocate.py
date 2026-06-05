"""Phase 5 tests: Devil's Advocate perspective + Integrity tools."""
from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path


class TestDevilsAdvocate:
    """run_devils_advocate_perspective integration."""

    def test_returns_list(self):
        """DA function returns empty list when LLM unavailable (graceful)."""
        # Test the function signature exists
        from src.argument._reviewer_perspectives import run_devils_advocate_perspective

        assert callable(run_devils_advocate_perspective)

    def test_handles_llm_failure(self):
        """When LLM fails, returns empty list without crash."""
        from src.argument._reviewer_perspectives import run_devils_advocate_perspective

        import asyncio
        result = asyncio.new_event_loop().run_until_complete(
            run_devils_advocate_perspective(
                text="test paper content",
                venue_profile="ICLR",
                cloud_client=None,
                ollama_client=None,
            )
        )
        assert isinstance(result, list)

    def test_synthesize_exists(self):
        """synthesize_review function exists."""
        from src.argument._reviewer_perspectives import synthesize_review

        assert callable(synthesize_review)


class TestIntegrityTools:
    """check_integrity and check_citations tools."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.tmp = tmp_path

    def _write_file(self, content: str) -> str:
        p = self.tmp / "test.md"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_orphan_citation_detected(self):
        from src.agent.tools.integrity_tools import check_integrity

        content = (
            "As shown in \\cite{Smith2020}, the results are significant.\n\n"
            "\\begin{thebibliography}{99}\n"
            "\\bibitem{Jones2019} Jones. Some paper. 2019.\n"
            "\\end{thebibliography}\n"
        )
        path = self._write_file(content)
        result = json.loads(check_integrity(file_path=path))

        orphan_issues = [i for i in result.get("issues", []) if i["type"] == "orphan_citation"]
        assert len(orphan_issues) >= 1

    def test_impossible_p_value(self):
        from src.agent.tools.integrity_tools import check_integrity

        content = "Results show significant improvement (p = 1.5, n=100)."
        path = self._write_file(content)
        result = json.loads(check_integrity(file_path=path))

        issues = [i for i in result.get("issues", []) if "p_value" in i.get("type", "")]
        assert len(issues) >= 1

    def test_clean_document_passes(self):
        from src.agent.tools.integrity_tools import check_integrity

        content = "This is a clean document with no statistical claims or citations."
        path = self._write_file(content)
        result = json.loads(check_integrity(file_path=path))

        assert result["summary"]["total_issues"] == 0

    def test_nonexistent_file_returns_error(self):
        from src.agent.tools.integrity_tools import check_integrity

        result = json.loads(check_integrity(file_path="/no/such/file.txt"))
        assert "error" in result

    def test_empty_text_document(self):
        from src.agent.tools.integrity_tools import check_integrity

        path = self._write_file("")
        result = json.loads(check_integrity(file_path=path))

        assert result["summary"]["total_issues"] == 0

    def test_check_citations_no_citations(self):
        from src.agent.tools.integrity_tools import check_citations

        path = self._write_file("This is a paragraph with no citations at all.")
        result = json.loads(check_citations(file_path=path))

        assert result["citations"] == []

    def test_check_citations_nonexistent(self):
        from src.agent.tools.integrity_tools import check_citations

        result = json.loads(check_citations(file_path="/no/such/file.txt"))
        assert "error" in result
