"""学术写作 Prompt 加载器 — 从 prompts/ 目录读取模板文件，渲染用户变量。

设计原则：
- 不依赖外部解析库，手写正则提取 system_prompt / user_template
- 每个任务一个渲染函数，显式声明所需变量，IDE 可补全
- 文件不存在时返回安全的 fallback，不崩后端
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

# prompts/ 目录根路径
_PROMPTS_DIR = Path(__file__).parent


def _load_raw(name: str) -> str:
    path = _PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _extract_system_prompt(text: str) -> str:
    """从 prompt 文件中提取 "System Prompt:" 之后的文本块（支持带编号的章节头）。"""
    m = re.search(
        r"(?i)^(?:\d+\.\s*)?System\s+Prompt:\s*\n(.*?)(?=^\d+\.\s*(?:User\s+Prompt|Task\s+Prompt|Few-)|^---)",
        text, re.M | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _extract_user_template(text: str) -> str:
    """从 prompt 文件中提取 "User Prompt Template:" 之后的文本块（支持带编号的章节头）。"""
    m = re.search(
        r"(?i)^(?:\d+\.\s*)?(?:User\s+Prompt\s+Template|Task\s+Prompt):\s*\n(.*)",
        text, re.M | re.DOTALL,
    )
    return m.group(1).strip() if m else text


def _render_template(template: str, **kwargs) -> str:
    """简单的 {{var}} / {var} 模板替换。"""
    for k, v in kwargs.items():
        if v is None:
            v = ""
        template = template.replace(f"{{{k}}}", str(v))
    return template


# ── 全局系统设定 ────────────────────────────────────────────────

def get_system_prompt(
    field: str = "Computer Science",
    venue: str = "conference paper",
    terminology: str = "",
    context: str = "",
) -> str:
    """加载全局系统 prompt，可注入用户配置的领域/期刊信息。"""
    raw = _load_raw("system/academic_writer_system.md")
    if not raw:
        return "You are a helpful academic writing assistant."
    # 系统设定只有系统 prompt 部分，不含用户模板
    sys_part = _extract_system_prompt(raw)
    return _render_template(sys_part, field=field, venue=venue, terminology=terminology, context=context)


# ── 润色 (polish) ────────────────────────────────────────────────

def render_polish_prompt(
    text: str,
    field: str = "Computer Science",
    venue: str = "conference paper",
    terminology: str = "",
    language: str = "zh",
) -> tuple[str, str]:
    """
    返回 (system_prompt, user_prompt)，用于调用 LLM 做学术润色。

    Args:
        text: 待润色的原文
        field: 研究领域
        venue: 目标期刊/会议
        terminology: 需保留的术语列表，逗号分隔
        language: 原文语言 (zh / en)
    """
    raw = _load_raw("tasks_polish/academic_polish.md")
    sys_p = _extract_system_prompt(raw) if raw else "Polish the following academic text."
    user_t = _extract_user_template(raw) if raw else "Polish: {text}"

    term_str = f"[{terminology}]" if terminology else "N/A"
    user = _render_template(user_t,
        field=field,
        venue=venue,
        terminology=term_str,
        language=language,
        text=text,
    )
    return sys_p, user


# ── 连贯性 (coherence) ──────────────────────────────────────────

def render_coherence_prompt(
    current: str,
    previous: str,
    section_goal: str = "",
    terminology: str = "",
) -> tuple[str, str]:
    """
    返回 (system_prompt, user_prompt)，用于上下文连贯性修改。

    Args:
        current: 当前段落（用户选中的）
        previous: 前一段落（用于参考）
        section_goal: 当前小节的目标/目的
        terminology: 需保留的术语
    """
    raw = _load_raw("tasks_coherence/coherence_rewrite.md")
    sys_p = _extract_system_prompt(raw) if raw else "Improve the coherence of the current paragraph."
    user_t = _extract_user_template(raw) if raw else ""

    term_str = f"[{terminology}]" if terminology else "N/A"
    user = _render_template(user_t,
        section_goal=section_goal,
        previous_paragraph=previous,
        current_paragraph=current,
        terminology=term_str,
    )
    return sys_p, user


# ── 受控扩写 (expand) ───────────────────────────────────────────

def render_expand_prompt(
    draft: str,
    section_type: str = "method",
    context: str = "",
    terminology: str = "",
    length: str = "medium",
) -> tuple[str, str]:
    """
    返回 (system_prompt, user_prompt)，用于把草稿扩写成完整段落。

    Args:
        draft: 简短草稿
        section_type: 章节类型 (introduction / method / experiment / discussion)
        context: 背景上下文
        terminology: 需保留的术语
        length: 目标长度 (short / medium / long)
    """
    raw = _load_raw("tasks_expand/grounded_expand.md")
    sys_p = _extract_system_prompt(raw) if raw else "Expand the draft into a complete academic paragraph."
    user_t = _extract_user_template(raw) if raw else ""

    term_str = f"[{terminology}]" if terminology else "N/A"
    user = _render_template(user_t,
        section_type=section_type,
        context=context,
        terminology=term_str,
        length=length,
        draft_text=draft,
    )
    return sys_p, user


# ── Ghost Text 专用 ─────────────────────────────────────────────

def render_ghost_text_prompt(
    context: str,
    after: str = "",
) -> tuple[str, str]:
    """
    Ghost Text 专用提示词：基于上下文续写下一句。

    使用 expand prompt 的变体，但简化输入。
    """
    sys_p = get_system_prompt()
    user = (
        "You are continuing an academic paper.\n"
        "Read the partial text below, then write the next sentence or phrase naturally.\n"
        "Output ONLY the continuation, no explanations, no quotes, no markdown.\n\n"
        f"Partial text:\n{context}"
    )
    if after:
        user += f"\n\nText after cursor (for context only, do not repeat):\n{after[:500]}"
    return sys_p, user


# ── AI 编辑 (edit) ────────────────────────────────────────────────

def render_edit_with_text_prompt(
    text: str,
    instruction: str,
) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt)，用于 AI 编辑（有选中文本时）。"""
    raw = _load_raw("tasks_edit/edit_with_text.md")
    sys_p = _extract_system_prompt(raw) if raw else (
        "你是一个学术写作助手。用户会提供一段文本和一条指令，"
        "请严格根据指令处理文本。直接输出处理后的结果，不要添加解释或前言。"
        "如果指令不是对文本进行编辑操作（如问候、闲聊、提问），请正常回复。"
    )
    user_t = _extract_user_template(raw) if raw else "--- 文本 ---\n{text}\n--- 指令 ---\n{instruction}"
    user = _render_template(user_t, text=text, instruction=instruction)
    return sys_p, user


