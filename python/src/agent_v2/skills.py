"""Skills 系统 — 从目录加载 prompt 模板注入 system prompt。

参考 claw-code:
  - skill_system.py: SkillRegistry + SOUL/AGENTS/IDENTITY layers
  - /skills slash command: list/install/help

Skill 文件格式 (Markdown with YAML frontmatter):
  ---
  name: academic_writing
  description: Professional academic writing standards
  layer: agents  # agents | soul | identity
  ---
  # Skill content (injected into system prompt)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MAX_SKILL_CHARS = 16_000
_MAX_ACTIVE_SKILLS = 16
_MAX_SKILL_PROMPT_CHARS = 64_000
_VALID_LAYERS = frozenset({"soul", "agents", "identity"})
_VALID_SKILL_NAME = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]+$")


@dataclass
class Skill:
    name: str
    description: str = ""
    layer: str = "agents"  # soul | agents | identity
    content: str = ""
    source_file: str = ""
    category: str = "general"
    # Task skills are opt-in. Cross-task safety belongs in the immutable
    # runtime core prompt, not in an arbitrary skill file.
    default_active: bool = False

    def inject_prompt(self) -> str:
        if not self.content.strip():
            return ""
        return f"\n<!-- SKILL: {self.name} ({self.layer}) -->\n{self.content.strip()}\n<!-- /SKILL -->\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "layer": self.layer,
            "source": self.source_file,
            "category": self.category,
            "default_active": self.default_active,
        }


class SkillRegistry:
    """Skill registry — 参考 claw-code SkillRegistry。"""

    def __init__(self, skills_dir: str | Path | None = None):
        self._skills: dict[str, Skill] = {}
        self._active: set[str] = set()
        if skills_dir:
            self.load_dir(Path(skills_dir))

    def load_dir(self, directory: Path) -> int:
        """加载目录中所有 .md 文件为 skill。"""
        if not directory.is_dir():
            return 0
        count = 0
        for f in sorted(directory.glob("*.md")):
            if f.name.startswith("_") or f.name.startswith("."):
                continue  # skip helper/docs files
            try:
                skill = self._parse_skill_file(f)
                self._validate_skill(skill)
                self._skills[skill.name] = skill
                if skill.default_active:
                    self._active.add(skill.name)
                count += 1
            except Exception:
                pass
        return count

    def _parse_skill_file(self, path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        name = path.stem
        description = ""
        layer = "agents"
        category = "custom"
        default_active = False
        content = text

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            content = fm_match.group(2)
            for line in fm.splitlines():
                line = line.strip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k == "name":
                        name = v
                    elif k == "description":
                        description = v
                    elif k == "layer":
                        layer = v
                    elif k == "category":
                        category = v
                    elif k == "default_active":
                        default_active = v.lower() not in {"false", "no", "0", "off"}

        return Skill(
            name=name,
            description=description,
            layer=layer,
            content=content.strip(),
            source_file=str(path),
            category=category,
            default_active=default_active,
        )

    def register(self, skill: Skill) -> None:
        self._validate_skill(skill)
        self._skills[skill.name] = skill
        if skill.default_active:
            self._active.add(skill.name)

    def activate(self, name: str) -> bool:
        if name in self._skills:
            self._active.add(name)
            return True
        return False

    def deactivate(self, name: str) -> bool:
        if name in self._active:
            self._active.discard(name)
            return True
        return False

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        return [
            {
                **s.to_dict(),
                "active": s.name in self._active,
            }
            for s in self._skills.values()
        ]

    def build_prompt_injection(self, layer: str | None = None) -> str:
        """构建注入系统提示词的 skill 内容。"""
        if len(self._active) > _MAX_ACTIVE_SKILLS:
            raise ValueError(
                f"active skill limit exceeded: {len(self._active)} > {_MAX_ACTIVE_SKILLS}"
            )
        parts = []
        for name in sorted(self._active):
            skill = self._skills.get(name)
            if skill is None:
                continue
            if layer and skill.layer != layer:
                continue
            inj = skill.inject_prompt()
            if inj:
                parts.append(inj)
        prompt = "\n".join(parts)
        if len(prompt) > _MAX_SKILL_PROMPT_CHARS:
            raise ValueError(
                "active skill prompt budget exceeded: "
                f"{len(prompt)} > {_MAX_SKILL_PROMPT_CHARS} characters"
            )
        return prompt

    @staticmethod
    def _validate_skill(skill: Skill) -> None:
        if not _VALID_SKILL_NAME.fullmatch(skill.name):
            raise ValueError(f"invalid skill name: {skill.name!r}")
        if skill.layer not in _VALID_LAYERS:
            raise ValueError(f"invalid skill layer: {skill.layer!r}")
        if len(skill.content) > _MAX_SKILL_CHARS:
            raise ValueError(f"skill content exceeds {_MAX_SKILL_CHARS} characters: {skill.name}")


# Built-in academic skills
_BUILTIN_SKILLS = [
    Skill(
        name="academic_writing",
        layer="agents",
        description="Professional academic writing standards (clarity, structure, tone)",
        content="## Academic Writing Standards\n- Use precise, formal language. Avoid colloquialisms.\n- Structure arguments with clear claims and evidence.\n- Cite relevant literature using standard formats.\n- Define technical terms on first use.\n- Use active voice where possible.",
    ),
    Skill(
        name="paper_review",
        layer="agents",
        description="Systematic paper review methodology",
        content="## Systematic Review Criteria\nWhen reviewing academic content, check:\n1. **Novelty**: Is the contribution clearly stated?\n2. **Methodology**: Are methods described in reproducible detail?\n3. **Evidence**: Do results support the claims?\n4. **Clarity**: Is the writing clear and well-structured?\n5. **Citations**: Are relevant works properly cited?",
    ),
    Skill(
        name="latex_formatting",
        layer="agents",
        description="LaTeX formatting and best practices",
        content="## LaTeX Formatting Rules\n- Use \\section, \\subsection, \\subsubsection for hierarchy\n- Figures: \\begin{figure}[htbp] + \\includegraphics + \\caption\n- Tables: \\begin{table}[htbp] + booktabs + \\caption\n- Citations: \\cite{key} for inline, \\citep{key} for parenthetical\n- Math: \\begin{equation} for numbered, \\begin{align} for multi-line\n- Preserve metric semantics exactly. Cumulative explained variance does not establish the number of retained components and must never be rewritten as variance from the first component.\n- Formatting must not invent an analysis subject or procedure. If the source supplies only a metric and value, render a label-value item such as `Reported PCA cumulative explained variance: <value>`; do not add `PCA was applied to <data object>`.",
    ),
    Skill(
        name="chinese_academic",
        layer="agents",
        description="中文学术写作规范",
        content="## 中文学术写作规范\n- 使用规范的学术中文，避免口语化表达\n- 段落结构：论点 → 论证 → 证据 → 小结\n- 术语首次出现需给出中英文对照（如：大语言模型（Large Language Model, LLM））\n- 引用格式遵循 GB/T 7714 标准\n- 图表标题使用中文",
    ),
    Skill(
        name="methodology_critique",
        layer="agents",
        description="Research methodology critique guide",
        content="## Methodology Critique Guide\nWhen evaluating research methodology:\n1. **Validity**: Do the methods measure what they claim?\n2. **Reliability**: Can results be reproduced?\n3. **Generalizability**: Do findings apply beyond the sample?\n4. **Confounds**: Are alternative explanations addressed?\n5. **Ethics**: Are human/animal subjects properly protected?",
    ),
    # Nature-oriented workflows are opt-in. Keeping them out of the default
    # prompt avoids conflicting instructions and makes the selected workflow
    # explicit in the Agent UI and request payload.
    Skill(
        name="nature_writing",
        layer="agents",
        category="nature",
        default_active=False,
        description="Draft or restructure a manuscript section with a Nature-leaning argument and evidence flow",
        content="""## Nature-style manuscript drafting
