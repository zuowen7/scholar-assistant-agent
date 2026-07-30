"""One-shot academic edit prompt safety and packaging contracts."""

from pathlib import Path

import pytest

from prompts import loader


@pytest.mark.parametrize(
    ("renderer", "args"),
    [
        (loader.render_edit_with_text_prompt, ("已有结果为59.1%。", "扩写")),
        (loader.render_edit_without_text_prompt, ("给我补充实验结果",)),
    ],
)
def test_edit_entrypoints_receive_the_same_non_fabrication_core(renderer, args):
    system_prompt, _user_prompt = renderer(*args)

    assert "不得新增输入中不存在的数字" in system_prompt
    assert "不得编造或猜测引用" in system_prompt
    assert "待核验" in system_prompt


def test_required_edit_prompt_missing_fails_closed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)

    with pytest.raises(loader.PromptLoadError, match="edit_with_text.md"):
        loader.render_edit_with_text_prompt("text", "polish")


def test_required_prompt_bundle_validation_returns_stable_hash():
    first = loader.validate_required_prompt_bundle()
    second = loader.validate_required_prompt_bundle()

    assert first["bundle_version"]
    assert first["bundle_hash"] == second["bundle_hash"]
    assert set(first["prompt_hashes"]) == set(loader.REQUIRED_PROMPTS)
