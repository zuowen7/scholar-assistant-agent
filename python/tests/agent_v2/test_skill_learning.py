from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent_v2.runtime.file_mutations import atomic_write_text
from src.agent_v2.runtime.session import Session
from src.agent_v2.skill_learning import (
    SkillLearningService,
    SkillProposalStore,
    _render_skill_document,
)
from src.agent_v2.skills import SkillRegistry
from src.agent_v2.types import (
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


class ReviewProvider:
    model = "review-test"

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return ProviderResponse(blocks=[TextBlock(text=json.dumps(self.payload))])


def _complete_session(
    workspace: Path, *, success: bool = True, correction: bool = False
) -> Session:
    session = Session(workspace=str(workspace), model="test", session_id="sess_learning")
    session.start_turn("turn_1")
    user_text = (
        "不对，以后应该先检查再修改" if correction else "Inspect and safely update the draft"
    )
    session.append(
        Message(role=MessageRole.USER, blocks=[TextBlock(text=user_text)], raw_text=user_text)
    )
    session.append(
        Message(
            role=MessageRole.ASSISTANT,
            blocks=[ToolUseBlock(id="tool_ok", name="read_file", input='{"file_path":"draft.md"}')],
        )
    )
    session.append(
        Message(
            role=MessageRole.TOOL,
            blocks=[
                ToolResultBlock(
                    tool_use_id="tool_ok",
                    tool_name="read_file",
                    output="api_key=secret-value\nDraft checked",
                    is_error=not success,
                    status="success" if success else "error",
                )
            ],
        )
    )
    session.set_outcome(
        "COMPLETE",
        {
            "tool_counts": {"success": 1 if success else 0, "error": 0 if success else 1},
            "changed_files": [],
            "pending_actions": [],
        },
    )
    return session


def _proposal_payload() -> dict:
    return {
        "decision": "propose",
        "action": "create",
        "name": "verify_before_edit",
        "description": "Verify source state before editing a workspace file",
        "reason": "The successful read established a reusable pre-edit check.",
        "evidence_tool_use_ids": ["tool_ok"],
        "body": (
            "## When to use\nBefore changing an existing workspace file.\n"
            "## Procedure\n1. Read the current file.\n2. Apply a scoped edit.\n"
            "## Verification\nRe-read the changed region and run focused checks."
        ),
    }


@pytest.mark.asyncio
async def test_review_creates_persistent_pending_proposal_with_redacted_trace(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    store = SkillProposalStore(tmp_path / "proposals", skills_dir)
    provider = ReviewProvider(_proposal_payload())
    service = SkillLearningService(
        provider=provider,
        registry=SkillRegistry(),
        store=store,
        config={"min_successful_tools": 1},
    )

    proposal = await service.review(_complete_session(tmp_path), force=True)

    assert proposal is not None
    assert proposal.status == "pending"
    assert store.get(proposal.id) == proposal
    review_message = provider.calls[0][0][0].text_content()
    assert "secret-value" not in review_message
    assert "<redacted>" in review_message


@pytest.mark.asyncio
async def test_failed_tool_is_not_reviewable_evidence_even_when_forced(tmp_path: Path):
    provider = ReviewProvider(_proposal_payload())
    service = SkillLearningService(
        provider=provider,
        registry=SkillRegistry(),
        store=SkillProposalStore(tmp_path / "proposals", tmp_path / "skills"),
    )

    proposal = await service.review(_complete_session(tmp_path, success=False), force=True)

    assert proposal is None
    assert provider.calls == []


def test_automatic_review_requires_opt_in_and_complexity_threshold(tmp_path: Path):
    session = _complete_session(tmp_path)
    store = SkillProposalStore(tmp_path / "proposals", tmp_path / "skills")

    disabled = SkillLearningService(
        provider=ReviewProvider(_proposal_payload()),
        registry=SkillRegistry(),
        store=store,
        config={"enabled": False, "min_successful_tools": 1},
    )
    enabled = SkillLearningService(
        provider=ReviewProvider(_proposal_payload()),
        registry=SkillRegistry(),
        store=store,
        config={"enabled": True, "min_successful_tools": 1},
    )
    too_simple = SkillLearningService(
        provider=ReviewProvider(_proposal_payload()),
        registry=SkillRegistry(),
        store=store,
        config={"enabled": True, "min_successful_tools": 2},
    )

    assert disabled.should_review(session) is False
    assert enabled.should_review(session) is True
    assert too_simple.should_review(session) is False


def test_proposal_dedup_approval_persistence_and_reload(tmp_path: Path):
    store = SkillProposalStore(tmp_path / "proposals", tmp_path / "skills")
    document = _render_skill_document(
        "safe_workflow",
        "A safe reusable workflow",
        "## When to use\nFor repeat work.\n## Procedure\n1. Inspect.\n## Verification\nCheck.",
    )
    kwargs = {
        "action": "create",
        "skill_name": "safe_workflow",
        "description": "A safe reusable workflow",
        "content": document,
        "reason": "Reusable",
        "evidence_tool_use_ids": ["tool_ok"],
        "source_session_id": "sess_1",
        "source_turn_id": "turn_1",
        "workspace": str(tmp_path),
    }

    first = store.create(**kwargs)
    duplicate = store.create(**kwargs)
    approved = store.decide(first.id, "approve")
    registry = SkillRegistry(tmp_path / "skills")

    assert duplicate.id == first.id
    assert approved.status == "approved"
    assert registry.get("safe_workflow") is not None
    assert registry.get("safe_workflow").description == "A safe reusable workflow"


def test_illegal_skill_name_is_rejected_before_path_resolution(tmp_path: Path):
    store = SkillProposalStore(tmp_path / "proposals", tmp_path / "skills")
    with pytest.raises(ValueError, match="safe lowercase ASCII slug"):
        store.create(
            action="create",
            skill_name="../escape",
            description="No",
            content="---\nname: escape\ndescription: No\n---\n# Body",
            reason="No",
            evidence_tool_use_ids=["tool_ok"],
            source_session_id="sess_1",
            source_turn_id="turn_1",
            workspace=str(tmp_path),
        )


def test_update_approval_detects_changed_base_document(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    target = skills_dir / "safe_workflow" / "SKILL.md"
    original = _render_skill_document(
        "safe_workflow",
        "Original",
        "## When to use\nA.\n## Procedure\n1. A.\n## Verification\nA.",
    )
    atomic_write_text(target, original)
    store = SkillProposalStore(tmp_path / "proposals", skills_dir)
    updated = _render_skill_document(
        "safe_workflow",
        "Updated",
        "## When to use\nB.\n## Procedure\n1. B.\n## Verification\nB.",
    )
    from src.agent_v2.runtime.file_mutations import text_hash

    proposal = store.create(
        action="update",
        skill_name="safe_workflow",
        description="Updated",
        content=updated,
        reason="Improve",
        evidence_tool_use_ids=["tool_ok"],
        source_session_id="sess_1",
        source_turn_id="turn_1",
        workspace=str(tmp_path),
        base_content_hash=text_hash(original),
    )
    atomic_write_text(target, original + "\nExternal change")

    with pytest.raises(RuntimeError, match="changed after proposal"):
        store.decide(proposal.id, "approve")


def test_review_decision_api_closes_the_persistent_loop(tmp_path: Path, monkeypatch):
    import src.agent_v2.router as router

    session = _complete_session(tmp_path)
    sessions_dir = tmp_path / "sessions"
    session.save(sessions_dir / f"{session.session_id}.jsonl")
    provider = ReviewProvider(_proposal_payload())
    monkeypatch.setattr(router, "_SESSION_DIR", sessions_dir)
    monkeypatch.setattr(router, "_SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(router, "_SKILL_PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr(router, "_create_provider", lambda *args, **kwargs: provider)
    app = FastAPI()
    router.register_agent_v2_routes(app)
    client = TestClient(app)

    reviewed = client.post(f"/api/agent/v2/skills/review/{session.session_id}")
    assert reviewed.status_code == 200
    proposal = reviewed.json()["proposal"]
    assert proposal["status"] == "pending"

    pending = client.get("/api/agent/v2/skill-proposals").json()
    assert [item["id"] for item in pending] == [proposal["id"]]

    approved = client.post(
        f"/api/agent/v2/skill-proposals/{proposal['id']}/decision",
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    skills = client.get("/api/agent/v2/skills").json()
    assert "verify_before_edit" in {item["name"] for item in skills}
