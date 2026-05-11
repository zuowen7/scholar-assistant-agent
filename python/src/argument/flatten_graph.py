"""Argument graph → draft document flattener (Phase 5).

Traverses a Toulmin ArgGraph and produces a structured academic draft.
No LLM calls — pure deterministic traversal. Reuses format helpers.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from .models_v2 import ArgGraph, ArgNode

logger = logging.getLogger(__name__)

# ── Relation type constants ───────────────────────────────────────────────────

_SUPPORTS  = "supports"
_WARRANTS  = "warrants"
_BACKS     = "backs"
_QUALIFIES = "qualifies"
_REBUTS    = "rebuts"
_COUNTERS  = "counters"

# ── Section building ──────────────────────────────────────────────────────────

def _node_map(graph: ArgGraph) -> dict[str, ArgNode]:
    return {n.id: n for n in graph.nodes}


def _incoming(graph: ArgGraph, target_id: str, relation: str) -> list[ArgNode]:
    """Return source nodes with the given relation pointing to target_id."""
    nmap = _node_map(graph)
    return [
        nmap[e.source_id]
        for e in graph.edges
        if e.target_id == target_id and e.relation_type == relation and e.source_id in nmap
    ]


def _outgoing(graph: ArgGraph, source_id: str, relation: str) -> list[ArgNode]:
    """Return target nodes for the given relation from source_id."""
    nmap = _node_map(graph)
    return [
        nmap[e.target_id]
        for e in graph.edges
        if e.source_id == source_id and e.relation_type == relation and e.target_id in nmap
    ]


def graph_to_sections(graph: ArgGraph) -> list[dict]:
    """Convert ArgGraph into a list of {title, body, node_ids} sections.

    Structure per claim:
      §N  Claim text (topic sentence) + grounds + warrant
      §N.Lim  Rebuttal(s) + counters (as limitations/objections)

    Returns a flat list of section dicts.
    """
    if not graph.nodes:
        return []

    claims = [n for n in graph.nodes if n.node_type == "claim"]
    if not claims:
        # No claims — just dump all nodes as a single section
        body = "\n\n".join(n.text for n in graph.nodes)
        return [{"title": "论证内容", "body": body, "node_ids": [n.id for n in graph.nodes]}]

    sections: list[dict] = []
    used_ids: set[str] = set()

    for claim in claims:
        # --- Main claim section ---
        parts: list[str] = [claim.text]
        node_ids: list[str] = [claim.id]
        used_ids.add(claim.id)

        # Grounds (evidence)
        grounds = _incoming(graph, claim.id, _SUPPORTS)
        if grounds:
            parts.append("**依据：**")
            for g in grounds:
                parts.append(f"- {g.text}")
                node_ids.append(g.id)
                used_ids.add(g.id)
                # Backing for this ground (treat as sub-evidence)
                for b in _incoming(graph, g.id, _BACKS):
                    parts.append(f"  - （支撑）{b.text}")
                    node_ids.append(b.id)
                    used_ids.add(b.id)

        # Warrants (reasoning bridges)
        warrants = _incoming(graph, claim.id, _WARRANTS)
        if warrants:
            parts.append("**论证保证：**")
            for w in warrants:
                parts.append(f"- {w.text}")
                node_ids.append(w.id)
                used_ids.add(w.id)
                # Backing for warrant
                for b in _incoming(graph, w.id, _BACKS):
                    parts.append(f"  - （支撑）{b.text}")
                    node_ids.append(b.id)
                    used_ids.add(b.id)

        # Qualifiers
        qualifiers = _incoming(graph, claim.id, _QUALIFIES)
        if qualifiers:
            qual_texts = "；".join(q.text for q in qualifiers)
            parts.append(f"**限定：** {qual_texts}")
            for q in qualifiers:
                node_ids.append(q.id)
                used_ids.add(q.id)

        sections.append({
            "title": claim.text[:60] + ("…" if len(claim.text) > 60 else ""),
            "body": "\n\n".join(parts),
            "node_ids": node_ids,
        })

        # --- Rebuttal sub-section for this claim ---
        rebuttals = _incoming(graph, claim.id, _REBUTS)
        if rebuttals:
            reb_parts: list[str] = []
            reb_ids: list[str] = []
            for r in rebuttals:
                if r.id in used_ids:
                    continue
                reb_parts.append(f"**反驳：** {r.text}")
                reb_ids.append(r.id)
                used_ids.add(r.id)
                # Counters to this rebuttal
                counters = _incoming(graph, r.id, _COUNTERS)
                for c in counters:
                    reb_parts.append(f"**回应：** {c.text}")
                    reb_ids.append(c.id)
                    used_ids.add(c.id)

            if reb_parts:
                sections.append({
                    "title": "局限性与反驳",
                    "body": "\n\n".join(reb_parts),
                    "node_ids": reb_ids,
                })

    # Orphan nodes not yet covered
    orphans = [n for n in graph.nodes if n.id not in used_ids]
    if orphans:
        body = "\n\n".join(n.text for n in orphans)
        sections.append({
            "title": "其他论证元素",
            "body": body,
            "node_ids": [n.id for n in orphans],
        })

    return sections


# ── Format helpers ─────────────────────────────────────────────────────────────

def _format_markdown(title: str, sections: list[dict]) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    for i, sec in enumerate(sections):
        heading_level = "##"
        parts.append(f"{heading_level} {sec['title']}\n\n{sec['body']}")
    return "\n\n".join(parts)


def _format_latex(title: str, sections: list[dict]) -> str:
    try:
        from pandoc_templates import convert_markdown
        md = _format_markdown(title, sections)
        result = convert_markdown(md, template_id="generic_article", output_format="tex",
                                  metadata={"title": title})
        if result.get("success") and result.get("tex"):
            return result["tex"]
    except Exception as exc:
        logger.debug("pandoc_templates unavailable: %s", exc)

    # Fallback: minimal LaTeX
    body_parts: list[str] = []
    for sec in sections:
        body_parts.append(f"\\section{{{sec['title']}}}\n\n{sec['body']}")
    body = "\n\n".join(body_parts)
    return (
        "\\documentclass{article}\n\\begin{document}\n"
        f"\\title{{{title}}}\n\\maketitle\n\n{body}\n\n\\end{{document}}\n"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def flatten_graph(
    graph: ArgGraph,
    template: str = "markdown",
    title: str = "",
) -> str:
    """Convert an ArgGraph into a draft document string.

    Args:
        graph:    The Toulmin argument graph.
        template: 'markdown' | 'latex' | 'docx' (docx produces markdown body
                  for subsequent pandoc conversion).
        title:    Optional document title.

    Returns:
        A string in the requested format.
    """
    sections = graph_to_sections(graph)

    if template == "latex":
        return _format_latex(title or "Draft", sections)
    # 'docx' and 'markdown' both produce markdown (docx needs pandoc separately)
    return _format_markdown(title, sections)


async def flatten_graph_stream(
    graph: ArgGraph,
    template: str = "markdown",
    title: str = "",
    output_dir: str | Path = ".",
) -> AsyncGenerator[dict, None]:
    """Async generator that yields SSE-style events and writes output file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    yield {"event": "progress", "data": json.dumps({"step": "building_sections"})}

    sections = graph_to_sections(graph)

    yield {
        "event": "progress",
        "data": json.dumps({"step": "formatting", "section_count": len(sections)}),
    }

    if template == "latex":
        content = _format_latex(title or "Draft", sections)
        ext = "tex"
    else:
        content = _format_markdown(title, sections)
        ext = "md"

    ts = str(int(time.time()))
    uid = uuid.uuid4().hex[:6]
    output_path = output_dir / f"argument_draft_{ts}_{uid}.{ext}"
    output_path.write_text(content, encoding="utf-8")

    yield {
        "event": "complete",
        "data": json.dumps({
            "output_path": str(output_path),
            "word_count": len(content),
            "section_count": len(sections),
            "template": template,
        }),
    }
