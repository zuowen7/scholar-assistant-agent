"""打包一致性测试 — api.exe 的 Python 子命令转发与运行时目录种子。"""

from __future__ import annotations

import sys
from pathlib import Path

from api import _maybe_run_python_subcommand


def test_api_exe_script_subcommand(tmp_path: Path, monkeypatch):
    """打包后 run_command 执行 `python script.py` 会以 `api.exe script.py` 形式调用。"""
    marker = tmp_path / "marker.txt"
    script = tmp_path / "probe.py"
    script.write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["api.exe", str(script), "arg1"])

    assert _maybe_run_python_subcommand() is True
    assert marker.read_text(encoding="utf-8") == "ok"


def test_api_exe_dash_m_subcommand(tmp_path: Path, monkeypatch):
    """`python -m module` 形式（pip 等）同样转发。"""
    marker = tmp_path / "m.txt"
    module = tmp_path / "probe_mod.py"
    module.write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('m-ok', encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["api.exe", "-m", "probe_mod"])

    assert _maybe_run_python_subcommand() is True
    assert marker.read_text(encoding="utf-8") == "m-ok"


def test_api_exe_server_args_return_false(monkeypatch):
    """普通服务端参数不触发子命令转发。"""
    monkeypatch.setattr(sys, "argv", ["api.exe", "--port", "1234"])
    assert _maybe_run_python_subcommand() is False


def test_seed_optional_runtime_dir_copies_once(tmp_path: Path):
    import api_factory

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("bundled", encoding="utf-8")
    dst = tmp_path / "dst"

    api_factory._seed_optional_runtime_dir(src, dst)
    assert (dst / "a.md").read_text(encoding="utf-8") == "bundled"

    # 已存在 → 不覆盖（尊重用户本地修改）
    (dst / "a.md").write_text("user-modified", encoding="utf-8")
    api_factory._seed_optional_runtime_dir(src, dst)
    assert (dst / "a.md").read_text(encoding="utf-8") == "user-modified"
