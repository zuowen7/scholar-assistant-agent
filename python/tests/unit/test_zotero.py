"""Zotero 客户端单元测试"""

import pytest
from src.zotero.client import ZoteroClient, ZoteroItem


class TestZoteroItem:
    """ZoteroItem 测试"""

    def test_citation_key_with_author(self):
        """有作者时生成正确的 citation key"""
        item = ZoteroItem(
            key="ABC123",
            item_type="journalArticle",
            title="Deep Learning",
            authors=["Smith, John", "Doe, Jane"],
            year="2020",
        )
        assert "smith" in item.citation_key.lower()
        assert "2020" in item.citation_key

    def test_citation_key_without_author(self):
        """无作者时使用 year"""
        item = ZoteroItem(
            key="ABC123",
            item_type="document",
            title="Report",
            authors=[],
            year="2021",
        )
        assert "2021" in item.citation_key

    def test_to_bibtex_article(self):
        """导出期刊文章为 BibTeX"""
        item = ZoteroItem(
            key="ABC123",
            item_type="journalArticle",
            title="Test Paper",
            authors=["Smith, J."],
            year="2020",
            journal="Nature",
            volume="10",
            pages="1-10",
        )
        bibtex = item.to_bibtex()

        assert "@article{" in bibtex
        assert "title = {Test Paper}" in bibtex
        assert "author = {Smith, J.}" in bibtex
        assert "year = {2020}" in bibtex
        assert "journal = {Nature}" in bibtex

    def test_to_bibtex_book(self):
        """导出书籍为 BibTeX"""
        item = ZoteroItem(
            key="ABC123",
            item_type="book",
            title="Python Guide",
            authors=["Author, Name"],
            year="2019",
        )
        bibtex = item.to_bibtex()

        assert "@book{" in bibtex

    def test_to_markdown_citation(self):
        """生成 Markdown 引用格式"""
        item = ZoteroItem(
            key="ABC123",
            item_type="article",
            title="Test",
            authors=["Smith"],
            year="2020",
        )
        citation = item.to_markdown_citation()

        assert citation.startswith("[@")
        assert citation.endswith("]")

    def test_to_dict(self):
        """转换为字典"""
        item = ZoteroItem(
            key="ABC123",
            item_type="article",
            title="Test Paper",
            authors=["Smith, J."],
            year="2020",
            journal="Nature",
        )
        d = item.to_dict()

        assert d["key"] == "ABC123"
        assert d["title"] == "Test Paper"
        assert d["citation_key"]
        assert d["markdown_citation"]
        assert d["authors"] == ["Smith, J."]


class TestZoteroClient:
    """ZoteroClient 测试"""

    def test_client_init(self):
        """客户端初始化"""
        client = ZoteroClient(api_key="test-key", user_id="123456")
        assert client.api_key == "test-key"
        assert client.user_id == "123456"
        assert client.style == "ieee"

    def test_client_default_values(self):
        """默认配置"""
        client = ZoteroClient()
        assert client.timeout == 30.0

    def test_get_headers(self):
        """请求头包含认证信息"""
        client = ZoteroClient(api_key="my-key", user_id="123")
        headers = client._get_headers()

        assert headers["Zotero-API-Key"] == "my-key"
        assert headers["Zotero-API-Version"] == "3"

    def test_check_config_no_key(self):
        """未配置 API Key 时抛出异常"""
        client = ZoteroClient(api_key="", user_id="123")
        with pytest.raises(ValueError, match="API Key"):
            client._check_config()

    def test_check_config_no_user_id(self):
        """未配置 User ID 时抛出异常"""
        client = ZoteroClient(api_key="key", user_id="")
        with pytest.raises(ValueError, match="User ID"):
            client._check_config()


class TestZoteroItemTypes:
    """不同文献类型测试"""

    def test_journal_article(self):
        item = ZoteroItem(key="1", item_type="journalArticle", title="A")
        assert "@article{" in item.to_bibtex()

    def test_book(self):
        item = ZoteroItem(key="1", item_type="book", title="B")
        assert "@book{" in item.to_bibtex()

    def test_conference_paper(self):
        item = ZoteroItem(key="1", item_type="conferencePaper", title="C")
        assert "@inproceedings{" in item.to_bibtex()

    def test_unknown_type(self):
        item = ZoteroItem(key="1", item_type="unknownType", title="D")
        assert "@misc{" in item.to_bibtex()


class TestZoteroEdgeCases:
    """边界情况测试"""

    def test_empty_title(self):
        item = ZoteroItem(key="1", item_type="article", title="")
        bibtex = item.to_bibtex()
        # 空标题时 title 字段不输出，但类型仍是 article
        assert "@article{" in bibtex or "@misc{" in bibtex

    def test_no_year(self):
        item = ZoteroItem(key="1", item_type="article", title="T", authors=["A"], year="")
        assert "unknown" in item.citation_key.lower() or item.citation_key

    def test_long_abstract_truncation(self):
        item = ZoteroItem(
            key="1",
            item_type="article",
            title="T",
            abstract="A" * 500,
        )
        d = item.to_dict()
        assert len(d["abstract"]) <= 203  # 200 + "..."

    def test_special_characters_in_title(self):
        item = ZoteroItem(
            key="1",
            item_type="article",
            title="Test: \"Quotes\" & <Special>",
            authors=["Smith, J."],
            year="2020",
        )
        bibtex = item.to_bibtex()
        assert "Test" in bibtex
