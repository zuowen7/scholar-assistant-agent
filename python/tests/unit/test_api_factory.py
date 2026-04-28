"""Unit tests for api_factory helpers — mask, deep_merge, validate_file_path, config cache."""

from __future__ import annotations

import os
import textwrap

import pytest
from fastapi import HTTPException
from pathlib import Path


# ── _mask_api_key / _is_masked ──────────────────────────────────────────


class TestMaskApiKey:

    def _mask(self, cfg: dict) -> None:
        from api_factory import _mask_api_key
        _mask_api_key(cfg)

    def test_long_key_masked(self) -> None:
        cfg = {"translator": {"cloud": {"api_key": "sk-1234567890abcdef"}}}
        self._mask(cfg)
        assert cfg["translator"]["cloud"]["api_key"] == "sk-1****cdef"

    def test_short_key_not_masked(self) -> None:
        cfg = {"translator": {"cloud": {"api_key": "short"}}}
        self._mask(cfg)
        assert cfg["translator"]["cloud"]["api_key"] == "short"

    def test_empty_key_untouched(self) -> None:
        cfg = {"translator": {"cloud": {"api_key": ""}}}
        self._mask(cfg)
        assert cfg["translator"]["cloud"]["api_key"] == ""

    def test_missing_cloud_section_no_error(self) -> None:
        cfg = {"translator": {}}
        self._mask(cfg)

    def test_missing_translator_section_no_error(self) -> None:
        self._mask({})

    def test_exactly_8_chars_not_masked(self) -> None:
        cfg = {"translator": {"cloud": {"api_key": "12345678"}}}
        self._mask(cfg)
        assert cfg["translator"]["cloud"]["api_key"] == "12345678"

    def test_exactly_9_chars_masked(self) -> None:
        cfg = {"translator": {"cloud": {"api_key": "123456789"}}}
        self._mask(cfg)
        assert cfg["translator"]["cloud"]["api_key"] == "1234****6789"


class TestIsMasked:

    def test_masked_value(self) -> None:
        from api_factory import _is_masked
        assert _is_masked("sk-1****cdef")

    def test_unmasked_value(self) -> None:
        from api_factory import _is_masked
        assert not _is_masked("sk-1234567890")

    def test_empty_string(self) -> None:
        from api_factory import _is_masked
        assert not _is_masked("")


# ── _deep_merge ─────────────────────────────────────────────────────────


class TestDeepMerge:

    def _merge(self, base: dict, override: dict) -> dict:
        from api_factory import _deep_merge
        return _deep_merge(base, override)

    def test_shallow_override(self) -> None:
        result = self._merge({"a": 1, "b": 2}, {"b": 3})
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self) -> None:
        result = self._merge(
            {"translator": {"temperature": 0.3, "model": "a"}},
            {"translator": {"temperature": 0.7}},
        )
        assert result["translator"]["temperature"] == 0.7
        assert result["translator"]["model"] == "a"

    def test_new_key_added(self) -> None:
        result = self._merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_base_not_mutated(self) -> None:
        base = {"translator": {"temperature": 0.3}}
        self._merge(base, {"translator": {"temperature": 0.9}})
        assert base["translator"]["temperature"] == 0.3

    def test_override_non_dict_replaces_dict(self) -> None:
        result = self._merge({"a": {"b": 1}}, {"a": "flat"})
        assert result == {"a": "flat"}

    def test_empty_base(self) -> None:
        result = self._merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self) -> None:
        result = self._merge({"a": 1}, {})
        assert result == {"a": 1}


# ── _validate_file_path ────────────────────────────────────────────────


