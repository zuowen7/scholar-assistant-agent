"""Project management router — create, detect, load, recent, templates."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

_MAX_RECENT = 20
_MAX_FOLDERS = 50
_NAME_RE = re.compile(r"^[\w\-. ]+$")
_ILLEGAL_CHARS_RE = re.compile(r'[<>\:"/\\|?*\x00]')
_FOLDER_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# Windows reserved names (case-insensitive, with or without dot suffix)
_WINDOWS_RESERVED = frozenset(
    x.lower() for x in [
        "CON", "PRN", "AUX", "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    ]
)

# ── Models ────────────────────────────────────────────────────────────────


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=1000)
    author: str = Field(default="", max_length=200)
    template_id: str = Field(default="research_paper", max_length=64)
    init_git: bool = True


class CreateProjectResponse(BaseModel):
    project_path: str
    metadata: dict[str, Any]
    warnings: list[str] = []


class RecentProjectEntry(BaseModel):
    path: str
    name: str
    template_id: str
    opened_at: str


class DetectResponse(BaseModel):
    is_project: bool
    metadata: dict[str, Any] | None = None


# ── Template loader ──────────────────────────────────────────────────────

_templates_cache: list[dict[str, Any]] | None = None


def _load_templates() -> list[dict[str, Any]]:
    global _templates_cache
    if _templates_cache is not None:
        return _templates_cache
    tpl_path = Path(__file__).resolve().parent.parent / "templates" / "project_templates.json"
    if tpl_path.exists():
        try:
            data = json.loads(tpl_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.warning("project_templates.json is not a list, ignoring")
                _templates_cache = []
            else:
                _templates_cache = data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load project templates: %s", e)
            _templates_cache = []
    else:
        _templates_cache = []
    return _templates_cache


def _get_template(template_id: str) -> dict[str, Any] | None:
    for tpl in _load_templates():
        if isinstance(tpl, dict) and tpl.get("id") == template_id:
            return tpl
    return None


# ── Path validation ──────────────────────────────────────────────────────


def _get_allowed_prefixes() -> list[str]:
    """Return normcased absolute paths the user may create projects under."""
    home = str(Path.home().resolve())
    prefixes = [os.path.normcase(home)]
    for env_var in ["USERPROFILE", "HOME", "DOCUMENTS", "DESKTOP", "DOWNLOAD"]:
        val = os.environ.get(env_var)
        if val:
            prefixes.append(os.path.normcase(str(Path(val).resolve())))

    for folder_name in ["Documents", "Desktop", "Downloads", "projects", "Papers"]:
        candidate = Path.home() / folder_name
        if candidate.exists():
            prefixes.append(os.path.normcase(str(candidate.resolve())))

    tmp_prefix = os.path.normcase(str(Path(tempfile.gettempdir()).resolve()))
    prefixes.append(tmp_prefix)

    return list(set(prefixes))


def _validate_project_path(p: str) -> Path:
    """Validate and resolve a project-related path. Returns resolved Path."""
    # Reject null bytes
    if "\x00" in p:
        raise HTTPException(422, "路径包含非法字符 (null byte)")

    # Reject any raw string containing ..
    if ".." in p:
        raise HTTPException(422, "路径不得包含上级引用 (..)")

    try:
        path = Path(p)
    except Exception:
        raise HTTPException(422, f"路径格式无效: {p}")

    if not path.is_absolute():
        raise HTTPException(422, f"路径必须是绝对路径: {p}")

    resolved = path.resolve()
    resolved_str = os.path.normcase(str(resolved))

    allowed = _get_allowed_prefixes()
    if not any(resolved_str.startswith(prefix) for prefix in allowed):
        raise HTTPException(422, f"路径不在允许的工作目录内: {p}")

    return resolved


def _validate_project_name(name: str) -> str:
    """Validate project name. Returns stripped name if valid."""
    if not name or len(name) > 200:
        raise HTTPException(422, "项目名称长度必须在 1-200 之间")

    stripped = name.strip()
    if not stripped:
        raise HTTPException(422, "项目名称不得为纯空白字符")

    if stripped.startswith("."):
        raise HTTPException(422, "项目名称不得以 . 开头")

    if stripped.endswith("."):
        raise HTTPException(422, "项目名称不得以 . 结尾（Windows 文件系统限制）")

    if _ILLEGAL_CHARS_RE.search(stripped):
        raise HTTPException(422, f"项目名称包含非法字符: {stripped}")

    if not _NAME_RE.match(stripped):
        raise HTTPException(422, f"项目名称格式不合法: {stripped}")

    if ".." in stripped:
        raise HTTPException(422, "项目名称不得包含 ..")

    # Windows reserved names
    base = stripped.split(".")[0].lower()
    if base in _WINDOWS_RESERVED:
        raise HTTPException(422, f"项目名称 '{stripped}' 是 Windows 系统保留名")

    return stripped


# ── Recent projects ──────────────────────────────────────────────────────


def _recent_file(data_root: Path) -> Path:
    return data_root / "projects.json"


def _read_recent(data_root: Path) -> list[dict[str, Any]]:
    f = _recent_file(data_root)
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("recent", [])
    except (json.JSONDecodeError, OSError):
        return []


def _write_recent(data_root: Path, entries: list[dict[str, Any]]) -> None:
    valid = []
    for e in entries[:_MAX_RECENT]:
        if not isinstance(e, dict):
            continue
        try:
            if Path(str(e.get("path", ""))).exists():
                valid.append(e)
        except (OSError, Exception):
            pass
    atomic_write_json(_recent_file(data_root), {"recent": valid})


def _add_recent(data_root: Path, project_path: str, name: str, template_id: str) -> None:
    entries = _read_recent(data_root)
    now = datetime.now(timezone.utc).isoformat()

    nc_path = os.path.normcase(project_path)
    entries = [e for e in entries if os.path.normcase(e.get("path", "")) != nc_path]

    entries.insert(0, {
        "path": project_path,
        "name": name,
        "template_id": template_id,
        "opened_at": now,
    })
    _write_recent(data_root, entries[:_MAX_RECENT])


# ── Git ──────────────────────────────────────────────────────────────────


_GITIGNORE = """\
# YanMo project
.venv/
__pycache__/
*.pyc
.DS_Store
Thumbs.db
*.aux
*.log
*.out
*.synctex.gz
*.docx.tmp
*.pdf.tmp
.yanmo/ai_history/
"""


def _git_init(project_dir: Path, project_name: str) -> list[str]:
    """Initialize git repo with initial commit. Returns warnings."""
    warnings: list[str] = []
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5, check=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        warnings.append("Git 未安装或不可用，已跳过版本管理初始化")
        return warnings

    try:
        gitignore = project_dir / ".gitignore"
        gitignore.write_text(_GITIGNORE, encoding="utf-8")

        subprocess.run(
            ["git", "init"],
            cwd=str(project_dir), capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=str(project_dir), capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Initialize {project_name}"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
        logger.warning("Git init failed for %s: %s", project_name, e)
        warnings.append(f"Git 初始化失败: {e}")

    return warnings


# ── README ───────────────────────────────────────────────────────────────


def _generate_readme(name: str, author: str, template_id: str) -> str:
    lines = [
        f"# {name}",
        "",
    ]
    if author:
        lines.append(f"Author: {author}")
        lines.append("")
    lines.extend([
        f"Template: {template_id}",
        "",
        "## Structure",
        "",
    ])
    tpl = _get_template(template_id)
    if tpl:
        for folder in tpl.get("folders", []):
            lines.append(f"- `{folder}/`")
    lines.append("")
    return "\n".join(lines)


# ── Atomic creation ──────────────────────────────────────────────────────


def _validate_template_folders(tpl: dict[str, Any]) -> None:
    """Validate template folder names don't escape the project root."""
    folders = tpl.get("folders")
    if folders is None:
        return  # Missing folders key is OK, defaults to no folders
    if not isinstance(folders, list):
        raise HTTPException(422, f"模板 folders 必须是数组，实际类型: {type(folders)}")
    if len(folders) > _MAX_FOLDERS:
        raise HTTPException(422, f"模板文件夹数量超过上限: {len(folders)} > {_MAX_FOLDERS}")
    for f in folders:
        if not isinstance(f, str) or not f:
            raise HTTPException(422, f"模板文件夹名无效: {f!r}")
        if not _FOLDER_RE.match(f):
            raise HTTPException(422, f"模板文件夹名包含非法字符: {f!r}")
        if f.startswith(".") or ".." in f:
            raise HTTPException(422, f"模板文件夹名不合法: {f!r}")


