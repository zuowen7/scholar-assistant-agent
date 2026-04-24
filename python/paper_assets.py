"""Built-in paper template metadata and scaffolding helpers."""

from __future__ import annotations

from typing import Any


TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "generic",
        "name": "Generic Academic Paper",
        "venue": "General",
        "description": "A standard academic paper structure.",
    },
    {
        "id": "ieee",
        "name": "IEEE Conference",
        "venue": "IEEE",
        "description": "IEEE-style conference paper sections.",
    },
    {
        "id": "neurips",
        "name": "NeurIPS",
        "venue": "NeurIPS",
        "description": "Machine learning conference paper scaffold.",
    },
]

DEFAULT_SECTIONS = ["abstract", "introduction", "related_work", "method", "experiment", "conclusion"]


def get_template_list() -> list[dict[str, Any]]:
    return TEMPLATES


def generate_scaffold(template_id: str = "generic", title: str = "", sections: list[str] | None = None) -> str:
    selected = next((item for item in TEMPLATES if item["id"] == template_id), TEMPLATES[0])
    title = title.strip() or "Untitled Paper"
    sections = sections or DEFAULT_SECTIONS

    lines = [
        f"# {title}",
        "",
        f"<!-- Template: {selected['name']} -->",
        "",
    ]
    for section in sections:
        heading = section.replace("_", " ").title()
        lines.extend([f"## {heading}", "", "TODO", ""])
    return "\n".join(lines).rstrip() + "\n"


def get_style_examples(template_id: str = "generic", section: str = "introduction") -> str:
    template = next((item for item in TEMPLATES if item["id"] == template_id), TEMPLATES[0])
    return (
        f"Template: {template['name']}\n"
        f"Section: {section}\n"
        "Use concise academic prose, explicit claims, clear transitions, and reproducible terminology."
    )


def ingest_paper_assets(rag_store: Any) -> dict[str, Any]:
    count = 0
    for template in TEMPLATES:
        text = (
            f"{template['name']}\n{template['description']}\n"
            "Recommended structure: Abstract, Introduction, Related Work, Method, Experiments, Conclusion."
        )
        count += rag_store.ingest_document(
            doc_id=f"template-{template['id']}",
            text=text,
            metadata={"title": template["name"], "template_name": template["id"], "category": "template"},
        )
    return {"ingested_chunks": count, "templates": len(TEMPLATES)}


def get_ingestion_status(rag_store: Any) -> dict[str, Any]:
    return {"chunk_count": rag_store.count_chunks(), "templates": len(TEMPLATES)}
