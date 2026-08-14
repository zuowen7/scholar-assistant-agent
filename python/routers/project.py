"""Project management router — create, detect, load, recent, templates."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

_MAX_RECENT = 20
_MAX_FOLDERS = 50
_MAX_SOURCE_BYTES = 50 * 1024 * 1024
_NAME_RE = re.compile(r"^[\w\-. ]+$")
_ILLEGAL_CHARS_RE = re.compile(r'[<>\:"/\\|?*\x00]')
_FOLDER_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# Windows reserved names (case-insensitive, with or without dot suffix)
_WINDOWS_RESERVED = frozenset(
    x.lower()
    for x in [
        "CON",
        "PRN",
        "AUX",
        "NUL",
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


class ProjectSourceUpsert(BaseModel):
    project_path: str = Field(min_length=1, max_length=1000)
    source_id: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    original_path: str | None = Field(default=None, max_length=2000)
    translated_path: str | None = Field(default=None, max_length=2000)
    translation_task_id: str | None = Field(default=None, max_length=128)
    rag_status: Literal["unavailable", "queued", "ready", "failed"] = "unavailable"
    reading_status: Literal["unread", "reading", "read"] = "unread"
    cited: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectSourceTranslationAttach(BaseModel):
    project_path: str = Field(min_length=1, max_length=1000)
    output_path: str = Field(min_length=1, max_length=2000)
    task_id: str = Field(min_length=1, max_length=128)
    rag_status: Literal["unavailable", "queued", "ready", "failed"] = "unavailable"


class ProjectExportRecordCreate(BaseModel):
    project_path: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=500)
    format: Literal["word", "latex", "pdf"]
    template_id: str | None = Field(default=None, max_length=128)
    status: Literal["success", "failed", "cancelled"]
    message: str = Field(default="", max_length=2000)


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
    allowed = [Path(prefix).resolve() for prefix in _get_allowed_prefixes()]
    if not any(_is_relative_to(resolved, prefix) for prefix in allowed):
        raise HTTPException(422, f"路径不在允许的工作目录内: {p}")

    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether *path* is inside *parent* using path components."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


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
    now = datetime.now(UTC).isoformat()

    nc_path = os.path.normcase(project_path)
    entries = [e for e in entries if os.path.normcase(e.get("path", "")) != nc_path]

    entries.insert(
        0,
        {
            "path": project_path,
            "name": name,
            "template_id": template_id,
            "opened_at": now,
        },
    )
    _write_recent(data_root, entries[:_MAX_RECENT])


# ── Project sources ──────────────────────────────────────────────────────


def _source_manifest(project_path: Path) -> Path:
    return project_path / ".yanmo" / "sources.json"


def _require_project(project_path: str) -> Path:
    resolved = _validate_project_path(project_path)
    if not (resolved / ".yanmo" / "project.json").is_file():
        raise HTTPException(404, f"项目元数据不存在: {project_path}")
    return resolved


def _read_sources(project_path: Path) -> list[dict[str, Any]]:
    manifest = _source_manifest(project_path)
    if not manifest.exists():
        return []
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"读取项目文献清单失败: {exc}")
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    return [item for item in sources if isinstance(item, dict)]


def _upsert_source(req: ProjectSourceUpsert) -> dict[str, Any]:
    project_path = _require_project(req.project_path)
    sources = _read_sources(project_path)
    now = datetime.now(UTC).isoformat()
    source_id = req.source_id or f"src_{uuid.uuid4().hex[:16]}"
    existing = next((item for item in sources if item.get("id") == source_id), None)
    created_at = existing.get("created_at", now) if existing else now
    source = {
        "id": source_id,
        "title": req.title.strip(),
        "original_path": req.original_path,
        "translated_path": req.translated_path,
        "translation_task_id": req.translation_task_id,
        "rag_status": req.rag_status,
        "reading_status": req.reading_status,
        "cited": req.cited,
        "metadata": req.metadata,
        "created_at": created_at,
        "updated_at": now,
    }
    if existing:
        sources[sources.index(existing)] = source
    else:
        sources.insert(0, source)
    atomic_write_json(_source_manifest(project_path), {"version": 1, "sources": sources})
    return source


def _find_source(project_path: Path, source_id: str) -> dict[str, Any]:
    source = next(
        (item for item in _read_sources(project_path) if item.get("id") == source_id),
        None,
    )
    if source is None:
        raise HTTPException(404, f"项目文献不存在: {source_id}")
    return source


def _resolve_source_attachment(
    project_path: Path,
    source: dict[str, Any],
    *,
    path_key: str = "original_path",
) -> Path:
    raw_path = source.get(path_key)
    if not raw_path:
        label = "译文" if path_key == "translated_path" else "文献"
        raise HTTPException(409, f"该{label}尚未附加可读取的本地文件")
    candidate = Path(str(raw_path))
    if not candidate.is_absolute():
        candidate = project_path / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(404, "文献附件不存在")
    try:
        resolved.relative_to(project_path)
    except ValueError:
        raise HTTPException(403, "文献附件不在当前项目内，请重新导入")
    if not resolved.is_file():
        raise HTTPException(404, "文献附件不存在")
    return resolved


def _extract_source_content(path: Path) -> dict[str, Any]:
    from src.parser import extract_document

    try:
        document = extract_document(path)
    except Exception as exc:
        logger.warning("Source extraction failed for %s: %s", path.name, exc)
        raise HTTPException(422, f"无法解析文献内容: {exc}")
    text = document.full_text.strip()
    if not text:
        from src.parser.ocr import ocr_install_hint

        raise HTTPException(422, f"文献没有可提取文本（疑似扫描版 PDF）。{ocr_install_hint()}")
    return {
        "text": text,
        "pages": len(document.pages),
        "chars": len(text),
    }


def _export_manifest(project_path: Path) -> Path:
    return project_path / ".yanmo" / "exports.json"


def _read_export_history(project_path: Path) -> list[dict[str, Any]]:
    manifest = _export_manifest(project_path)
    if not manifest.exists():
        return []
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"读取项目导出历史失败: {exc}")
    records = payload.get("records", []) if isinstance(payload, dict) else []
    return [item for item in records if isinstance(item, dict)]


def _append_export_record(req: ProjectExportRecordCreate) -> dict[str, Any]:
    project_path = _require_project(req.project_path)
    records = _read_export_history(project_path)
    record = {
        "id": f"export_{uuid.uuid4().hex[:16]}",
        "title": req.title.strip(),
        "format": req.format,
        "template_id": req.template_id,
        "status": req.status,
        "message": req.message,
        "created_at": datetime.now(UTC).isoformat(),
    }
    records.insert(0, record)
    atomic_write_json(_export_manifest(project_path), {"version": 1, "records": records[:100]})
    return record


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
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        warnings.append("Git 未安装或不可用，已跳过版本管理初始化")
        return warnings

    try:
        gitignore = project_dir / ".gitignore"
        gitignore.write_text(_GITIGNORE, encoding="utf-8")

        subprocess.run(
            ["git", "init"],
            cwd=str(project_dir),
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "config", "user.email", "yanmo@local"],
            cwd=str(project_dir),
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["git", "config", "user.name", "研墨"],
            cwd=str(project_dir),
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=str(project_dir),
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Initialize {project_name}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
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
    lines.extend(
        [
            f"Template: {template_id}",
            "",
            "## Structure",
            "",
        ]
    )
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
    name: str,
    author: str,
    template_id: str,
    vcs_initialized: bool,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
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
            with contextlib.suppress(Exception):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            # Check if target already exists (race condition)
            if final_path.exists():
                raise HTTPException(409, f"项目路径已存在: {final_path}")
            raise HTTPException(500, f"创建项目失败: {e}")

        # Update status to "ready" atomically
        metadata["status"] = "ready"
        metadata["updated_at"] = datetime.now(UTC).isoformat()
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
        with contextlib.suppress(Exception):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except PermissionError:
        with contextlib.suppress(Exception):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(403, f"无权限创建项目: {name}")
    except Exception as e:
        with contextlib.suppress(Exception):
            shutil.rmtree(tmp_dir, ignore_errors=True)
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
    from src.agent_v2.runtime.workspace_grants import install_workspace_grants

    workspace_grants = install_workspace_grants(app)

    @app.get("/api/project/templates")
    def list_templates():
        return _load_templates()

    @app.post("/api/project/create")
    def create_project(req: CreateProjectRequest):
        result = _atomic_create_project(
            name=req.name,
            location=Path(req.location),
            author=req.author,
            template_id=req.template_id,
            init_git=req.init_git,
            data_root=data_root,
        )
        result["workspace_grant"] = workspace_grants.issue(result["project_path"])
        return result

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
        with contextlib.suppress(Exception):
            _add_recent(
                data_root, str(resolved), metadata.get("name", ""), metadata.get("template_id", "")
            )
        metadata["workspace_grant"] = workspace_grants.issue(resolved)
        return metadata

    @app.get("/api/project/sources")
    def list_project_sources(project_path: str):
        return {"sources": _read_sources(_require_project(project_path))}

    @app.post("/api/project/sources")
    def upsert_project_source(req: ProjectSourceUpsert):
        return _upsert_source(req)

    @app.post("/api/project/sources/import")
    async def import_project_source(
        project_path: str = Form(...),
        source_id: str | None = Form(default=None),
        file: UploadFile = File(...),
    ):
        from src.parser import SUPPORTED_EXTENSIONS

        project = _require_project(project_path)
        original_name = Path(file.filename or "source").name
        extension = Path(original_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(415, f"不支持的文献格式: {extension or '未知'}")

        content = await file.read(_MAX_SOURCE_BYTES + 1)
        if len(content) > _MAX_SOURCE_BYTES:
            raise HTTPException(413, "文献文件过大（最大 50 MB）")
        if not content:
            raise HTTPException(422, "文献文件为空")

        references = project / "references"
        references.mkdir(parents=True, exist_ok=True)
        target = references / original_name
        if target.exists():
            target = references / f"{target.stem}-{uuid.uuid4().hex[:8]}{target.suffix}"
        fd, temp_name = tempfile.mkstemp(
            dir=references,
            prefix=f".{target.stem}.",
            suffix=target.suffix,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise

        metadata: dict[str, Any] = {
            "filename": original_name,
            "extension": extension,
            "size": len(content),
        }
        try:
            metadata.update(_extract_source_content(target))
            metadata.pop("text", None)
        except HTTPException as exc:
            metadata["parse_error"] = str(exc.detail)

        try:
            existing = _find_source(project, source_id) if source_id else None
            return _upsert_source(
                ProjectSourceUpsert(
                    project_path=str(project),
                    source_id=source_id,
                    title=str(existing["title"]) if existing else Path(original_name).stem,
                    original_path=str(target),
                    translated_path=existing.get("translated_path") if existing else None,
                    translation_task_id=(existing.get("translation_task_id") if existing else None),
                    rag_status=existing.get("rag_status", "unavailable")
                    if existing
                    else "unavailable",
                    reading_status=existing.get("reading_status", "unread")
                    if existing
                    else "unread",
                    cited=bool(existing.get("cited", False)) if existing else False,
                    metadata={
                        **(dict(existing.get("metadata") or {}) if existing else {}),
                        **metadata,
                    },
                )
            )
        except Exception:
            with contextlib.suppress(OSError):
                target.unlink()
            raise

    @app.post("/api/project/sources/{source_id}/translation")
    def attach_project_source_translation(
        source_id: str,
        req: ProjectSourceTranslationAttach,
    ):
        project = _require_project(req.project_path)
        source = _find_source(project, source_id)
        try:
            output = Path(req.output_path).resolve(strict=True)
        except (OSError, RuntimeError):
            raise HTTPException(404, "翻译输出文件不存在")
        allowed_roots = [project.resolve(), runtime_dir.resolve()]
        if not any(output == root or root in output.parents for root in allowed_roots):
            raise HTTPException(403, "翻译输出不在项目或研墨运行目录内")
        translations = project / "references" / "translations"
        translations.mkdir(parents=True, exist_ok=True)
        original_stem = Path(str(source.get("original_path") or source["title"])).stem
        target = translations / f"{original_stem}.translated{output.suffix or '.md'}"
        if output != target:
            shutil.copy2(output, target)
        return _upsert_source(
            ProjectSourceUpsert(
                project_path=str(project),
                source_id=source_id,
                title=str(source["title"]),
                original_path=source.get("original_path"),
                translated_path=str(target),
                translation_task_id=req.task_id,
                rag_status=req.rag_status,
                reading_status=source.get("reading_status", "unread"),
                cited=bool(source.get("cited", False)),
                metadata=dict(source.get("metadata") or {}),
            )
        )

    @app.get("/api/project/sources/{source_id}/content")
    def read_project_source(
        source_id: str,
        project_path: str,
        version: Literal["original", "translated"] = "original",
    ):
        project = _require_project(project_path)
        source = _find_source(project, source_id)
        path_key = "translated_path" if version == "translated" else "original_path"
        payload = _extract_source_content(
            _resolve_source_attachment(project, source, path_key=path_key)
        )
        return {
            "source_id": source_id,
            "title": source.get("title", source_id),
            "version": version,
            **payload,
        }

    @app.delete("/api/project/sources/{source_id}")
    def delete_project_source(
        source_id: str,
        project_path: str,
        delete_file: bool = False,
    ):
        project = _require_project(project_path)
        sources = _read_sources(project)
        source = next((item for item in sources if item.get("id") == source_id), None)
        if source is None:
            raise HTTPException(404, f"项目文献不存在: {source_id}")
        if delete_file and source.get("original_path"):
            attachment = _resolve_source_attachment(project, source)
            managed_root = (project / "references").resolve()
            try:
                attachment.relative_to(managed_root)
            except ValueError:
                raise HTTPException(403, "只能删除项目 references 目录中的托管附件")
            attachment.unlink()
        remaining = [item for item in sources if item.get("id") != source_id]
        atomic_write_json(
            _source_manifest(project),
            {"version": 1, "sources": remaining},
        )
        return {"status": "ok", "deleted": source_id}

    @app.get("/api/project/exports")
    def list_project_exports(project_path: str):
        return {"records": _read_export_history(_require_project(project_path))}

    @app.post("/api/project/exports")
    def create_project_export_record(req: ProjectExportRecordCreate):
        return _append_export_record(req)

    return {}