def _create_project_metadata(
    name: str, author: str, template_id: str, vcs_initialized: bool,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": 1,
        "name": name,
        "author": author,
        "created_at": now,
        "updated_at": now,
        "template_id": template_id,
        "status": "creating",
        "tags": [],
        "vcs": {"initialized": vcs_initialized},
        "env": {"type": None, "path": None},
    }


_MARKDOWN_TEMPLATES: dict[str, str] = {
    "research_paper": """\
# {title}

## Abstract

> Brief summary of the research question, methodology, and key findings.

## 1. Introduction

### 1.1 Background

### 1.2 Research Question

### 1.3 Contributions

## 2. Related Work

## 3. Methodology

### 3.1 Problem Formulation

### 3.2 Proposed Approach

### 3.3 Implementation Details

## 4. Experiments

### 4.1 Experimental Setup

### 4.2 Datasets

### 4.3 Results

### 4.4 Ablation Study

## 5. Discussion

## 6. Conclusion

## References
""",
    "review_paper": """\
# {title}

## Introduction

### Scope of Review

### Search Strategy

## Background

## Thematic Analysis

### Theme 1

### Theme 2

### Theme 3

## Comparative Analysis

## Research Gaps

## Conclusions and Future Directions

## References
""",
    "thesis": """\
# {title}

## Abstract

## Chapter 1: Introduction

### 1.1 Background

### 1.2 Motivation

### 1.3 Research Questions

### 1.4 Thesis Structure

## Chapter 2: Literature Review

### 2.1 Foundation

### 2.2 State of the Art

### 2.3 Research Gaps

## Chapter 3: Methodology

### 3.1 Research Design

### 3.2 Data Collection

### 3.3 Analytical Framework

## Chapter 4: Results and Analysis

### 4.1 Main Findings

### 4.2 Discussion

## Chapter 5: Conclusion

### 5.1 Summary of Contributions

### 5.2 Limitations

### 5.3 Future Work

## References

## Appendix
""",
    "neurips": """\
# {title}

## Abstract

> Summarize the contribution, method, and results in one paragraph.

## 1. Introduction

## 2. Preliminaries

### 2.1 Notation

### 2.2 Problem Setting

## 3. Method

### 3.1 Overview

### 3.2 Key Insight

### 3.3 Algorithm

## 4. Experiments

### 4.1 Setup

### 4.2 Main Results

### 4.3 Analysis

## 5. Conclusion

## Broader Impact

## References

## Appendix

### A. Proofs

### B. Additional Experiments
""",
}


