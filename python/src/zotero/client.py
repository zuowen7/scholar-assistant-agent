"""Zotero Web API 客户端

支持：
- 搜索文献库
- 获取文献详情
- 导出 BibTeX
- 生成引用格式

使用方式：
1. 云端：在 Zotero 设置中创建 API Key: https://www.zotero.org/settings/keys，
   获取 User ID 并配置到 config/default.yaml
2. 本地：无需配置，启动 Zotero 7 桌面版即可通过本地 API
   （http://localhost:23119）免 Key 搜索文献库

配置示例：
zotero:
  api_key: "your-api-key"
  user_id: "1234567"
  style: "ieee"  # 引用格式: ieee/apa/gbt7714
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# 云端 API 基础 URL
ZOTERO_API_BASE = "https://api.zotero.org"
# Zotero 7 桌面版本地 API（免 Key，仅本机可用）
LOCAL_API_BASE = "http://localhost:23119/api"
# 本地 API 探测超时（秒）
_LOCAL_PROBE_TIMEOUT = 1.5


@dataclass
class ZoteroItem:
    """Zotero 文献条目"""

    key: str
    item_type: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: str = ""
    journal: str = ""
    volume: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    tags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def citation_key(self) -> str:
        """生成 BibTeX 引用 key"""
        if not self.authors:
            return f"{self.year}_unknown" if self.year else "unknown"
        first_author = self.authors[0].split(",")[0].strip().lower()
        first_author = "".join(c for c in first_author if c.isalnum())
        return f"{first_author}{self.year}" if self.year else first_author

    def to_bibtex(self) -> str:
        """导出为 BibTeX 格式"""
        entry_type = self._get_bibtex_type()
        key = self.citation_key

        lines = [f"@{entry_type}{{{key},"]

        if self.title:
            lines.append(f"  title = {{{self.title}}},")
        if self.authors:
            authors_str = " and ".join(self.authors)
            lines.append(f"  author = {{{authors_str}}},")
        if self.year:
            lines.append(f"  year = {{{self.year}}},")
        if self.journal:
            lines.append(f"  journal = {{{self.journal}}},")
        if self.volume:
            lines.append(f"  volume = {{{self.volume}}},")
        if self.pages:
            lines.append(f"  pages = {{{self.pages}}},")
        if self.doi:
            lines.append(f"  doi = {{{self.doi}}},")
        if self.url:
            lines.append(f"  url = {{{self.url}}},")

        lines.append("}")
        return "\n".join(lines)

    def _get_bibtex_type(self) -> str:
        """根据文献类型返回 BibTeX 条目类型"""
        type_map = {
            "journalArticle": "article",
            "book": "book",
            "bookSection": "incollection",
            "conferencePaper": "inproceedings",
            "thesis": "phdthesis",
            "report": "techreport",
            "webpage": "misc",
            "document": "misc",
        }
        return type_map.get(self.item_type, "misc")

    def to_markdown_citation(self) -> str:
        """生成 Markdown 引用格式"""
        return f"[@{self.citation_key}]"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "citation_key": self.citation_key,
            "item_type": self.item_type,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "volume": self.volume,
            "pages": self.pages,
            "doi": self.doi,
            "url": self.url,
            "abstract": self.abstract[:200] + "..." if len(self.abstract) > 200 else self.abstract,
            "tags": self.tags,
            "markdown_citation": self.to_markdown_citation(),
        }


class ZoteroClient:
    """Zotero Web API 客户端"""

    def __init__(
        self,
        api_key: str = "",
        user_id: str = "",
        style: str = "ieee",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.user_id = user_id
        self.style = style
        self.timeout = timeout

        # 从配置文件加载
        self._load_config()

    def _load_config(self) -> None:
        """从配置文件加载 Zotero 设置"""
        try:
            import yaml

            config_path = Path(__file__).parent.parent.parent / "config" / "default.yaml"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                zotero_cfg = config.get("zotero", {})
                self.api_key = self.api_key or zotero_cfg.get("api_key", "")
                self.user_id = self.user_id or zotero_cfg.get("user_id", "")
                self.style = self.style or zotero_cfg.get("style", "ieee")
        except Exception as e:
            logger.warning("加载 Zotero 配置失败: %s", e)

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "Zotero-API-Key": self.api_key,
            "Zotero-API-Version": "3",
        }

    def _check_config(self) -> None:
        """检查配置是否完整（仅云端模式需要）"""
        if not self.api_key:
            raise ValueError(
                "未配置 Zotero API Key，请在 config/default.yaml 中设置 zotero.api_key"
            )
        if not self.user_id:
            raise ValueError(
                "未配置 Zotero User ID，请在 config/default.yaml 中设置 zotero.user_id"
            )

    def _cloud_ready(self) -> bool:
        """云端模式是否可用"""
        return bool(self.api_key and self.user_id)

    def local_available(self) -> bool:
        """Zotero 7 桌面版本地 API 是否可用（免 Key）"""
        try:
            with httpx.Client(timeout=_LOCAL_PROBE_TIMEOUT) as client:
                resp = client.get(
                    f"{LOCAL_API_BASE}/users/0/items",
                    params={"limit": 1, "format": "json"},
                )
                return resp.status_code < 500
        except Exception:
            return False

    def resolve_mode(self) -> str:
        """返回当前可用模式: 'cloud' | 'local' | 'unavailable'"""
        if self._cloud_ready():
            return "cloud"
        if self.local_available():
            return "local"
        return "unavailable"

    def _require_mode(self) -> str:
        """解析模式；完全不可用时抛出可操作的 ValueError"""
        mode = self.resolve_mode()
        if mode == "unavailable":
            raise ValueError(
                "未配置 Zotero API Key，且未检测到本地 Zotero；"
                "请在设置中配置 zotero.api_key / zotero.user_id，或启动 Zotero 7 桌面版"
            )
        return mode

    def _items_base_url(self, mode: str) -> str:
        """按模式返回 items 集合的基础 URL"""
        if mode == "cloud":
            return f"{ZOTERO_API_BASE}/users/{self.user_id}/items"
        return f"{LOCAL_API_BASE}/users/0/items"

    def search(
        self,
        query: str,
        item_type: str | None = None,
        limit: int = 20,
    ) -> list[ZoteroItem]:
        """搜索文献

        Args:
            query: 搜索关键词
            item_type: 限定文献类型（可选）
            limit: 最大返回数量

        Returns:
            文献条目列表
        """
        mode = self._require_mode()

        params = {
            "q": query,
            "format": "json",
            "limit": min(limit, 100),
        }

        if item_type:
            params["itemType"] = item_type

        try:
            with httpx.Client(timeout=self.timeout) as client:
                url = self._items_base_url(mode)
                headers = self._get_headers() if mode == "cloud" else None
                resp = client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

            items = []
            for raw_item in data:
                try:
                    item = self._parse_item(raw_item)
                    items.append(item)
                except Exception as e:
                    logger.warning("解析文献失败: %s", e)
                    continue

            logger.info("Zotero 搜索 '%s' 返回 %d 条结果", query, len(items))
            return items

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise ValueError("Zotero API Key 无效或已过期，请检查配置")
            raise
        except Exception as e:
            logger.error("Zotero 搜索失败: %s", e)
            raise

    def get_item(self, item_key: str) -> ZoteroItem | None:
        """获取单条文献详情

        Args:
            item_key: 文献 key

        Returns:
            文献条目或 None
        """
        mode = self._require_mode()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                url = f"{self._items_base_url(mode)}/{item_key}"
                headers = self._get_headers() if mode == "cloud" else None
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            return self._parse_item(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error("获取 Zotero 文献失败: %s", e)
            raise

    def get_items_by_keys(self, item_keys: list[str]) -> list[ZoteroItem]:
        """批量获取文献

        Args:
            item_keys: 文献 key 列表

        Returns:
            文献条目列表
        """
        mode = self._require_mode()

        if not item_keys:
            return []

        try:
            with httpx.Client(timeout=self.timeout) as client:
                url = self._items_base_url(mode)
                keys_param = ",".join(item_keys)
                headers = self._get_headers() if mode == "cloud" else None
                resp = client.get(
                    url,
                    headers=headers,
                    params={"items": keys_param, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()

            items = []
            for raw_item in data:
                try:
                    item = self._parse_item(raw_item)
                    items.append(item)
                except Exception as e:
                    logger.debug("Skipping malformed Zotero item: %s", e)
                    continue

            return items

        except Exception as e:
            logger.error("批量获取 Zotero 文献失败: %s", e)
            raise

    def export_bibtex(self, item_keys: list[str] | None = None) -> str:
        """导出 BibTeX 格式

        Args:
            item_keys: 要导出的文献 key 列表，None 则导出全部

        Returns:
            BibTeX 格式文本
        """
        mode = self._require_mode()

        if mode == "local":
            # 本地 API 对 format=bibtex 支持不完整，用已解析条目在客户端生成
            if item_keys:
                items = self.get_items_by_keys(item_keys)
            else:
                items = self.search(query="", limit=100)
            return "\n\n".join(item.to_bibtex() for item in items)

        self._check_config()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                url = self._items_base_url(mode)

                params = {"format": "bibtex"}
                if item_keys:
                    params["items"] = ",".join(item_keys)

                resp = client.get(url, headers=self._get_headers(), params=params)
                resp.raise_for_status()

            return resp.text

        except Exception as e:
            logger.error("导出 BibTeX 失败: %s", e)
            raise

    def _parse_item(self, raw: dict) -> ZoteroItem:
        """解析 Zotero API 返回的原始数据"""
        data = raw.get("data", {})
        key = raw.get("key", "")

        # 提取作者
        creators = data.get("creators", [])
        authors = []
        for creator in creators:
            if creator.get("creatorType") == "author":
                if creator.get("lastName"):
                    name = f"{creator.get('firstName', '')}, {creator['lastName']}".strip()
                    if name == ",":
                        name = creator.get("name", "Unknown")
                elif creator.get("name"):
                    name = creator["name"]
                else:
                    name = "Unknown"
                authors.append(name)

        # 提取年份
        date = data.get("date", "")
        year = ""
        if date:
            import re

            year_match = re.search(r"\d{4}", date)
            if year_match:
                year = year_match.group(0)

        return ZoteroItem(
            key=key,
            item_type=data.get("itemType", "document"),
            title=data.get("title", "Untitled"),
            authors=authors,
            year=year,
            journal=data.get("publicationTitle", ""),
            volume=data.get("volume", ""),
            pages=data.get("pages", ""),
            doi=data.get("DOI", ""),
            url=data.get("url", ""),
            abstract=data.get("abstractNote", ""),
            tags=data.get("tags", []),
            raw=data,
        )
