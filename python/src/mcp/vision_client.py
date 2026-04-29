"""MCP Vision Client — 多模态图像理解

支持 Claude Vision API，能够理解：
- 文字识别 (OCR)
- 图表分析 (柱状图、折线图、饼图、流程图)
- 表格识别
- 示意图理解

返回结构化结果，供 Agent 理解和编辑。
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class VisionResult:
    """图像分析结果"""

    def __init__(
        self,
        text: str = "",
        chart_type: str | None = None,
        chart_description: str = "",
        table_data: list[list[str]] | None = None,
        key_findings: list[str] | None = None,
        raw_description: str = "",
    ):
        self.text = text
        self.chart_type = chart_type
        self.chart_description = chart_description
        self.table_data = table_data
        self.key_findings = key_findings or []
        self.raw_description = raw_description

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "chart_type": self.chart_type,
            "chart_description": self.chart_description,
            "table_data": self.table_data,
            "key_findings": self.key_findings,
            "raw_description": self.raw_description,
        }


class VisionClient:
    """MCP 多模态图像理解客户端"""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _load_config(self) -> dict:
        """从配置文件加载云端设置"""
        try:
            import yaml
            config_path = Path(__file__).parent.parent.parent / "config" / "default.yaml"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def _get_credentials(self) -> tuple[str, str, str]:
        """获取认证信息。优先读取 vision 专属配置，其次回退到 translator.cloud。"""
        config = self._load_config()
        vision_cfg = config.get("vision", {})
        cloud_cfg = config.get("translator", {}).get("cloud", {})

        base_url = (vision_cfg.get("base_url", "").rstrip("/")
                    or cloud_cfg.get("base_url", "").rstrip("/")
                    or self.base_url)
        api_key = (self.api_key
                   or vision_cfg.get("api_key", "")
                   or cloud_cfg.get("api_key", ""))
        model = (vision_cfg.get("model", "")
                 or cloud_cfg.get("model", "")
                 or self.model)

        if not api_key:
            import os
            api_key = os.environ.get("OPENAI_API_KEY", "")
            base_url = os.environ.get("OPENAI_BASE_URL", base_url)

        return base_url, api_key, model or "gpt-4o"

    def _encode_image(self, image_path: str | Path) -> str:
        """将图片编码为 base64"""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(f"不支持的图片格式: {ext}")

        with open(path, "rb") as f:
            data = f.read()
            return base64.b64encode(data).decode("utf-8")

    def _is_claude_format(self) -> bool:
        """判断是否使用 Claude 格式"""
        base_url, _, _ = self._get_credentials()
        return "anthropic" in base_url.lower() or "claude" in base_url.lower()

    async def analyze_image(
        self,
        image_path: str | Path,
        analysis_type: Literal["general", "chart", "table", "formula"] = "general",
    ) -> VisionResult:
        """分析图片内容

        Args:
            image_path: 图片路径
            analysis_type: 分析类型
                - general: 通用描述
                - chart: 图表分析
                - table: 表格识别
                - formula: 公式识别

        Returns:
            VisionResult 结构化结果
        """
        base_url, api_key, model = self._get_credentials()

        if not api_key:
            logger.warning("未配置 API Key，返回占位结果")
            return VisionResult(
                text="[需要配置云端 API Key 才能进行图像分析]",
                raw_description="API key not configured",
            )

        try:
            if self._is_claude_format():
                return await self._analyze_claude(image_path, analysis_type)
            else:
                return await self._analyze_openai(image_path, analysis_type)
        except Exception as e:
            logger.error("图像分析失败: %s", e)
            return VisionResult(
                text=f"[图像分析失败: {e}]",
                raw_description=str(e),
            )

    async def _analyze_openai(
        self,
        image_path: str | Path,
        analysis_type: str,
    ) -> VisionResult:
        """使用 OpenAI-compatible Vision API 分析"""
        use_httpx = False
        try:
            import aiohttp
        except ImportError:
            try:
                import httpx
                use_httpx = True
            except ImportError:
                raise ImportError("需要安装 aiohttp 或 httpx")

        base_url, api_key, model = self._get_credentials()
        image_b64 = self._encode_image(image_path)

        # 根据分析类型构建不同的 prompt
        prompts = {
            "general": """请详细描述这张图片的内容，包括：
1. 图片中的主要元素
2. 文字内容（如果有）
3. 整体含义和目的
请用中文回答。""",
            "chart": """这是一个数据图表，请分析：
1. 图表类型（柱状图/折线图/饼图/散点图等）
2. 图表标题和坐标轴标签
3. 主要数据趋势和模式
4. 关键数据点和数值
5. 图表的主要发现或结论
请用中文回答，尽可能提取精确数据。""",
            "table": """这是一个表格或表格形式的图片，请：