def render_edit_without_text_prompt(
    instruction: str,
) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt)，用于 AI 对话（无选中文本时）。"""
    raw = _load_raw("tasks_edit/edit_without_text.md")
    sys_p = _extract_system_prompt(raw) if raw else (
        "你是一个学术研究助手，可以帮助用户进行学术写作、翻译、润色、"
        "文献检索、论文大纲等任务。请用中文回复用户的问题。"
    )
    user_t = _extract_user_template(raw) if raw else "{instruction}"
    user = _render_template(user_t, instruction=instruction)
    return sys_p, user


def render_auto_complete_prompt(
    context: str,
) -> str:
    """返回用于自动补全的完整 prompt（单条 user 消息）。"""
    raw = _load_raw("tasks_edit/auto_complete.md")
    sys_p = _extract_system_prompt(raw) if raw else (
        "You are an academic writing auto-complete assistant. "
        "Continue the text naturally. Output ONLY the continuation, "
        "no explanations, no markdown, no preamble."
    )
    user_t = _extract_user_template(raw) if raw else "Context:\n{context}"
    user = _render_template(user_t, context=context)
    return f"{sys_p}\n\n{user}"


# ── 内容合规检查 ────────────────────────────────────────────────

def render_compliance_prompt(
    text: str,
    title: str = "",
    venue: str = "",
    required_sections: str = "",
) -> tuple[str, str]:
    """
    返回 (system_prompt, user_prompt)，用于 AI 内容合规检查。

    Args:
        text: 论文全文（Markdown 格式）
        title: 论文标题
        venue: 目标期刊/会议
        required_sections: 必需章节（逗号分隔）
    """
    raw = _load_raw("tasks_compliance/compliance_check.md")
    sys_p = _extract_system_prompt(raw) if raw else "Analyze the paper and output JSON."
    user_t = _extract_user_template(raw) if raw else ""

    user = _render_template(user_t,
        title=title or "Untitled",
        venue=venue or "general academic paper",
        required_sections=required_sections or "introduction, related_work, method, experiment, conclusion",
        text=text[:8000],  # 限制字数，避免 token 超限
    )
    return sys_p, user


def parse_compliance_json(raw: str) -> dict:
    """
    解析合规检查返回的 JSON。

    尝试从 LLM 返回中提取 JSON 对象，支持以下情况：
    - 纯 JSON
    - JSON 包裹在 markdown ```json ``` 中
    - JSON 前有少量文字说明
    """
    import json as _json

    # 尝试直接解析
    try:
        return _json.loads(raw.strip())
    except Exception:
        pass

    # 尝试从 markdown 代码块中提取
    import re as _re
    m = _re.search(r"```json\s*(.*?)\s*```", raw, _re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(1).strip())
        except Exception:
            pass

    # 尝试找第一个 { 到最后一个 } 之间所有内容
    m = _re.search(r"(\{.*\})", raw, _re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(1).strip())
        except Exception:
            pass

    # 全解析失败，返回错误结构
    return {
        "error": "JSON 解析失败",
        "raw_preview": raw[:500],
        "summary": {"compliance_score": 0, "overall_status": "fail"},
    }


# ── 统一解析 ───────────────────────────────────────────────────

def parse_llm_output(raw: str) -> dict:
    """
    解析 LLM 返回的 markdown 格式输出。

    支持格式：
        [Main Text]
        ...

        [Key Edits / Supporting Notes / Added Elements / Coherence Strategy]
        - ...

        [Risk Flags]
        - ...

    Returns:
        dict with keys: main_text, secondary, risk_flags
    """
    result = {"main_text": "", "secondary": "", "risk_flags": ""}

    # 提取 [Main Text] / [Revised Paragraph] / [Expanded Paragraph]
    for label in ["Main Text", "Revised Paragraph", "Expanded Paragraph"]:
        m = re.search(
            rf"(?i)\[{label}\]\s*\n(.*?)(?=\n\[|$)",
            raw, re.DOTALL
        )
        if m:
            result["main_text"] = m.group(1).strip()
            break

    # 提取第二个 section
    for label in ["Key Edits", "Supporting Notes", "Added Elements", "Coherence Strategy"]:
        m = re.search(
            rf"(?i)\[{label}\]\s*\n(.*?)(?=\n\[|$)",
            raw, re.DOTALL
        )
        if m:
            result["secondary"] = m.group(1).strip()
            break

    # 提取 Risk Flags
    m = re.search(r"(?i)\[Risk Flags\]\s*\n(.*)", raw, re.DOTALL)
    if m:
        result["risk_flags"] = m.group(1).strip()

    # 如果完全没有结构化标记，整段返回为主文本
    if not result["main_text"]:
        result["main_text"] = raw.strip()

    return result


# ── Schema validation utility (Phase B) ────────────────────────────────────

def validate_prompt_schema(name: str, strict: bool = False) -> list[str]:
    """Validate a prompt file against the 6-layer PromptSpec schema.

    Args:
        name: relative path from prompts/ dir (e.g. "tasks_polish/academic_polish.md")
        strict: if True, raise PromptSchemaError on missing layer; if False, return as warning
    Returns:
        list of warning strings (empty = fully valid)
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    try:
        from src.prompts.schema import PromptSpec, PromptSchemaError
    except ImportError:
        return ["schema module not available (src.prompts.schema)"]

    raw = _load_raw(name)
    if not raw:
        return [f"File not found: {name}"]

    try:
        spec = PromptSpec.from_yaml_frontmatter(raw)
    except PromptSchemaError as e:
        msg = f"Schema error in {name}: {e}"
        if strict:
            raise
        _log.warning(msg)
        return [msg]

    warnings = spec.validate()
    for w in warnings:
        _log.warning("Prompt schema warning in %s: %s", name, w)
    return warnings
