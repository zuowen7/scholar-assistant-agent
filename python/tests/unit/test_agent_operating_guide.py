"""Agent operating guide tests.

The guide is the compact, machine-readable equivalent of the top of AGENTS.md:
role, gates, decision routes, and verification commands.
"""

from __future__ import annotations


def test_operating_guide_contains_hitl_gates_and_decision_routes():
    from src.agent.operating_guide import build_agent_operating_guide

    guide = build_agent_operating_guide()

    assert guide["name"] == "Scholar Assistant Agent Operating Guide"
    assert "Codex for papers" in guide["role"]
    gate_names = {gate["name"] for gate in guide["gates"]}
    assert {"SmartPause", "WorkspaceBoundary", "DocQAShortCircuit"} <= gate_names
    routes = {route["intent"]: route["path"] for route in guide["decision_guide"]}
    assert routes["document_qa"] == "oneshot_doc_qa"
    assert routes["file_mutation"] == "agent_react_with_approval"
    assert any("pytest tests/unit/ -q" in cmd for cmd in guide["verification"])


def test_operating_guide_is_safe_to_expose_as_json():
    from src.agent.operating_guide import build_agent_operating_guide

    guide = build_agent_operating_guide()

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert isinstance(key, str)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        else:
            assert value is None or isinstance(value, (str, int, float, bool))

    walk(guide)
