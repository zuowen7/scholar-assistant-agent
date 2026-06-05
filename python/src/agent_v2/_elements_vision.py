"""Vision integration — Agent image/chart analysis via Vision API."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _get_vision_client():
    """获取 Vision 客户端实例"""
    try:
        from src.mcp.vision_client import VisionClient
        return VisionClient()
    except ImportError:
        return None


async def _analyze_image_async(image_path: str, analysis_type: str = "general") -> dict:
    """异步分析图片"""
    client = _get_vision_client()
    if client is None:
        return {
            "success": False,
            "error": "Vision 客户端不可用，请确保已安装必要的依赖",
        }

    try:
        result = await client.analyze_image(image_path, analysis_type=analysis_type)
        return {
            "success": True,
            "analysis_type": analysis_type,
            "text": result.text,
            "chart_type": result.chart_type,
            "chart_description": result.chart_description,
            "table_data": result.table_data,
            "key_findings": result.key_findings,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def analyze_image_with_vision(image_path: str) -> str:
    """使用 Vision API 分析图片内容。

    识别图片中的文字、图表数据、关键发现等，帮助 Agent 理解图片。
    需要配置云端 API Key。

    Args:
        image_path: 图片文件的绝对路径（不支持远程 URL）。

    Returns:
        图片分析结果，包含识别的文字、图表类型、关键发现等。
    """
    result = asyncio.run(_analyze_image_async(image_path, "general"))

    if not result.get("success"):
        return f"图片分析失败: {result.get('error', '未知错误')}"

    lines = ["【图片分析结果】"]
    if result.get("text"):
        lines.append(f"\n识别的文字内容:\n{result['text']}")
    if result.get("chart_type"):
        lines.append(f"\n图表类型: {result['chart_type']}")
        if result.get("chart_description"):
            lines.append(f"图表描述: {result['chart_description']}")
    if result.get("key_findings"):
        lines.append("\n关键发现:")
        for finding in result["key_findings"][:5]:
            lines.append(f"- {finding}")

    return "\n".join(lines)


def analyze_chart_image(image_path: str) -> str:
    """使用 Vision API 分析图表图片。

    专门分析柱状图、折线图、饼图等数据图表，提取数据趋势和关键发现。
    需要配置云端 API Key。

    Args:
        image_path: 图表图片文件的绝对路径。

    Returns:
        图表分析结果，包含图表类型、数据趋势、关键数值等。
    """
    result = asyncio.run(_analyze_image_async(image_path, "chart"))

    if not result.get("success"):
        return f"图表分析失败: {result.get('error', '未知错误')}"

    lines = ["【图表分析结果】"]

    chart_type = result.get("chart_type", "未知")
    type_names = {
        "bar": "柱状图",
        "line": "折线图",
        "pie": "饼图",
        "scatter": "散点图",
        "table": "表格",
        "flowchart": "流程图",
    }
    lines.append(f"\n图表类型: {type_names.get(chart_type, chart_type)}")

    if result.get("chart_description"):
        lines.append(f"\n详细描述:\n{result['chart_description']}")

    if result.get("table_data"):
        lines.append("\n提取的表格数据:")
        for row in result["table_data"][:10]:
            lines.append(" | ".join(str(c) for c in row))

    if result.get("key_findings"):
        lines.append("\n关键发现:")
        for finding in result["key_findings"][:5]:
            lines.append(f"- {finding}")

    return "\n".join(lines)