def _generate_markdown_scaffold(template_id: str, dest: Path, title: str) -> None:
    """Generate a Markdown outline file based on the project template."""
    md = _MARKDOWN_TEMPLATES.get(template_id)
    if not md:
        return
    content = md.replace("{title}", title)
    draft_dir = dest / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "main.md").write_text(content, encoding="utf-8")


def _atomic_create_project(
    name: str,
    location: Path,
    author: str,
    template_id: str,
    init_git: bool,
    data_root: Path,
) -> dict[str, Any]:
    """Create project atomically. Returns response dict."""
    name = _validate_project_name(name)
    location = _validate_project_path(str(location))

    final_path = (location / name).resolve()
    nc_final = os.path.normcase(str(final_path))

    if final_path.exists():
        raise HTTPException(409, f"项目路径已存在: {final_path}")
    try:
        for sibling in location.iterdir():
            if os.path.normcase(str(sibling)) == nc_final:
                raise HTTPException(409, f"项目路径已存在（大小写不同）: {sibling}")
    except HTTPException:
        raise
    except OSError:
        pass

    tpl = _get_template(template_id)
    if tpl is None:
        raise HTTPException(422, f"未知模板: {template_id}")
    _validate_template_folders(tpl)

    tmp_name = f".tmp-{uuid.uuid4().hex[:8]}"
    tmp_dir = location / tmp_name
    warnings: list[str] = []

    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
    except PermissionError:
        raise HTTPException(403, f"无权限在 {location} 下创建目录")
    except FileExistsError:
        raise HTTPException(500, "临时目录已存在，请重试")

    try:
        for folder in tpl.get("folders", []):
            (tmp_dir / folder).mkdir(parents=True, exist_ok=True)

        _generate_markdown_scaffold(template_id, tmp_dir, name)

        yanmo_dir = tmp_dir / ".yanmo"
        yanmo_dir.mkdir(parents=True, exist_ok=True)

        metadata = _create_project_metadata(name, author, template_id, init_git)
        meta_path = yanmo_dir / "project.json"
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        readme = tmp_dir / "README.md"
        readme.write_text(_generate_readme(name, author, template_id), encoding="utf-8")

        if init_git:
            git_warnings = _git_init(tmp_dir, name)
            warnings.extend(git_warnings)
            metadata["vcs"]["initialized"] = len(git_warnings) == 0

        # Atomic move (shutil.move handles cross-drive on Windows)
        try:
            shutil.move(str(tmp_dir), str(final_path))
        except OSError as e:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            # Check if target already exists (race condition)
            if final_path.exists():
                raise HTTPException(409, f"项目路径已存在: {final_path}")
            raise HTTPException(500, f"创建项目失败: {e}")

        # Update status to "ready" atomically
        metadata["status"] = "ready"
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            ready_meta_path = final_path / ".yanmo" / "project.json"
            atomic_write_json(ready_meta_path, metadata)
        except OSError as e:
            logger.warning("Failed to update project.json status to ready: %s", e)

        # Best-effort: recent list failure must not fail the whole request
        try:
            _add_recent(data_root, str(final_path), name, template_id)
        except Exception as e:
            logger.warning("Failed to update recent projects: %s", e)

        return {
            "project_path": str(final_path),
            "metadata": metadata,
            "warnings": warnings,
        }

    except HTTPException:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise
    except PermissionError:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise HTTPException(403, f"无权限创建项目: {name}")
    except Exception as e:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        raise HTTPException(500, f"创建项目失败: {e}")