class TestValidateFilePath:

    def _validate(self, p: Path) -> None:
        from api_factory import _validate_file_path
        _validate_file_path(p)

    def test_normal_path_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "paper.pdf"
        f.write_text("ok")
        self._validate(f)

    def test_etc_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            self._validate(Path("/etc/passwd"))
        assert exc_info.value.status_code == 403

    def test_proc_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            self._validate(Path("/proc/1/cmdline"))
        assert exc_info.value.status_code == 403

    def test_dev_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            self._validate(Path("/dev/null"))
        assert exc_info.value.status_code == 403

    def test_windows_path_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            self._validate(Path("C:\\Windows\\System32\\config\\SAM"))
        assert exc_info.value.status_code == 403

    def test_program_files_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            self._validate(Path("C:\\Program Files\\app\\config.ini"))
        assert exc_info.value.status_code == 403

    def test_dot_env_extension_blocked(self, tmp_path: Path) -> None:
        f = tmp_path / "secrets.env"
        with pytest.raises(HTTPException) as exc_info:
            self._validate(f)
        assert exc_info.value.status_code == 403

    def test_dot_key_extension_blocked(self, tmp_path: Path) -> None:
        f = tmp_path / "server.key"
        with pytest.raises(HTTPException) as exc_info:
            self._validate(f)
        assert exc_info.value.status_code == 403

    def test_dot_pem_extension_blocked(self, tmp_path: Path) -> None:
        f = tmp_path / "cert.pem"
        with pytest.raises(HTTPException) as exc_info:
            self._validate(f)
        assert exc_info.value.status_code == 403

    def test_hidden_file_blocked(self, tmp_path: Path) -> None:
        f = tmp_path / ".bashrc"
        with pytest.raises(HTTPException) as exc_info:
            self._validate(f)
        assert exc_info.value.status_code == 403

    def test_normal_dot_in_filename_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "paper.v2.pdf"
        f.write_text("ok")
        self._validate(f)

    def test_ssh_dir_blocked(self) -> None:
        home = Path.home()
        with pytest.raises(HTTPException) as exc_info:
            self._validate(home / ".ssh" / "id_rsa")
        assert exc_info.value.status_code == 403

    def test_aws_dir_blocked(self) -> None:
        home = Path.home()
        with pytest.raises(HTTPException) as exc_info:
            self._validate(home / ".aws" / "credentials")
        assert exc_info.value.status_code == 403

    def test_gnupg_dir_blocked(self) -> None:
        home = Path.home()
        with pytest.raises(HTTPException) as exc_info:
            self._validate(home / ".gnupg" / "pubring.kbx")
        assert exc_info.value.status_code == 403

    def test_docker_dir_blocked(self) -> None:
        home = Path.home()
        with pytest.raises(HTTPException) as exc_info:
            self._validate(home / ".docker" / "config.json")
        assert exc_info.value.status_code == 403

    def test_non_sensitive_home_subdir_passes(self) -> None:
        home = Path.home()
        f = home / "Documents" / "paper.pdf"
        if f.parent.exists():
            self._validate(f)

    def test_symlink_to_etc_blocked(self, tmp_path: Path) -> None:
        link = tmp_path / "link_to_etc"
        link.symlink_to(Path("/etc"))
        with pytest.raises(HTTPException) as exc_info:
            self._validate(link / "passwd")
        assert exc_info.value.status_code == 403

    def test_symlink_to_sensitive_ext_blocked(self, tmp_path: Path) -> None:
        target = tmp_path / "real.key"
        target.write_text("secret")
        link = tmp_path / "link"
        link.symlink_to(target)
        with pytest.raises(HTTPException) as exc_info:
            self._validate(link)
        assert exc_info.value.status_code == 403


# ── _load_config cache behavior ─────────────────────────────────────────


class TestConfigCache:

    def test_loads_from_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import api_factory

        config_file = tmp_path / "config" / "default.yaml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text(textwrap.dedent("""\
            translator:
              temperature: 0.5
            agent:
              max_steps: 10
        """))
        monkeypatch.setattr(api_factory, "CONFIG_PATH", config_file)
        monkeypatch.setattr(api_factory, "_config_cache", None)
        monkeypatch.setattr(api_factory, "_config_cache_mtime", 0.0)

        cfg = api_factory._load_config()
        assert cfg["translator"]["temperature"] == 0.5
        assert cfg["agent"]["max_steps"] == 10

    def test_returns_cached_on_same_mtime(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import api_factory
        import time as _time

        config_file = tmp_path / "config" / "default.yaml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text("translator:\n  temperature: 0.3\n")
        mtime = config_file.stat().st_mtime

        cached_cfg = {"translator": {"temperature": 0.9}, "cached": True}
        monkeypatch.setattr(api_factory, "CONFIG_PATH", config_file)
        monkeypatch.setattr(api_factory, "_config_cache", cached_cfg)
        monkeypatch.setattr(api_factory, "_config_cache_mtime", mtime)

        cfg = api_factory._load_config()
        assert cfg["cached"] is True

    def test_reload_on_mtime_change(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import api_factory

        config_file = tmp_path / "config" / "default.yaml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text("translator:\n  temperature: 0.3\n")
        old_mtime = config_file.stat().st_mtime - 100.0

        monkeypatch.setattr(api_factory, "CONFIG_PATH", config_file)
        monkeypatch.setattr(api_factory, "_config_cache", {"old": True})
        monkeypatch.setattr(api_factory, "_config_cache_mtime", old_mtime)

        cfg = api_factory._load_config()
        assert "old" not in cfg
        assert cfg["translator"]["temperature"] == 0.3

    def test_missing_config_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import api_factory

        missing = tmp_path / "nonexistent" / "default.yaml"
        monkeypatch.setattr(api_factory, "CONFIG_PATH", missing)
        monkeypatch.setattr(api_factory, "_config_cache", None)
        monkeypatch.setattr(api_factory, "_config_cache_mtime", 0.0)

        cfg = api_factory._load_config()
        assert cfg == {}

    def test_env_override_applies(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import api_factory

        config_file = tmp_path / "config" / "default.yaml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text("translator:\n  temperature: 0.3\n")
        monkeypatch.setattr(api_factory, "CONFIG_PATH", config_file)
        monkeypatch.setattr(api_factory, "_config_cache", None)
        monkeypatch.setattr(api_factory, "_config_cache_mtime", 0.0)
        monkeypatch.setenv("SCHOLAR_CLOUD_API_KEY", "sk-test-key-from-env")

        cfg = api_factory._load_config()
        assert cfg["translator"]["cloud"]["api_key"] == "sk-test-key-from-env"
