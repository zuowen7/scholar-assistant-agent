from datetime import date

from src.agent_v2.router import _build_system_prompt


def test_system_prompt_exposes_current_date_to_agent():
    prompt = _build_system_prompt("C:/workspace", [])

    assert f"Current date: {date.today().isoformat()}" in prompt