1. 提取所有行列数据
2. 识别表头
3. 以 Markdown 表格格式输出
4. 如有合并单元格，请标注
请用中文标注表格含义。""",
            "formula": """这是一个数学公式或表达式，请：
1. 识别公式内容
2. 转换为标准 LaTeX 格式
3. 解释公式含义（变量说明）
请用中文解释。""",
        }

        prompt = prompts.get(analysis_type, prompts["general"])

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{Path(image_path).suffix[1:]};base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

        try:
            if use_httpx:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "max_tokens": 2048,
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "max_tokens": 2048,
                        },
                    ) as resp:
                        resp.raise_for_status()
                        result = await resp.json()

            content = result["choices"][0]["message"]["content"]
            return self._parse_vision_response(content, analysis_type)

        except Exception as e:
            logger.error("Vision API 调用失败: %s", e)
            raise

    async def _analyze_claude(
        self,
        image_path: str | Path,
        analysis_type: str,
    ) -> VisionResult:
        """使用 Claude Vision API 分析"""
        base_url, api_key, _ = self._get_credentials()
        image_b64 = self._encode_image(image_path)

        prompts = {
            "general": "请详细描述这张图片的内容，用中文回答。",
            "chart": "这是一个数据图表，请分析图表类型、数据趋势、关键数值，用中文回答。",
            "table": "这是一个表格图片，请提取所有数据并以 Markdown 表格格式输出，用中文标注含义。",
            "formula": "请识别图片中的数学公式，转换为 LaTeX 格式并解释含义，用中文回答。",
        }

        prompt = prompts.get(analysis_type, prompts["general"])

        try:
            import aiohttp
        except ImportError:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{base_url}/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-3-opus-20240229",
                        "max_tokens": 2048,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": f"image/{Path(image_path).suffix[1:]}",
                                            "data": image_b64,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    },
                                ],
                            }
                        ],
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                content = result["content"][0]["text"]
                return self._parse_vision_response(content, analysis_type)
        else:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-3-opus-20240229",
                        "max_tokens": 2048,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": f"image/{Path(image_path).suffix[1:]}",
                                            "data": image_b64,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    },
                                ],
                            }
                        ],
                    },
                ) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
                    content = result["content"][0]["text"]
                    return self._parse_vision_response(content, analysis_type)

    def _parse_vision_response(self, content: str, analysis_type: str) -> VisionResult:
        """解析 Vision API 返回的内容"""
        result = VisionResult(
            text=content,
            raw_description=content,
        )

        # 尝试识别图表类型
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["柱状图", "bar chart", "柱形"]):
            result.chart_type = "bar"
        elif any(kw in content_lower for kw in ["折线图", "line chart", "曲线"]):
            result.chart_type = "line"
        elif any(kw in content_lower for kw in ["饼图", "pie chart", "圆形"]):
            result.chart_type = "pie"
        elif any(kw in content_lower for kw in ["表格", "table", "|"]):
            result.chart_type = "table"
        elif any(kw in content_lower for kw in ["流程图", "流程", "flow"]):
            result.chart_type = "flowchart"
        elif any(kw in content_lower for kw in ["公式", "equation", "latex", "$", "frac"]):
            result.chart_type = "formula"

        # 尝试提取表格数据
        if "|" in content:
            lines = content.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("|") and stripped.endswith("|"):
                    # 可能是表格行
                    cells = [c.strip() for c in stripped.split("|")[1:-1]]
                    if len(cells) > 1:
                        if result.table_data is None:
                            result.table_data = []
                        result.table_data.append(cells)

        result.chart_description = content[:500] if content else ""

        # 尝试提取关键发现
        finding_keywords = ["主要", "关键", "发现", "结论", "趋势", "结论是", "重要"]
        for keyword in finding_keywords:
            if keyword in content:
                idx = content.find(keyword)
                snippet = content[max(0, idx - 20) : idx + 100]
                result.key_findings.append(snippet.strip())

        return result

    async def ocr_image(self, image_path: str | Path) -> VisionResult:
        """OCR 专用接口 — 识别图片中的文字"""
        return await self.analyze_image(image_path, analysis_type="general")

    async def analyze_chart(self, image_path: str | Path) -> VisionResult:
        """图表分析专用接口"""
        return await self.analyze_image(image_path, analysis_type="chart")

    async def extract_table(self, image_path: str | Path) -> VisionResult:
        """表格提取专用接口"""
        return await self.analyze_image(image_path, analysis_type="table")

    async def recognize_formula(self, image_path: str | Path) -> VisionResult:
        """公式识别专用接口"""
        return await self.analyze_image(image_path, analysis_type="formula")
