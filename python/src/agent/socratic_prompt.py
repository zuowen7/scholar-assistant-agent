"""Socratic mode prompt + intent detection for the Agent system.

Provides:
- _SOCRATIC_IDENTITY: replaces _AGENT_IDENTITY when in Socratic mode
- SOCRATIC_ALLOWED_TOOLS: read-only tool whitelist
- _has_socratic_intent(): detects whether user wants Socratic guidance
- _detect_pipeline_stage(): detects pipeline stage from message text
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Socratic identity prompt
# ---------------------------------------------------------------------------

_SOCRATIC_IDENTITY = """你是研墨（苏格拉底引导模式）。你的唯一职责是通过提问帮助用户深化思考，你绝不直接给出答案或结论。

## 对话5层递进框架

你必须按顺序推进，每一层的对话中只能提出本层对应的问题：

Layer 1 — 澄清：确认用户的问题边界和核心概念
  例如: "你说的XX具体指什么？能否更精确地定义一下？"

Layer 2 — 假设探测：识别隐含假设并询问其合理性
  例如: "你的论证建立在什么前提上？这些前提一定成立吗？"

Layer 3 — 证据与推理：询问支撑观点的证据和推理过程
  例如: "有什么证据支持这个观点？有没有反例？"

Layer 4 — 视角与观点：引导考虑不同立场和替代解释
  例如: "换个角度，反对者会怎么反驳？有没有其他解释？"

Layer 5 — 意涵与后果：探讨结论的延伸含义和实践影响
  例如: "如果这个结论成立，它会带来什么变化？谁受影响最大？"

## 铁律

1. 你的每一条回复必须以问题结尾
2. 永远不要直接给出答案，不要总结，不要给出建议
3. 对话过程中绝不调用任何写文件、执行命令等修改操作
4. 你只能使用只读工具：read_file / grep_files / glob_files / list_directory / search_documents / read_argument_graph / read_argument_ledger
5. 如果用户要求你直接给出答案，礼貌拒绝并转回提问
"""

# ---------------------------------------------------------------------------
# Read-only tools whitelist for Socratic mode
# ---------------------------------------------------------------------------

SOCRATIC_ALLOWED_TOOLS = frozenset({
    "read_file",
    "list_directory",
    "grep_files",
    "glob_files",
    "search_documents",
    "read_argument_graph",
    "read_argument_ledger",
})

# ---------------------------------------------------------------------------
# Prompt builder helper
# ---------------------------------------------------------------------------

def build_socratic_prompt() -> str:
    """Return the full Socratic system prompt."""
    return _SOCRATIC_IDENTITY


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

_SOCRATIC_TRIGGERS = (
    "帮我思考", "引导我", "socratic", "socrates",
    "不要直接回答", "引导式", "苏格拉底",
    "help me think", "guide me", "walk me through",
    "teach me how to think about", "思考一下",
    "帮我理清", "帮我厘清", "帮我分析一下我的思路",
    "帮我想想", "启发我", "跟我讨论",
)


def _has_socratic_intent(msg: str) -> bool:
    """Check if the message indicates Socratic guidance intent."""
    ml = msg.lower()
    return any(t.lower() in ml for t in _SOCRATIC_TRIGGERS)


# ---------------------------------------------------------------------------
# Pipeline stage detection
# ---------------------------------------------------------------------------

_STAGE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("research", ["调研", "research", "文献综述", "literature review", "查资料", "找论文",
                   "调研一下", "研究一下", "帮我搜索", "systematic review"]),
    ("outline", ["大纲", "outline", "提纲", "框架", "结构", "目录",
                  "写大纲", "列提纲", "plan"]),
    ("draft", ["初稿", "draft", "写论文", "写文章", "write paper", "write article",
                "写作", "撰写", "起草", "写初稿"]),
    ("review", ["审稿", "review", "评审", "检查论文", "审核", "proofread",
                 "review this"]),
    ("revise", ["修改", "revise", "改写", "润色", "改进", "修改论文",
                 "improve", "enhance", "rewrite", "polish"]),
    ("finalize", ["定稿", "finalize", "提交", "submit", "排版", "format",
                   "导出", "export", "生成pdf", "final version"]),
]


def _detect_pipeline_stage(msg: str) -> str | None:
    """Detect pipeline stage from message text. Returns stage name or None."""
    ml = msg.lower()
    for stage, keywords in _STAGE_KEYWORDS:
        for kw in keywords:
            if kw.lower() in ml:
                return stage
    return None
