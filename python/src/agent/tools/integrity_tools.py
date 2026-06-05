"""Integrity check tools for Agent: citation hallucination + statistical anomaly detection.

These are deterministic tools (no LLM calls) that detect common issues in
academic documents: orphan citations, impossible p-values, fake DOI formats.
"""
from __future__ import annotations

import json as _json
import re as _re
from pathlib import Path

from src.agent.tools.core import tool


@tool
def check_integrity(file_path: str, checks: str = "all") -> str:
    """对文档进行完整性检查。检测虚构引用、统计声明异常、参考文献一致性等问题。

    Args:
        file_path: 待检查的文档路径。
        checks: 检查类型，可选 all（全部）、citations（引用）、statistics（统计）、references（参考文献一致性）。
    """
    path = Path(file_path) if file_path else None
    if not path or not path.exists():
        return _json.dumps({"error": f"file not found: {file_path}"}, ensure_ascii=False)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return _json.dumps({"error": f"read failed: {e}"}, ensure_ascii=False)

    results: dict = {"issues": [], "summary": {}}

    if checks in ("all", "citations"):
        citation_issues = _check_citation_consistency(text)
        results["issues"].extend(citation_issues)
        results["summary"]["citation_issues"] = len(citation_issues)

    if checks in ("all", "statistics"):
        stat_issues = _check_statistical_claims(text)
        results["issues"].extend(stat_issues)
        results["summary"]["stat_issues"] = len(stat_issues)

    if checks in ("all", "references"):
        ref_issues = _check_reference_format(text)
        results["issues"].extend(ref_issues)
        results["summary"]["ref_issues"] = len(ref_issues)

    results["summary"]["total_issues"] = len(results["issues"])
    return _json.dumps(results, ensure_ascii=False, indent=2)


def _check_citation_consistency(text: str) -> list[dict]:
    """Detect citations without matching bibliography entries."""
    issues: list[dict] = []

    # Extract \cite{KEY} patterns
    cite_keys: set[str] = set(_re.findall(r"\\cite\{([^}]+)\}", text))

    # Extract bib items
    bib_start = text.find("\\begin{thebibliography}")
    if bib_start >= 0:
        bib_section = text[bib_start:]
        for key in cite_keys:
            if f"\\bibitem{{{key}}}" not in bib_section and f"\\bibitem{{{key}" not in bib_section:
                issues.append({
                    "type": "orphan_citation",
                    "detail": f"Citation key '{key}' has no matching \\bibitem",
                })
    elif cite_keys:
        # No bibliography found but has citations
        issues.append({
            "type": "missing_bibliography",
            "detail": f"Found {len(cite_keys)} citations but no bibliography section",
        })

    return issues


def _check_statistical_claims(text: str) -> list[dict]:
    """Detect impossible statistical claims."""
    issues: list[dict] = []

    # p-value: p < X, p = X, p > X
    p_val_patterns = _re.findall(r"p\s*[<>=]\s*(\d+\.?\d*(?:[eE][+-]?\d+)?)", text)
    for p_str in p_val_patterns:
        try:
            p_val = float(p_str)
            if p_val < 0 or p_val > 1:
                issues.append({
                    "type": "impossible_p_value",
                    "detail": f"p value {p_val} is outside [0, 1]",
                })
        except ValueError:
            pass

    # Percentage > 100% or < 0%
    pct_patterns = _re.findall(r"(\d+\.?\d*(?:[eE][+-]?\d+)?)\s*%", text)
    for p_str in pct_patterns:
        try:
            pct = float(p_str)
            if pct < 0:
                issues.append({
                    "type": "negative_percentage",
                    "detail": f"Percentage {pct}% is negative",
                })
            elif pct > 200:
                issues.append({
                    "type": "suspicious_percentage",
                    "detail": f"Percentage {pct}% exceeds reasonable maximum",
                })
        except ValueError:
            pass

    # Confidence interval with inverted bounds
    ci_patterns = _re.findall(r"(\d+\.?\d*(?:[eE][+-]?\d+)?)\s*[,;]\s*(\d+\.?\d*(?:[eE][+-]?\d+)?)", text)
    for a, b in ci_patterns:
        try:
            if float(a) > float(b):
                issues.append({
                    "type": "inverted_ci",
                    "detail": f"Confidence interval [{a}, {b}] has inverted bounds",
                })
        except ValueError:
            pass

    return issues


def _check_reference_format(text: str) -> list[dict]:
    """Detect suspicious reference formats."""
    issues: list[dict] = []

    # Fake DOI format: random hex strings
    fake_doi_pattern = _re.findall(r"10\.\d{4}/[a-f0-9]{64}", text)
    for doi in fake_doi_pattern:
        issues.append({
            "type": "suspicious_doi",
            "detail": f"DOI {doi[:50]}... looks like a random hex string (likely hallucinated)",
        })

    # Multiple arXiv IDs with sequential numbers (common hallucination pattern)
    arxiv_ids = _re.findall(r"arXiv:(\d{4}\.\d{5})", text)
    if len(arxiv_ids) >= 5:
        # Check if they're sequential
        try:
            sorted_ids = sorted(arxiv_ids)
            is_sequential = all(
                abs(float(sorted_ids[i]) - float(sorted_ids[i + 1])) < 0.001
                for i in range(len(sorted_ids) - 1)
            )
            if is_sequential:
                issues.append({
                    "type": "sequential_arxiv_ids",
                    "detail": f"Found {len(arxiv_ids)} nearly-identical arXiv IDs (possible hallucination)",
                })
        except ValueError:
            pass

    return issues


@tool
def check_citations(file_path: str, max_citations: int = 20) -> str:
    """检查文档中引用与声明的对齐情况。分析每个引用的上下文，判断支持程度。

    Args:
        file_path: 待检查的文档路径。
        max_citations: 最多检查的引用数量，默认 20。
    """
    path = Path(file_path) if file_path else None
    if not path or not path.exists():
        return _json.dumps({"error": f"file not found: {file_path}"}, ensure_ascii=False)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return _json.dumps({"error": f"read failed: {e}"}, ensure_ascii=False)

    # Extract citation contexts
    citation_contexts = _re.findall(
        r"([^.]*\\(?:cite|citep|citep|citealp)\{[^}]+\}[^.]*\.)",
        text,
    )
    if not citation_contexts:
        return _json.dumps({"citations": [], "source": "no citations found in document"}, ensure_ascii=False)

    results = []
    for ctx in citation_contexts[:max_citations]:
        cite_keys = _re.findall(r"\\(?:cite|citep|citep|citealp)\{([^}]+)\}", ctx)
        results.append({
            "context": ctx.strip()[:200],
            "cite_keys": cite_keys,
            "support_level": "needs_llm_verification",
        })

    return _json.dumps({"citations": results, "total": len(citation_contexts)}, ensure_ascii=False, indent=2)