# ── Router registration ──────────────────────────────────────────────────


def register_project(
    app: FastAPI,
    *,
    cloud_only: bool,
    load_config,
    runtime_dir: Path,
    data_root: Path,
) -> dict[str, Any]:
    """Register project management routes."""

    @app.get("/api/project/templates")
    def list_templates():
        return _load_templates()

    @app.post("/api/project/create")
    def create_project(req: CreateProjectRequest):
        return _atomic_create_project(
            name=req.name,
            location=Path(req.location),
            author=req.author,
            template_id=req.template_id,
            init_git=req.init_git,
            data_root=data_root,
        )

    @app.post("/api/project/detect")
    def detect_project(path: str):
        resolved = _validate_project_path(path)
        if not resolved.is_dir():
            return DetectResponse(is_project=False, metadata=None)
        meta_path = resolved / ".yanmo" / "project.json"
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(metadata, dict):
                    return DetectResponse(is_project=True, metadata=metadata)
            except (json.JSONDecodeError, OSError):
                pass
        return DetectResponse(is_project=False, metadata=None)

    @app.delete("/api/project/recent")
    def remove_recent_project(path: str):
        entries = _read_recent(data_root)
        nc_path = os.path.normcase(path)
        filtered = [e for e in entries if os.path.normcase(e.get("path", "")) != nc_path]
        _write_recent(data_root, filtered)
        return {"removed": len(entries) - len(filtered)}

    @app.get("/api/project/recent")
    def list_recent_projects():
        entries = _read_recent(data_root)
        valid = []
        changed = False
        for e in entries:
            try:
                if Path(e["path"]).exists():
                    valid.append(e)
                else:
                    changed = True
            except (OSError, KeyError):
                changed = True
        if changed:
            _write_recent(data_root, valid)
        return valid

    @app.get("/api/project/load")
    def load_project(path: str):
        resolved = _validate_project_path(path)
        meta_path = resolved / ".yanmo" / "project.json"
        if not meta_path.exists():
            raise HTTPException(404, f"项目元数据不存在: {path}")
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise HTTPException(500, f"读取项目元数据失败: {e}")
        # Best-effort: update recent list
        try:
            _add_recent(data_root, str(resolved), metadata.get("name", ""), metadata.get("template_id", ""))
        except Exception:
            pass
        return metadata

    return {}