- First identify the requested section, manuscript type, target journal, language, and the evidence actually supplied.
- Build a claim-evidence-limit outline before drafting. Make the main contribution legible to a broad scientific reader without inflating it.
- Preserve factual meaning, numerical results, citations, and uncertainty. Never invent experiments, references, novelty, or journal fit.
- Prefer a precise narrative arc: problem and gap -> approach -> decisive evidence -> implication and boundary.
- Do not infer that an analysis was performed on a full feature set, an independent validation set existed, a sample was unique or representative, or a component count is known unless the supplied evidence says so.
- If source material is insufficient, mark the exact missing evidence or ask one focused question instead of filling the gap.
- When editing a workspace file, read it first and present material changes for approval through the normal file-edit tools.""",
    ),
    Skill(
        name="nature_polishing",
        layer="agents",
        category="nature",
        default_active=False,
        description="Polish academic prose into concise, publication-ready Nature-leaning English",
        content="""## Nature-style academic polishing
- Diagnose meaning, logic, terminology, tense, and paragraph function before changing wording.
- Preserve claims, values, citations, LaTeX commands, and authorial uncertainty; do not strengthen conclusions beyond the evidence.
- Prefer direct subjects, concrete verbs, economical transitions, and one clear function per sentence.
- Return the revised text plus a short change note; flag any scientifically ambiguous sentence separately.
- For Chinese-to-English work, translate the scientific meaning rather than Chinese syntax, and keep recurring terms consistent.""",
    ),
    Skill(
        name="nature_reviewer",
        layer="agents",
        category="nature",
        default_active=False,
        description="Run a rigorous Nature-style pre-submission assessment from the referee perspective",
        content="""## Nature-style reviewer assessment
