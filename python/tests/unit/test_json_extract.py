"""json_extract — 共享 JSON 提取工具测试。

覆盖从 LLM 输出中提取 JSON 对象/数组的所有边界情况：
纯 JSON、markdown fence 包裹、前后缀说明文字、嵌套结构、多对象取首个。
"""
import pytest


def _import():
    from src.utils.json_extract import extract_json_object, extract_json_array
    return extract_json_object, extract_json_array


# ── extract_json_object ─────────────────────────────────────────────


class TestExtractJsonObject:
    """T1–T8, T13–T14"""

    def test_t1_pure_json_object(self):
        """纯 JSON 对象直接解析。"""
        extract_json_object, _ = _import()
        assert extract_json_object('{"a": 1}') == {"a": 1}

    def test_t2_pure_json_array_returns_none(self):
        """纯 JSON 数组不是对象，返回 None。"""
        extract_json_object, _ = _import()
        assert extract_json_object("[1, 2, 3]") is None

    def test_t3_markdown_fence_wrapped(self):
        """markdown fence包裹的 JSON 对象。"""
        extract_json_object, _ = _import()
        text = '```\n{"a": 1}\n```'
        assert extract_json_object(text) == {"a": 1}

    def test_t4_fence_with_language_identifier(self):
        """带 ```json 语言标识的 fence。"""
        extract_json_object, _ = _import()
        text = '```json\n{"a": 1}\n```'
        assert extract_json_object(text) == {"a": 1}

    def test_t5_prefix_text(self):
        """前有说明文字。"""
        extract_json_object, _ = _import()
        text = 'Here is the JSON:\n{"a": 1}'
        assert extract_json_object(text) == {"a": 1}

    def test_t6_prefix_and_suffix(self):
        """前后都有文字。"""
        extract_json_object, _ = _import()
        text = 'Result: {"a": 1} Done.'
        assert extract_json_object(text) == {"a": 1}

    def test_t7_nested_object(self):
        """嵌套对象正确解析。"""
        extract_json_object, _ = _import()
        text = '{"a": {"b": [1, 2]}}'
        assert extract_json_object(text) == {"a": {"b": [1, 2]}}

    def test_t8_invalid_input_returns_none(self):
        """无 JSON 返回 None。"""
        extract_json_object, _ = _import()
        assert extract_json_object("no json here") is None

    def test_t13_two_objects_takes_first(self):
        """两个 JSON 对象取第一个。"""
        extract_json_object, _ = _import()
        text = 'A: {"x": 1} B: {"y": 2}'
        assert extract_json_object(text) == {"x": 1}

    def test_t14_braces_inside_string(self):
        """花括号在字符串内不算深度。"""
        extract_json_object, _ = _import()
        text = 'text {"a": "val}ue"} end'
        assert extract_json_object(text) == {"a": "val}ue"}

    def test_empty_string_returns_none(self):
        extract_json_object, _ = _import()
        assert extract_json_object("") is None

    def test_whitespace_only_returns_none(self):
        extract_json_object, _ = _import()
        assert extract_json_object("   \n\t  ") is None

    def test_object_with_chinese_values(self):
        """中文值正常解析。"""
        extract_json_object, _ = _import()
        text = '{"title": "你好世界", "count": 3}'
        result = extract_json_object(text)
        assert result == {"title": "你好世界", "count": 3}

    def test_fence_with_prefix_and_suffix(self):
        """fence + 前后缀文字。"""
        extract_json_object, _ = _import()
        text = 'Here is the result:\n```json\n{"a": 1}\n```\nHope this helps!'
        assert extract_json_object(text) == {"a": 1}


# ── extract_json_array ──────────────────────────────────────────────


class TestExtractJsonArray:
    """T9–T12"""

    def test_t9_pure_json_array(self):
        """纯 JSON 数组。"""
        _, extract_json_array = _import()
        assert extract_json_array("[1, 2, 3]") == [1, 2, 3]

    def test_t10_fence_wrapped(self):
        """markdown fence 包裹。"""
        _, extract_json_array = _import()
        text = '```json\n[{"a": 1}]\n```'
        assert extract_json_array(text) == [{"a": 1}]

    def test_t11_prefix_and_suffix(self):
        """前后缀文字。"""
        _, extract_json_array = _import()
        text = 'Points:\n[{"a": 1}]\nEnd'
        assert extract_json_array(text) == [{"a": 1}]

    def test_t12_empty_array(self):
        """空数组。"""
        _, extract_json_array = _import()
        assert extract_json_array("[]") == []

    def test_pure_object_returns_none(self):
        """纯 JSON 对象不是数组，返回 None。"""
        _, extract_json_array = _import()
        assert extract_json_array('{"a": 1}') is None

    def test_array_with_prefix_text(self):
        """常见 LLM 前缀 + 数组。"""
        _, extract_json_array = _import()
        text = 'I found the following issues:\n```json\n[{"severity": "major", "title": "test"}]\n```'
        result = extract_json_array(text)
        assert len(result) == 1
        assert result[0]["severity"] == "major"

    def test_gemini_style_output(self):
        """Gemini 风格输出：说明文字 + fence + 后缀。"""
        _, extract_json_array = _import()
        text = (
            "Here is the analysis:\n\n"
            "```json\n"
            '[{"category": "method", "title": "T1"}]\n'
            "```\n\n"
            "Let me know if you need more details."
        )
        result = extract_json_array(text)
        assert len(result) == 1
        assert result[0]["category"] == "method"

    def test_array_with_nested_objects(self):
        """嵌套对象数组。"""
        _, extract_json_array = _import()
        text = '[{"a": {"b": 1}}, {"c": [2, 3]}]'
        result = extract_json_array(text)
        assert len(result) == 2
        assert result[0] == {"a": {"b": 1}}
        assert result[1] == {"c": [2, 3]}

    def test_invalid_input_returns_none(self):
        _, extract_json_array = _import()
        assert extract_json_array("no array here") is None

    def test_empty_string_returns_none(self):
        _, extract_json_array = _import()
        assert extract_json_array("") is None
