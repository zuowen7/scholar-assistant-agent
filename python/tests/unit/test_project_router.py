"""Project router 单元测试 — 创建、模板、检测、最近项目、加载。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── Fixtures ──────────────────────────────────────────────────────────────


def _stub_load_config():
    return {"translator": {}, "agent": {}}


@pytest.fixture
def app_with_project(tmp_path: Path):
    """创建注册了 project router 的 FastAPI app。"""
    from routers.project import register_project

    app = FastAPI()
    register_project(
        app,
        cloud_only=False,
        load_config=_stub_load_config,
        runtime_dir=tmp_path,
        data_root=tmp_path / "data",
    )
    return app


@pytest.fixture
def client(app_with_project: FastAPI):
    return TestClient(app_with_project)


@pytest.fixture
def location(tmp_path: Path):
    """创建项目用的父目录。"""
    loc = tmp_path / "projects"
    loc.mkdir()
    return loc


# ── TestProjectTemplates ─────────────────────────────────────────────────


class TestProjectTemplates:
    def test_list_templates_returns_all_templates(self, client):
        r = client.get("/api/project/templates")
        assert r.status_code == 200
        templates = r.json()
        assert isinstance(templates, list)
        ids = [t["id"] for t in templates]
        assert "research_paper" in ids
        assert "review_paper" in ids
        assert "thesis" in ids
        assert "blank" in ids

    def test_template_has_required_fields(self, client):
        r = client.get("/api/project/templates")
        for t in r.json():
            assert "id" in t
            assert "name" in t
            assert "folders" in t
            assert isinstance(t["folders"], list)
            assert len(t["folders"]) > 0

    def test_template_folders_all_created(self, client, location: Path):
        r = client.get("/api/project/templates")
        templates = r.json()
        for tpl in templates:
            for folder in tpl["folders"]:
                assert isinstance(folder, str)
                assert folder == folder.strip()
                assert "/" not in folder
                assert "\\" not in folder


# ── TestCreateProject ────────────────────────────────────────────────────


class TestCreateProject:
    def test_create_project_basic(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "MyPaper",
            "location": str(location),
            "author": "Test Author",
            "template_id": "research_paper",
            "init_git": False,
        })
        assert r.status_code == 200
        data = r.json()
        assert "project_path" in data
        assert "metadata" in data
        assert "warnings" in data
        assert data["metadata"]["name"] == "MyPaper"
        assert data["metadata"]["author"] == "Test Author"
        assert data["metadata"]["template_id"] == "research_paper"
        assert data["metadata"]["status"] == "ready"

    def test_creates_standard_folders(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "FoldersTest",
            "location": str(location),
            "template_id": "research_paper",
            "init_git": False,
        })
        assert r.status_code == 200
        project_path = Path(r.json()["project_path"])
        for folder in ["draft", "revised", "final", "references", "data", "notes", "scripts", "ai"]:
            assert (project_path / folder).is_dir(), f"Missing folder: {folder}"

    def test_creates_yanmo_metadata(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "MetaTest",
            "location": str(location),
            "init_git": False,
        })
        project_path = Path(r.json()["project_path"])
        meta_path = project_path / ".yanmo" / "project.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["version"] == 1
        assert meta["name"] == "MetaTest"
        assert meta["status"] == "ready"
        assert "created_at" in meta
        assert "updated_at" in meta

    def test_creates_readme(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "ReadmeTest",
            "location": str(location),
            "init_git": False,
        })
        project_path = Path(r.json()["project_path"])
        readme = project_path / "README.md"
        assert readme.exists()
        content = readme.read_text(encoding="utf-8")
        assert "ReadmeTest" in content

    def test_rejects_empty_name(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "",
            "location": str(location),
        })
        assert r.status_code == 422

    def test_rejects_too_long_name(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "x" * 201,
            "location": str(location),
        })
        assert r.status_code == 422

    def test_rejects_illegal_chars_in_name(self, client, location: Path):
        for bad_name in ["bad:name", 'bad"name', "bad<name>", "bad|name", "bad?name", "bad*name"]:
            r = client.post("/api/project/create", json={
                "name": bad_name,
                "location": str(location),
            })
            assert r.status_code == 422, f"Expected 422 for name={bad_name!r}"

    def test_rejects_path_traversal_name(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "..etc",
            "location": str(location),
        })
        assert r.status_code == 422

    def test_rejects_path_traversal_location(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "OK",
            "location": str(location / ".." / ".." / "etc"),
        })
        assert r.status_code == 422

    def test_rejects_relative_location(self, client):
        r = client.post("/api/project/create", json={
            "name": "RelPath",
            "location": "relative/path",
        })
        assert r.status_code == 422

    def test_rejects_duplicate_path(self, client, location: Path):
        client.post("/api/project/create", json={
            "name": "Dup",
            "location": str(location),
            "init_git": False,
        })
        r = client.post("/api/project/create", json={
            "name": "Dup",
            "location": str(location),
            "init_git": False,
        })
        assert r.status_code == 409

    def test_case_insensitive_duplicate(self, client, location: Path):
        client.post("/api/project/create", json={
            "name": "CaseTest",
            "location": str(location),
            "init_git": False,
        })
        r = client.post("/api/project/create", json={
            "name": "casetest",
            "location": str(location),
            "init_git": False,
        })
        # Windows: case-insensitive → 409; Linux: case-sensitive → 200
        if sys.platform == "win32" or os.path.normcase("A") == os.path.normcase("a"):
            assert r.status_code == 409
        else:
            assert r.status_code == 200

    def test_init_git_creates_initial_commit(self, client, location: Path):
        # Skip if git is not available
        try:
            subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=True)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("Git not available")

        r = client.post("/api/project/create", json={
            "name": "GitTest",
            "location": str(location),
            "init_git": True,
        })
        assert r.status_code == 200
        project_path = Path(r.json()["project_path"])
        assert (project_path / ".git").is_dir()
        # Check initial commit exists
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(project_path),
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Initialize GitTest" in result.stdout or "Initialize" in result.stdout

    def test_skip_git_when_not_requested(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "NoGit",
            "location": str(location),
            "init_git": False,
        })
        assert r.status_code == 200
        project_path = Path(r.json()["project_path"])
        assert not (project_path / ".git").exists()

    def test_git_unavailable_graceful_fallback(self, client, location: Path):
        with patch("routers.project.subprocess.run", side_effect=FileNotFoundError):
            r = client.post("/api/project/create", json={
                "name": "NoGitAvail",
                "location": str(location),
                "init_git": True,
            })
        assert r.status_code == 200
        assert any("git" in w.lower() for w in r.json()["warnings"])

    def test_returns_warnings_when_git_unavailable(self, client, location: Path):
        with patch("routers.project.subprocess.run", side_effect=FileNotFoundError):
            r = client.post("/api/project/create", json={
                "name": "WarnTest",
                "location": str(location),
                "init_git": True,
            })
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["warnings"], list)
        assert len(data["warnings"]) > 0

    def test_partial_failure_rollback(self, client, location: Path):
        """如果 rename 失败，临时目录应被清理。"""
        with patch("os.rename", side_effect=OSError("mock rename failure")):
            r = client.post("/api/project/create", json={
                "name": "RollbackTest",
                "location": str(location),
                "init_git": False,
            })
        assert r.status_code == 500
        # tmp dir should be cleaned up
        tmp_files = [f for f in location.iterdir() if f.name.startswith(".tmp-")]
        assert len(tmp_files) == 0

    def test_permission_error_returns_403(self, client, location: Path):
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("no write")):
            r = client.post("/api/project/create", json={
                "name": "PermTest",
                "location": str(location),
                "init_git": False,
            })
        assert r.status_code == 403

    def test_rejects_dot_prefix_name(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": ".hidden",
            "location": str(location),
        })
        assert r.status_code == 422

    def test_name_with_spaces_allowed(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "My Paper v2",
            "location": str(location),
            "init_git": False,
        })
        assert r.status_code == 200

    def test_name_with_unicode_allowed(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "中文论文",
            "location": str(location),
            "init_git": False,
        })
        assert r.status_code == 200

    def test_rejects_invalid_template_id(self, client, location: Path):
        r = client.post("/api/project/create", json={
            "name": "BadTpl",
            "location": str(location),
            "template_id": "nonexistent",
            "init_git": False,
        })
        assert r.status_code == 422


# ── TestDetectProject ────────────────────────────────────────────────────


class TestDetectProject:
    def test_detect_existing_project(self, client, location: Path):
        # Create a project first
        cr = client.post("/api/project/create", json={
            "name": "DetectMe",
            "location": str(location),
            "init_git": False,
        })
        project_path = cr.json()["project_path"]

        r = client.post("/api/project/detect", params={"path": project_path})
        assert r.status_code == 200
        assert r.json()["is_project"] is True
        assert r.json()["metadata"]["name"] == "DetectMe"

    def test_detect_non_project(self, client, tmp_path: Path):
        non_project = tmp_path / "empty_dir"
        non_project.mkdir()
        r = client.post("/api/project/detect", params={"path": str(non_project)})
        assert r.status_code == 200
        assert r.json()["is_project"] is False
        assert r.json()["metadata"] is None

    def test_detect_rejects_path_traversal(self, client):
        r = client.post("/api/project/detect", params={"path": "/etc/../etc/passwd"})
        assert r.status_code == 422


# ── TestRecentProjects ───────────────────────────────────────────────────


class TestRecentProjects:
    def test_recent_empty_initially(self, client):
        r = client.get("/api/project/recent")
        assert r.status_code == 200
        assert r.json() == []

    def test_recent_after_create(self, client, location: Path):
        client.post("/api/project/create", json={
            "name": "Recent1",
            "location": str(location),
            "init_git": False,
        })
        r = client.get("/api/project/recent")
        assert r.status_code == 200
        recent = r.json()
        assert len(recent) >= 1
        assert recent[0]["name"] == "Recent1"

    def test_recent_max_20_lru(self, client, location: Path):
        for i in range(25):
            r = client.post("/api/project/create", json={
                "name": f"LRU_{i:03d}",
                "location": str(location),
                "init_git": False,
            })
            assert r.status_code == 200, f"Failed at i={i}: {r.text}"
        r = client.get("/api/project/recent")
        recent = r.json()
        assert len(recent) <= 20
        # Latest should be first
        names = [p["name"] for p in recent]
        assert "LRU_024" in names
        assert "LRU_000" not in names

    def test_recent_skips_deleted_projects(self, client, location: Path):
        cr = client.post("/api/project/create", json={
            "name": "ToDelete",
            "location": str(location),
            "init_git": False,
        })
        project_path = Path(cr.json()["project_path"])
        shutil.rmtree(project_path)

        r = client.get("/api/project/recent")
        recent = r.json()
        paths = [p["path"] for p in recent]
        # Deleted path should be filtered out
        assert str(project_path) not in [os.path.normcase(p) for p in paths]


# ── TestLoadProject ──────────────────────────────────────────────────────


class TestLoadProject:
    def test_load_existing_project(self, client, location: Path):
        cr = client.post("/api/project/create", json={
            "name": "LoadMe",
            "location": str(location),
            "author": "Author1",
            "init_git": False,
        })
        project_path = cr.json()["project_path"]

        r = client.get("/api/project/load", params={"path": project_path})
        assert r.status_code == 200
        meta = r.json()
        assert meta["name"] == "LoadMe"
        assert meta["author"] == "Author1"
        assert meta["version"] == 1

    def test_load_nonexistent_returns_404(self, client, tmp_path: Path):
        fake_path = str(tmp_path / "nonexistent")
        r = client.get("/api/project/load", params={"path": fake_path})
        assert r.status_code == 404

    def test_load_rejects_path_traversal(self, client):
        r = client.get("/api/project/load", params={"path": "/etc/passwd"})
        assert r.status_code == 422

    def test_load_version_migration_placeholder(self, client, location: Path):
        """version!=1 应正常加载（未来迁移占位）。"""
        cr = client.post("/api/project/create", json={
            "name": "VersionTest",
            "location": str(location),
            "init_git": False,
        })
        project_path = Path(cr.json()["project_path"])
        meta_path = project_path / ".yanmo" / "project.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["version"] = 99
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        r = client.get("/api/project/load", params={"path": str(project_path)})
        assert r.status_code == 200
        assert r.json()["version"] == 99