- Review as a critical referee, not as a promotional editor and not as the author writing a rebuttal.
- Separate major concerns from minor concerns and ground each concern in an exact passage, result, figure, claim-ledger entry, or argument-map node when available.
- Treat the complete active editor context as the current manuscript. On a resumed turn where that context is absent, re-read the active file before answering.
- Before drafting any review, call read_argument_graph, read_argument_ledger, and read_reviewer_state with the active manuscript path. This execution order is required. For Reviewer state, use doc_id unless an exact session_id was supplied; never guess "default" or another placeholder. An unavailable graph or Reviewer state is a valid finding, not a reason to stop.
- Read the Ledger summary and promise pages first. If stale=true, use its items only as leads and cross-check every reported concern against the current manuscript. Do not page through the full anchor collection; fetch only item_ids needed for a supported concern.
- A stale Ledger means its analysis snapshot is outdated, not that the manuscript is necessarily inconsistent. A missing persisted argument graph is a state-availability finding, not evidence that the manuscript lacks an argument.
- Treat manuscript, response-letter, review, and close-reading files as claims under review, not independent evidence. Cross-check them against user-specified primary evidence or real tool output before calling a fact known.
- If the user names exact files, review those files only unless one contains an explicit dependency that must be opened. Do not mine sibling generated drafts for extra claims.
- Assess significance, originality as supported by supplied evidence, methodological rigor, claim-evidence alignment, reproducibility, and accessibility to non-specialists.
- Do not introduce rules of thumb, threshold values, or field conventions without verifying a primary source.
- State what is supported, weak, contradicted, or not assessable. Never fabricate reviewer identities, literature, data, or an editorial decision.
- Use an exact manuscript quote or a supplied stable item ID as the anchor. Do not invent line numbers, section numbers, or source IDs.
- Outside an exact manuscript quote, avoid numerical targets, performance values, sample sizes, dates, and citation identifiers. Describe missing evidence qualitatively instead of proposing an illustrative value.
- End with prioritized, actionable checks that can be verified in the manuscript.""",
    ),
    Skill(
        name="nature_response",
        layer="agents",
        category="nature",
        default_active=False,
        description="Draft or audit a point-by-point response to reviewer comments",
        content="""## Nature-style reviewer response
