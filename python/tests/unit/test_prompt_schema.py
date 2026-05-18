"""Phase B — 6-layer prompt schema tests (B1-B10)."""
import textwrap
import pytest
from pathlib import Path

# ── import under test ──────────────────────────────────────────────────────
schema_mod = pytest.importorskip(
    "src.prompts.schema",
    reason="Phase B GREEN not yet implemented",
)
PromptSpec = schema_mod.PromptSpec
PromptSchemaError = schema_mod.PromptSchemaError

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# ── helpers ────────────────────────────────────────────────────────────────
def _make_frontmatter(**overrides) -> str:
    """Build a minimal valid frontmatter + body."""
    data = {
        "role": "You are a test assistant.",
        "task": "Do a test task.",
        "constraints": ["At most 3 output sentences."],
        "format": "Plain text.",
        "examples": [],
        "fallback": "If input is empty, return 'No input provided.'",
    }
    data.update(overrides)
    lines = ["---"]
    for k, v in data.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - \"{item}\"")
        else:
            lines.append(f'{k}: "{v}"')
    lines += ["---", "", "Body content."]
    return "\n".join(lines)

# ── B1: each missing required layer raises PromptSchemaError ──────────────
@pytest.mark.parametrize("missing_layer", ["role", "task", "constraints", "format", "fallback"])
def test_schema_six_layers_required(missing_layer):
    """B1: missing any required layer must raise PromptSchemaError."""
    content = _make_frontmatter(**{missing_layer: None})
    # YAML null value → missing layer
    with pytest.raises(PromptSchemaError, match=missing_layer):
        PromptSpec.from_yaml_frontmatter(content)

def test_schema_no_frontmatter_raises():
    """B1 extra: no frontmatter block at all raises PromptSchemaError."""
    with pytest.raises(PromptSchemaError):
        PromptSpec.from_yaml_frontmatter("Just plain text, no --- markers.")

# ── B2-B7: each task prompt file passes schema ────────────────────────────
@pytest.mark.parametrize("rel_path", [
    "tasks_polish/academic_polish.md",
    "tasks_expand/grounded_expand.md",
    "tasks_coherence/coherence_rewrite.md",
    "tasks_edit/edit_with_text.md",
    "tasks_edit/edit_without_text.md",
    "tasks_compliance/compliance_check.md",
])
def test_task_prompt_passes_schema(rel_path):
    """B2-B7: all task prompt files must have valid 6-layer frontmatter."""
    path = PROMPTS_DIR / rel_path
    assert path.exists(), f"Prompt file not found: {path}"
    text = path.read_text(encoding="utf-8")
    spec = PromptSpec.from_yaml_frontmatter(text)  # must not raise
    assert spec.role
    assert spec.task
    assert len(spec.constraints) >= 1

# ── B8: role layer includes persona ───────────────────────────────────────
@pytest.mark.parametrize("rel_path", [
    "tasks_polish/academic_polish.md",
    "tasks_expand/grounded_expand.md",
    "tasks_coherence/coherence_rewrite.md",
    "tasks_edit/edit_with_text.md",
    "tasks_edit/edit_without_text.md",
    "tasks_compliance/compliance_check.md",
])
def test_role_layer_includes_persona(rel_path):
    """B8: role layer must start with 'You are'."""
    path = PROMPTS_DIR / rel_path
    text = path.read_text(encoding="utf-8")
    spec = PromptSpec.from_yaml_frontmatter(text)
    assert spec.role.strip().startswith("You are"), (
        f"role in {rel_path} must start with 'You are', got: {spec.role[:60]!r}"
    )

# ── B9: constraints layer quantified ──────────────────────────────────────
import re as _re

@pytest.mark.parametrize("rel_path", [
    "tasks_polish/academic_polish.md",
    "tasks_expand/grounded_expand.md",
])
def test_constraints_layer_quantified(rel_path):
    """B9: at least 1 constraint must contain a number."""
    path = PROMPTS_DIR / rel_path
    text = path.read_text(encoding="utf-8")
    spec = PromptSpec.from_yaml_frontmatter(text)
    has_number = any(_re.search(r"\d", c) for c in spec.constraints)
    assert has_number, (
        f"constraints in {rel_path} must include at least 1 quantified constraint; "
        f"got: {spec.constraints}"
    )

# ── B10: fallback layer handles empty input ───────────────────────────────
@pytest.mark.parametrize("rel_path", [
    "tasks_polish/academic_polish.md",
    "tasks_edit/edit_with_text.md",
])
def test_fallback_layer_handles_empty_input(rel_path):
    """B10: fallback must mention empty or short input handling."""
    path = PROMPTS_DIR / rel_path
    text = path.read_text(encoding="utf-8")
    spec = PromptSpec.from_yaml_frontmatter(text)
    assert _re.search(r"empty|fewer than|no input|short|blank", spec.fallback, _re.IGNORECASE), (
        f"fallback in {rel_path} must describe empty-input handling, got: {spec.fallback!r}"
    )
