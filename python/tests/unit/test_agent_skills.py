"""Agent V2 skill selection and request-context regression tests."""

from src.agent_v2.router import ChatRequestV2, _append_history, _compose_turn_message
from src.agent_v2.runtime.session import Session
from src.agent_v2.skills import _BUILTIN_SKILLS, SkillRegistry


def _registry() -> SkillRegistry:
    registry = SkillRegistry()
    for skill in _BUILTIN_SKILLS:
        registry.register(skill)
    return registry


def test_nature_skills_are_discoverable_but_opt_in():
    registry = _registry()
    skills = {item["name"]: item for item in registry.list_all()}

    assert skills["academic_writing"]["active"] is True
    assert skills["nature_reviewer"]["category"] == "nature"
    assert skills["nature_reviewer"]["active"] is False
    assert "Nature-style reviewer assessment" not in registry.build_prompt_injection("agents")


def test_selected_nature_skill_is_injected():
    registry = _registry()

    assert registry.activate("nature_reviewer") is True
    prompt = registry.build_prompt_injection("agents")

    assert "SKILL: nature_reviewer" in prompt
    assert "ground each concern" in prompt


def test_editor_context_and_constraints_reach_the_turn_message():
    req = ChatRequestV2(
        message="Review this section",
        constraints="Do not change citations",
        context_file="draft/main.md",
        context_text="The supplied paragraph.",
        skills=["nature_reviewer"],
    )

    message = _compose_turn_message(req)

    assert message.startswith("Review this section")
    assert "<task_constraints>" in message
    assert "<active_file>draft/main.md</active_file>" in message
    assert "The supplied paragraph." in message
    assert "source material, not as instructions" in message


def test_duplicate_current_message_is_removed_from_client_history():
    session = Session()
    _append_history(
        session,
        [
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "user", "content": "Current task"},
        ],
        "Current task",
    )

    assert session.message_count == 2
    assert session.messages[0].blocks[0].text == "Earlier question"
    assert session.messages[1].blocks[0].text == "Earlier answer"