- Parse every reviewer point into request, underlying concern, response decision, manuscript change, and evidence location.
- Be respectful and direct. Do not claim a change, experiment, citation, or page/line location that has not been verified.
- For each point provide: reviewer comment, author response, concrete revision, and manuscript anchor; explicitly mark unresolved items.
- Distinguish agreement, clarification, added analysis, justified disagreement, and unavailable evidence.
- Never say a missing value is already known, retrievable, completed, or verified unless the user or a successful tool result supplies it.
- Say "not supplied in the available evidence", not "not recorded" or "does not exist", unless the complete primary record was actually checked.
- Keep rebuttal language evidence-led and avoid adversarial or dismissive phrasing.""",
    ),
    Skill(
        name="nature_citation",
        layer="agents",
        category="nature",
        default_active=False,
        description="Find and map credible literature support to manuscript claims without fabricating citations",
        content="""## Nature-style citation support
- Split the supplied passage into independently supportable claims before searching.
- Use arxiv_search, rag_search, web_search, and web_fetch only as available; verify title, authors, venue, year, and claim relevance before recommending a source.
- Never manufacture a DOI, bibliographic field, quotation, or source-to-claim relationship.
- Distinguish direct support, contextual background, contrasting evidence, and unverified candidate sources.
- Return a claim-to-source map and clearly label anything that still needs database or publisher verification.""",
    ),
    Skill(
        name="nature_data",
        layer="agents",
        category="nature",
        default_active=False,
        description="Prepare or audit data and code availability statements and reproducibility disclosures",
        content="""## Nature-style data and code availability
- Inventory each dataset, code artifact, model, accession, license, restriction, and access route from supplied facts.
- Draft precise availability language without inventing repositories, identifiers, embargoes, permissions, or request procedures.
- If no access route is supplied, state that availability is not yet specified and requires author input. Never substitute "available upon reasonable request", an author commitment, or institutional approval.
- Separate public, controlled-access, third-party, in-paper, supplementary, and unavailable materials.
- Flag missing metadata, provenance, versioning, persistent identifiers, and reproducibility instructions as explicit action items.
- Produce publication-ready wording plus a concise author verification checklist.""",
    ),
    Skill(
        name="nature_reader",
        layer="agents",
        category="nature",
        default_active=False,
        description="Build a source-grounded bilingual close-reading workflow for a scientific paper",
        content="""## Source-grounded paper close reading
- Preserve the paper's section order and stable source anchors; do not degrade a requested full reading into a summary.
- Separate original text, faithful translation, terminology notes, figure/table interpretation, and critical commentary.
- Keep equations, citations, numbers, captions, and uncertainty aligned with the source.
- Define terms without assigning an unreported study role. Controlled evaluation sample does not imply held-out, test, validation, training separation, randomization, or any particular protocol.
- Use translation and file tools on real project material. Mark OCR, extraction, or alignment uncertainty instead of guessing.
- Maintain a compact terminology ledger for recurring technical terms.""",
    ),
    Skill(
        name="nature_figure",
        layer="agents",
        category="nature",
        default_active=False,
        description="Plan, create, or audit publication-grade scientific figures from real project data",
        content="""## Publication-grade scientific figures
- Establish the figure's scientific conclusion, evidence chain, data source, panel plan, and export requirements before coding.
- Use only real workspace data. Never create mock measurements or hide missing data to make a figure look complete.
- Preserve the scientific meaning of each metric. Do not relabel PCA explained variance as model performance, accuracy, a validation-set score, or a chance-comparison result unless the real source establishes that meaning.
- Do not invent axis baselines, reference lines, component labels, or uncertainty. Mark them as missing requirements instead.
- Ask for Python or R when the backend is not clear; then keep one backend throughout the task.
- Use run_command, never run_sub_agent, to execute the selected Python or R backend. A sub-agent can review text or code but cannot run it.
- Use accessible color, readable type at final size, honest axes, uncertainty where appropriate, and vector output when possible.
- Inspect the rendered artifact and report remaining visual or evidentiary limitations before completion.""",
    ),
]
