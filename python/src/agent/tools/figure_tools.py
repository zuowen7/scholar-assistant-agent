"""科研图表生成工具 — 让 Agent 能够根据用户描述生成发表级别的科学图表。

借鉴 nature-figure 的核心方法：
- Figure Contract: 先定核心结论→证据链→图表原型→发表规格，再写代码
- 配色方案: Nature 语义色板，统一方法族色系
- 排版规则: Arial/DejaVu Sans, SVG fonttype='none', 7pt 基础字号
- 多面板布局: hero panel + 从属证据面板
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Nature 风格默认配色 ───────────────────────────────────────────────────────

_NATURE_PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE",
    "green_2": "#AADCA9",
    "green_3": "#8BCF8B",
    "red_1": "#F6CFCB",
    "red_2": "#E9A6A1",
    "red_strong": "#B64342",
    "neutral_light": "#CFCECE",
    "neutral_mid": "#767676",
    "neutral_dark": "#4D4D4D",
    "neutral_black": "#272727",
    "gold": "#FFD700",
    "teal": "#42949E",
    "violet": "#9A4D8E",
}

_DEFAULT_COLORS = [
    _NATURE_PALETTE["blue_main"],
    _NATURE_PALETTE["green_3"],
    _NATURE_PALETTE["red_strong"],
    _NATURE_PALETTE["teal"],
    _NATURE_PALETTE["violet"],
    _NATURE_PALETTE["neutral_light"],
]


# ── matplotlib 脚本模板 ───────────────────────────────────────────────────────

_FIGURE_SCRIPT_TEMPLATE = '''"""
Auto-generated scientific figure script.
Figure type: {figure_type}
Claim: {figure_claim}
"""

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

# ── Nature-style rcParams ──
mpl.rcParams.update({{
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": {font_size},
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "legend.frameon": False,
}})

# ── Nature semantic palette ──
PALETTE = {palette}

DEFAULT_COLORS = {default_colors}

# ── Data (placeholder — replace with actual data) ──
{data_section}

# ── Figure ──
{plot_code}

# ── Export ──
{export_code}
'''


# ── 图表类型简要指南 ───────────────────────────────────────────────────────────

_FIGURE_TYPE_GUIDE = {
    "bar": {
        "description": "柱状图 / 分组柱状图",
        "archetype": "quantitative grid",
        "font_size": 7,
        "hero_rule": "按降序排列，hero 分组用深色",
    },
    "line": {
        "description": "折线图 / 趋势图",
        "archetype": "quantitative grid",
        "font_size": 7,
        "hero_rule": "hero 线用最粗 stroke + 主色",
    },
    "scatter": {
        "description": "散点图 / 气泡图",
        "archetype": "quantitative grid",
        "font_size": 7,
        "hero_rule": "hero 数据点用最高不透明度",
    },
    "heatmap": {
        "description": "热力图 / 矩阵",
        "archetype": "quantitative grid",
        "font_size": 6,
        "hero_rule": "使用连续色板，标注关键数值",
    },
    "distribution": {
        "description": "分布图 (histogram / KDE / violin)",
        "archetype": "quantitative grid",
        "font_size": 7,
        "hero_rule": "hero 分布填充不透明度最高",
    },
    "multipanel": {
        "description": "多面板组合图",
        "archetype": "asymmetric mixed-modality",
        "font_size": 7,
        "hero_rule": "1 个 hero panel 占 50%+ 空间，其余为从属证据",
    },
}


def build_figure_script(
    figure_type: str = "bar",
    figure_claim: str = "",
    data_description: str = "",
    panel_layout: str = "single",
) -> str:
    """根据参数生成 matplotlib 图表脚本。

    Args:
        figure_type: 图表类型 (bar / line / scatter / heatmap / distribution / multipanel)
        figure_claim: 图表的核心主张（一句话）
        data_description: 数据结构描述
        panel_layout: 面板布局（single / grid / asymmetric）

    Returns:
        完整的 Python 脚本字符串
    """
    guide = _FIGURE_TYPE_GUIDE.get(figure_type, _FIGURE_TYPE_GUIDE["bar"])
    font_size = guide.get("font_size", 7)

    # 数据代码段
    data_section = "# TODO: Replace with actual data\n"
    if data_description:
        data_section += f"# Data description: {data_description}\n"
    data_section += (
        "categories = ['A', 'B', 'C', 'D']\n"
        "values = [1.0, 2.3, 1.8, 3.1]\n"
        "errors = [0.1, 0.2, 0.15, 0.25]\n"
    )

    # 绘图代码段
    if figure_type == "bar":
        plot_code = (
            "fig, ax = plt.subplots(figsize=(6, 4))\n"
            "bars = ax.bar(categories, values, color=DEFAULT_COLORS[:len(categories)],\n"
            "               edgecolor='white', linewidth=0.5)\n"
            "ax.errorbar(categories, values, yerr=errors, fmt='none',\n"
            "            ecolor=PALETTE['neutral_mid'], capsize=3, linewidth=0.8)\n"
            "ax.set_ylabel('Value')\n"
            "ax.set_xlabel('Category')\n"
            "# Direct labels — prefer over legends when spatially fixed\n"
            "for bar, val in zip(bars, values):\n"
            "    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,\n"
            "            f'{val:.1f}', ha='center', va='bottom', fontsize=6)\n"
        )
    elif figure_type == "line":
        plot_code = (
            "fig, ax = plt.subplots(figsize=(6, 4))\n"
            "x = np.arange(len(categories))\n"
            "ax.plot(x, values, 'o-', color=PALETTE['blue_main'],\n"
            "        linewidth=2.0, markersize=6, label='Main')\n"
            "ax.fill_between(x, [v-e for v,e in zip(values, errors)],\n"
            "                [v+e for v,e in zip(values, errors)],\n"
            "                color=PALETTE['blue_main'], alpha=0.15)\n"
            "ax.set_xticks(x)\n"
            "ax.set_xticklabels(categories)\n"
            "ax.set_ylabel('Value')\n"
        )
    elif figure_type == "scatter":
        plot_code = (
            "fig, ax = plt.subplots(figsize=(6, 5))\n"
            "sizes = [v*80 for v in values]  # bubble size proportional\n"
            "ax.scatter(categories, values, s=sizes, c=DEFAULT_COLORS[:len(categories)],\n"
            "           alpha=0.75, edgecolors='white', linewidth=0.5)\n"
            "ax.set_ylabel('Value')\n"
        )
    elif figure_type == "heatmap":
        plot_code = (
            "fig, ax = plt.subplots(figsize=(6, 5))\n"
            "matrix = np.array([values, [v*0.8 for v in values],\n"
            "                   [v*1.2 for v in values], [v*0.9 for v in values]])\n"
            "im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')\n"
            "cbar = plt.colorbar(im, ax=ax, shrink=0.8)\n"
            "cbar.ax.tick_params(labelsize=6)\n"
            "ax.set_xticks(range(len(categories)))\n"
            "ax.set_xticklabels(categories, fontsize=6)\n"
            "ax.set_yticks(range(4))\n"
            "ax.set_yticklabels(['R1', 'R2', 'R3', 'R4'], fontsize=6)\n"
        )
    else:
        plot_code = (
            "fig, ax = plt.subplots(figsize=(6, 4))\n"
            "ax.bar(categories, values, color=DEFAULT_COLORS[:len(categories)])\n"
            "ax.set_ylabel('Value')\n"
        )

    # 导出代码段
    export_code = (
        "output_dir = Path(__file__).resolve().parent / 'output'\n"
        "output_dir.mkdir(exist_ok=True)\n"
        "for fmt, dpi in [('svg', None), ('pdf', None), ('png', 300)]:\n"
        "    path = output_dir / f'figure.{{fmt}}'\n"
        "    fig.savefig(path, dpi=dpi, bbox_inches='tight')\n"
        "    print(f'Saved: {{path}}')\n"
        "plt.close()\n"
    )

    return _FIGURE_SCRIPT_TEMPLATE.format(
        figure_type=figure_type,
        figure_claim=figure_claim or "TODO: define the one-sentence claim this figure defends",
        font_size=font_size,
        palette=json.dumps(_NATURE_PALETTE, indent=4),
        default_colors=json.dumps(_DEFAULT_COLORS),
        data_section=data_section,
        plot_code=plot_code,
        export_code=export_code,
    )


def generate_figure(
    figure_type: str = "bar",
    figure_claim: str = "",
    data_description: str = "",
    output_dir: str | Path = "",
) -> str:
    """生成并执行科研图表脚本。

    Args:
        figure_type: 图表类型
        figure_claim: 图表的核心主张
        data_description: 数据结构描述
        output_dir: 输出目录

    Returns:
        执行结果描述（包含生成的文件路径）
    """
    script = build_figure_script(
        figure_type=figure_type,
        figure_claim=figure_claim,
        data_description=data_description,
    )

    # 写入临时脚本
    tmp_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="fig_"))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    script_path = tmp_dir / "figure_script.py"

    # 在脚本开头添加必要的 import
    full_script = (
        "from pathlib import Path\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')  # non-interactive backend\n\n"
        + script
    )
    script_path.write_text(full_script, encoding="utf-8")

    # 执行脚本
    try:
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(tmp_dir),
        )
        output_files = list(tmp_dir.glob("output/*"))
        files_str = "\n".join(f"  - {f}" for f in output_files) if output_files else "无输出文件"

        if result.returncode == 0:
            return (
                f"图表生成成功！\n\n"
                f"类型: {_FIGURE_TYPE_GUIDE.get(figure_type, {}).get('description', figure_type)}\n"
                f"核心主张: {figure_claim or '(未指定)'}\n"
                f"输出目录: {tmp_dir / 'output'}\n"
                f"生成文件:\n{files_str}\n\n"
                f"脚本路径: {script_path}\n"
                f"(替换其中的占位数据后重新运行以获得实际图表)"
            )
        else:
            return (
                f"图表脚本已生成但执行出错:\n"
                f"stderr:\n{result.stderr[:500]}\n\n"
                f"stdout:\n{result.stdout[:500]}\n\n"
                f"脚本路径: {script_path}\n"
                f"(请检查数据格式和依赖后重试)"
            )
    except subprocess.TimeoutExpired:
        return f"图表脚本执行超时（60秒）。脚本路径: {script_path}"
    except FileNotFoundError:
        return (
            f"图表脚本已生成，但系统中未找到 Python 或 matplotlib。\n"
            f"请安装: pip install matplotlib numpy\n"
            f"脚本路径: {script_path}"
        )


def list_figure_types() -> str:
    """列出所有支持的图表类型及其描述"""
    lines = ["支持的图表类型:"]
    for ft, guide in _FIGURE_TYPE_GUIDE.items():
        lines.append(
            f"  - {ft}: {guide['description']} "
            f"(archetype={guide['archetype']}, font_size={guide['font_size']})"
        )
    return "\n".join(lines)
