"""AWA v2 工作区工具 — Agent Workspace Automation 工具集。

本模块实现了 Agent 在项目工作区内的文件操作能力，包括：
- read_file_v2: 带行号的文件读取，支持分页
- list_directory: 目录列表，支持递归和 glob 过滤
- str_replace: 精确字符串替换（自动备份）
- write_file_v2: 整文件写入（自动备份）
- undo_last_change: 回退最近 N 次操作
- run_command_v2: 持久 Bash 会话命令执行
- git_op: 受控 git 操作

版权声明: 本模块属于 Scholar Assistant Agent 子系统。
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_LINE_NUMBER_LIMIT = 2000


# ---------------------------------------------------------------------------
# 工作区工具实现
# ---------------------------------------------------------------------------

def _read_file_v2(
    file_path: str,
    workspace,  # WorkspaceEnv — 在 create_default_registry 中通过闭包注入
    *,
    offset: int = 0,
    limit: int | None = None,
    encoding: str = "utf-8",
) -> str:
    """读取项目工作区内的文件，返回带行号的内容。

    Args:
        file_path: 相对项目根的路径，绝对路径若在项目根内也接受。
        workspace: WorkspaceEnv 实例（内部注入，不暴露给 LLM）。
        offset: 起始行号（0-indexed），默认 0。
        limit: 最多读取行数，None 表示读到结尾。
        encoding: 文件编码，默认 utf-8。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        resolved = workspace.resolve(file_path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not resolved.is_file():
        return json.dumps({"error": f"file not found: {file_path}"})

    # 文档格式（PDF / Word / PPT / EPUB 等二进制文档）→ 走文档解析器提取纯文本。
    # 否则 Agent 读论文永远得到 "binary file, refusing to read" 死胡同，
    # 只能在各工具间反复试探，导致 ReAct 死循环。
    _DOC_EXTS = {".pdf", ".docx", ".doc", ".epub", ".rtf", ".pptx", ".xlsx"}
    ext = resolved.suffix.lower()
    if ext in _DOC_EXTS:
        try:
            from src.parser import extract_document as _extract_doc
            doc = _extract_doc(str(resolved))
            full = doc.full_text or ""
        except Exception as e:
            return json.dumps(
                {"error": f"document parse failed: {e}", "file_path": file_path},
                ensure_ascii=False,
            )
        all_lines = full.splitlines()
        total_lines = len(all_lines)
        end = min(offset + (limit or _LINE_NUMBER_LIMIT), total_lines)
        body = "\n".join(all_lines[offset:end])
        return json.dumps({
            "file_path": file_path,
            "format": ext.lstrip("."),
            "total_lines": total_lines,
            "returned_lines": [offset + 1, end],
            "content": body,
            "truncated": end < total_lines,
            "note": "已由文档解析器提取为纯文本（保留段落顺序，丢弃排版/图片/公式渲染）。这是该文件的真实正文，可直接据此回答，无需再次读取。",
        }, ensure_ascii=False)

    # 二进制检测：前 4096 字节含 NUL → 拒绝（非文档类二进制文件）
    try:
        with open(resolved, "rb") as f:
            head = f.read(4096)
        if b"\x00" in head:
            return json.dumps({
                "error": f"binary file, cannot read as text: {file_path}",
                "hint": "这是二进制文件，不是文本/文档，无需重试读取。请基于已有信息回答或换用其他工具。",
            }, ensure_ascii=False)
    except OSError as e:
        return json.dumps({"error": str(e)})

    # 大小检查
    if resolved.stat().st_size > workspace.max_file_bytes:
        return json.dumps({"error": f"file too large ({resolved.stat().st_size} bytes), max {workspace.max_file_bytes}"})

    try:
        lines = resolved.read_text(encoding=encoding).splitlines(True)
    except Exception as e:
        return json.dumps({"error": f"read failed: {e}"})

    total_lines = len(lines)
    end = min(offset + (limit or _LINE_NUMBER_LIMIT), total_lines)
    sliced = lines[offset:end]

    numbered = []
    for i, line in enumerate(sliced, start=offset + 1):
        numbered.append(f"{i:>6}\t{line.rstrip()}")

    content = "\n".join(numbered)
    truncated = end < total_lines

    return json.dumps({
        "file_path": file_path,
        "total_lines": total_lines,
        "returned_lines": [offset + 1, end],
        "content": content,
        "truncated": truncated,
    }, ensure_ascii=False)


def _list_directory(
    path: str,
    workspace,
    *,
    pattern: str | None = None,
    recursive: bool = False,
    max_entries: int = 200,
) -> str:
    """列出目录内容，返回带类型和大小的结构。

    Args:
        path: 相对项目根的目录路径，默认根目录。
        workspace: WorkspaceEnv 实例（内部注入）。
        pattern: glob 过滤（如 '*.py'），None 表示不过滤。
        recursive: 是否递归（递归时尊重 .gitignore）。
        max_entries: 最大返回条目数，默认 200。
    """
    from src.agent.workspace import WorkspaceViolation

    target = path if path else "."
    try:
        resolved = workspace.resolve(target)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not resolved.is_dir():
        return json.dumps({"error": f"not a directory: {target}"})

    entries = []
    seen = 0
    max_entries = min(max_entries, 1000)

    try:
        if recursive:
            # 读取 .gitignore
            gitignore_patterns = _load_gitignore(resolved, workspace.root)

            for item in resolved.rglob(pattern or "*"):
                rel = item.relative_to(resolved)
                rel_str = str(rel).replace("\\", "/")
                if _gitignored(rel_str, gitignore_patterns):
                    continue
                if seen >= max_entries:
                    break
                entries.append(_dir_entry(item, resolved))
                seen += 1
        else:
            for item in resolved.iterdir():
                if pattern and not item.match(pattern):
                    continue
                if seen >= max_entries:
                    break
                entries.append(_dir_entry(item, resolved))
                seen += 1
    except PermissionError:
        return json.dumps({"error": f"permission denied: {target}"})

    entries.sort(key=lambda e: (e["type"] == "dir", e["name"].lower()))

    return json.dumps({
        "path": target,
        "entries": entries,
        "truncated": seen >= max_entries,
    }, ensure_ascii=False)


def _str_replace(
    file_path: str,
    old_string: str,
    new_string: str,
    workspace,
    journal,  # ChangeJournal — 闭包注入
    *,
    session_id: str = "",
    event_id: str = "",
    replace_all: bool = False,
) -> str:
    """精确字符串替换。

    Args:
        file_path: 目标文件相对路径。
        old_string: 待替换的精确字符串。
        new_string: 替换后的字符串。
        workspace: WorkspaceEnv 实例（内部注入）。
        journal: ChangeJournal 实例（内部注入）。
        session_id: 当前会话 ID。
        event_id: 当前事件 ID。
        replace_all: True 时替换所有出现；False 时要求 old_string 唯一。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        resolved = workspace.resolve(file_path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not resolved.is_file():
        return json.dumps({"error": f"file not found: {file_path}"})

    content = resolved.read_text(encoding="utf-8")
    count = content.count(old_string)

    if count == 0:
        return json.dumps({"error": "old_string not found in file", "file_path": file_path})
    if count > 1 and not replace_all:
        return json.dumps({
            "error": f"old_string appears {count} times — ambiguous. Use replace_all=True or expand old_string context.",
            "file_path": file_path,
            "occurrences": count,
        })

    # 备份
    backup_id = journal.generate_backup_id()
    original_sha = _file_sha256(resolved)
    journal.backup_file(backup_id, resolved, workspace.root)

    # 执行替换
    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    resolved.write_text(new_content, encoding="utf-8")
    new_sha = _file_sha256(resolved)

    # 生成 diff preview
    diff_preview = _make_diff_preview(content, new_content, file_path)

    # 写 journal
    journal.append_entry(
        backup_id=backup_id,
        session_id=session_id or "default",
        event_id=event_id or backup_id,
        tool="str_replace",
        file=file_path.replace("\\", "/"),
        operation="edit",
        original_sha256=original_sha,
        new_sha256=new_sha,
        diff_preview=diff_preview,
    )

    actual = new_content.count(new_string) if old_string != new_string else count
    return json.dumps({
        "file_path": file_path,
        "occurrences": count if replace_all else 1,
        "diff": diff_preview,
        "backup_id": backup_id,
    }, ensure_ascii=False)


def _write_file_v2(
    file_path: str,
    content: str,
    workspace,
    journal,
    *,
    session_id: str = "",
    event_id: str = "",
    must_not_exist: bool = False,
) -> str:
    """整文件写入（仅用于新建文件或全量重写）。

    Args:
        file_path: 目标文件相对路径。
        content: 完整内容。
        workspace: WorkspaceEnv 实例（内部注入）。
        journal: ChangeJournal 实例（内部注入）。
        session_id: 当前会话 ID。
        event_id: 当前事件 ID。
        must_not_exist: True 时若文件已存在则报错。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        resolved = workspace.resolve(file_path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    created = not resolved.exists()

    if must_not_exist and resolved.exists():
        return json.dumps({"error": f"file already exists: {file_path}", "created": False})

    # 备份已存在文件
    backup_id = journal.generate_backup_id()
    original_sha = ""
    if resolved.exists():
        original_sha = _file_sha256(resolved)
        journal.backup_file(backup_id, resolved, workspace.root)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    new_sha = _file_sha256(resolved)

    journal.append_entry(
        backup_id=backup_id,
        session_id=session_id or "default",
        event_id=event_id or backup_id,
        tool="write_file",
        file=file_path.replace("\\", "/"),
        operation="create" if created else "overwrite",
        original_sha256=original_sha,
        new_sha256=new_sha,
    )

    return json.dumps({
        "file_path": file_path,
        "size": len(content),
        "created": created,
        "backup_id": backup_id,
    }, ensure_ascii=False)


def _undo_last_change(
    journal,
    workspace,
    *,
    count: int = 1,
    backup_id: str | None = None,
) -> str:
    """回退最近 N 次破坏性操作。

    Args:
        journal: ChangeJournal 实例（内部注入）。
        workspace: WorkspaceEnv 实例（内部注入）。
        count: 回退次数，默认 1。
        backup_id: 指定回退到某个 backup 点。
    """
    reverted = journal.undo(count=count, backup_id=backup_id)
    if not reverted:
        return json.dumps({"error": "no undoable operations found"})

    return json.dumps({
        "reverted": [
            {"backup_id": r.get("backup_id"), "file_path": r.get("file"), "operation": r.get("tool")}
            for r in reverted
        ],
        "count": len(reverted),
    }, ensure_ascii=False)


def _run_command_v2(
    command: str,
    bash_session,  # BashSession — 闭包注入
    *,
    timeout: int = 120,
    cwd: str | None = None,
) -> str:
    """在持久 BashSession 中执行 shell 命令。

    Args:
        command: 命令字符串。
        bash_session: BashSession 实例（内部注入）。
        timeout: 超时秒，默认 120，硬上限 600。
        cwd: 工作目录相对项目根，None 表示沿用上次 cwd。
    """
    result = bash_session.run_command(command, timeout=timeout, cwd=cwd)
    return result.to_json()


_GIT_ALLOWED_OPS = frozenset({
    "status", "diff", "log", "show", "branch", "tag", "remote",
    "commit", "restore", "checkout", "add", "stash",
})


def _git_op(
    operation: str,
    workspace,  # WorkspaceEnv — 闭包注入
    *,
    args: dict | None = None,
) -> str:
    """受控 git 操作。

    Args:
        operation: 操作名，支持 status/diff/log/show/branch/tag/remote/commit/restore/checkout/add/stash。
        workspace: WorkspaceEnv 实例（内部注入）。
        args: 操作参数字典。
    """
    args = args or {}
    operation = operation.strip().lower()

    if operation not in _GIT_ALLOWED_OPS:
        return json.dumps({
            "error": f"git operation '{operation}' is not allowed",
            "allowed": sorted(_GIT_ALLOWED_OPS),
        })

    # 禁止危险标志
    args_str = json.dumps(args, ensure_ascii=False)
    forbidden = ["--no-verify", "--no-gpg-sign", "--force", "--hard"]
    for flag in forbidden:
        if flag in args_str:
            return json.dumps({"error": f"git flag '{flag}' is banned"})

    # 构建 git 命令
    git_cmd = _build_git_command(operation, args)

    try:
        result = subprocess.run(
            git_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
            cwd=str(workspace.root),
        )
        return json.dumps({
            "operation": operation,
            "exit_code": result.returncode,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:1000],
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"operation": operation, "exit_code": -1, "error": "git command timed out"})
    except Exception as e:
        return json.dumps({"operation": operation, "exit_code": -1, "error": str(e)})


def _build_git_command(operation: str, args: dict) -> str:
    """构建安全的 git 命令字符串。"""
    if operation == "status":
        return "git status --short"
    elif operation == "diff":
        path = args.get("path", "")
        staged = "--staged" if args.get("staged") else ""
        return f"git diff {staged} -- {path}".strip()
    elif operation == "log":
        n = args.get("count", 10)
        return f"git log --oneline -{n}"
    elif operation == "show":
        ref = args.get("ref", "HEAD")
        return f"git show --stat {ref}"
    elif operation == "branch":
        return "git branch -a"
    elif operation == "tag":
        return "git tag -l"
    elif operation == "remote":
        return "git remote -v"
    elif operation == "commit":
        msg = args.get("message", "agent commit").replace('"', '\\"')
        files = args.get("files", [])
        files_str = " ".join(f'"{f}"' for f in files) if files else "-a"
        return f'git commit {files_str} -m "{msg}"'
    elif operation == "add":
        files = args.get("files", [])
        if files:
            files_str = " ".join(f'"{f}"' for f in files)
            return f"git add {files_str}"
        return "git add -A"
    elif operation == "restore":
        path = args.get("path", "")
        source = args.get("source", "HEAD")
        return f'git restore --source={source} -- "{path}"'
    elif operation == "checkout":
        target = args.get("branch", "")
        if target:
            return f'git checkout "{target}"'
        path = args.get("path", "")
        return f'git checkout -- "{path}"'
    elif operation == "stash":
        action = args.get("action", "push")
        if action == "pop":
            return "git stash pop"
        elif action == "list":
            return "git stash list"
        return "git stash push -u"
    return "git status"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _dir_entry(item: Path, base: Path) -> dict:
    try:
        stat = item.stat()
        size = stat.st_size if item.is_file() else None
        import datetime
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
    except OSError:
        size = None
        mtime = ""
    return {
        "name": item.name,
        "type": "dir" if item.is_dir() else "file",
        "size": size,
        "mtime": mtime,
    }


def _load_gitignore(directory: Path, workspace_root: Path) -> list[str]:
    """加载 .gitignore 模式。"""
    gi = directory / ".gitignore"
    if not gi.is_file():
        # 向上查找到 workspace root
        for parent in directory.parents:
            gi = parent / ".gitignore"
            if gi.is_file():
                break
            if parent == workspace_root:
                break
    if not gi.is_file():
        return []
    patterns = []
    for line in gi.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _gitignored(rel_path: str, patterns: list[str]) -> bool:
    """简单 gitignore 匹配（不实现完整 gitignore 规范，只做常见模式）。"""
    parts = rel_path.split("/")
    basename = parts[-1]
    dir_parts = parts[:-1]  # 目录部分

    for pat in patterns:
        if pat.endswith("/"):
            # 目录匹配: node_modules/ → 过滤该目录下所有内容
            dir_name = pat.rstrip("/")
            if dir_name in parts:
                return True
        elif pat.startswith("*"):
            # 通配符匹配文件名
            import fnmatch
            if fnmatch.fnmatch(basename, pat):
                return True
        elif pat.startswith("/"):
            # 从根开始的路径
            import fnmatch
            if fnmatch.fnmatch(rel_path, pat[1:]):
                return True
        else:
            # 任意位置匹配
            import fnmatch
            if fnmatch.fnmatch(basename, pat):
                return True
            if any(fnmatch.fnmatch("/".join(dir_parts[i:]), pat) for i in range(len(dir_parts) + 1)):
                return True
    return False


def _file_sha256(path: Path) -> str:
    """计算文件 SHA-256。"""
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# grep / glob 搜索工具
# ---------------------------------------------------------------------------

def _grep_files(
    pattern: str,
    workspace,
    *,
    path: str = ".",
    glob: str = "*",
    case_sensitive: bool = True,
    max_results: int = 50,
    context_lines: int = 0,
) -> str:
    """在工作区文件中正则搜索内容，返回匹配行。

    Args:
        pattern: 正则表达式或字面字符串。
        workspace: WorkspaceEnv 实例（内部注入）。
        path: 搜索根目录（相对项目根），默认 "."。
        glob: 文件 glob 过滤，如 "*.py"，默认 "*"（全部文件）。
        case_sensitive: 是否区分大小写，默认 True。
        max_results: 最多返回匹配数，默认 50。
        context_lines: 每条匹配上下各显示 N 行，默认 0。
    """
    import re as _re
    from src.agent.workspace import WorkspaceViolation
    import fnmatch

    try:
        root = workspace.resolve(path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not root.is_dir():
        root = root.parent

    flags = 0 if case_sensitive else _re.IGNORECASE
    try:
        regex = _re.compile(pattern, flags)
    except _re.error as e:
        return json.dumps({"error": f"invalid regex: {e}"})

    matches: list[dict] = []
    _BINARY_EXTS = {".pyc", ".exe", ".dll", ".so", ".bin", ".png", ".jpg", ".pdf", ".db"}

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() in _BINARY_EXTS:
            continue
        if not fnmatch.fnmatch(filepath.name, glob):
            continue
        try:
            rel = str(filepath.relative_to(workspace.root))
        except ValueError:
            continue

        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            if regex.search(line):
                entry: dict = {"file": rel, "line": line_no, "content": line.rstrip()}
                if context_lines > 0:
                    ctx_start = max(0, line_no - 1 - context_lines)
                    ctx_end = min(len(lines), line_no + context_lines)
                    entry["context"] = lines[ctx_start:ctx_end]
                matches.append(entry)
                if len(matches) >= max_results:
                    return json.dumps({
                        "matches": matches,
                        "total": len(matches),
                        "truncated": True,
                    }, ensure_ascii=False)

    return json.dumps({
        "matches": matches,
        "total": len(matches),
        "truncated": False,
    }, ensure_ascii=False)


def _glob_files(
    pattern: str,
    workspace,
    *,
    path: str = ".",
    max_results: int = 200,
) -> str:
    """在工作区中按 glob 模式匹配文件路径。

    Args:
        pattern: glob 模式，如 "**/*.py" 或 "src/**/*.ts"。
        workspace: WorkspaceEnv 实例（内部注入）。
        path: 搜索根目录（相对项目根），默认 "."。
        max_results: 最多返回条目数，默认 200。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        root = workspace.resolve(path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not root.is_dir():
        root = root.parent

    try:
        found = sorted(root.glob(pattern))
    except Exception as e:
        return json.dumps({"error": f"glob failed: {e}"})

    results: list[dict] = []
    for p in found[:max_results]:
        try:
            rel = str(p.relative_to(workspace.root))
        except ValueError:
            continue
        results.append({
            "path": rel,
            "type": "dir" if p.is_dir() else "file",
            "size": p.stat().st_size if p.is_file() else None,
        })

    return json.dumps({
        "matches": results,
        "total": len(results),
        "truncated": len(found) > max_results,
    }, ensure_ascii=False)


def _make_diff_preview(old_content: str, new_content: str, file_path: str) -> str:
    """生成 unified diff 预览。"""
    import difflib
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{file_path}", tofile=f"b/{file_path}")
    result = "".join(diff)
    # 截断到 500 字符
    if len(result) > 500:
        result = result[:500] + "\n..."
    return result


# 导出公共接口
__all__ = [
    "_read_file_v2",
    "_list_directory",
    "_str_replace",
    "_write_file_v2",
    "_undo_last_change",
    "_run_command_v2",
    "_git_op",
    "_build_git_command",
]
