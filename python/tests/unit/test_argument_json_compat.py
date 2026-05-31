"""argument 模块 JSON 解析兼容性测试。

验证 ai_ops / ledger / reviewer / critique 中的 JSON 提取
在 LLM 添加前后缀文字、markdown fence 时能正确工作。
"""
import json
import pytest

from src.utils.json_extract import extract_json_object, extract_json_array


# ── ai_ops 模拟：extractArgument 场景 ───────────────────────────────


class TestAiOpsJsonCompat:
    def test_t1_preamble_before_json(self):
        """ai_ops: 前缀说明文字不影响提取。"""
        raw = '以下是提取的论证结构：\n{"candidates": [{"local_id": "n1", "type": "claim", "text": "test"}]}'
        result = extract_json_object(raw)
        assert result is not None
        assert len(result["candidates"]) == 1

    def test_t1b_with_fence(self):
        """ai_ops: fence 包裹的 JSON。"""
        raw = '```json\n{"candidates": [], "suggested_edges": []}\n```'
        result = extract_json_object(raw)
        assert result is not None
        assert "candidates" in result

    def test_t1c_suggest_nodes_with_preamble(self):
        """ai_ops suggest_nodes: Gemini 风格前缀。"""
        raw = (
            "Here are the suggested nodes:\n\n"
            '```json\n{"candidates": [{"local_id": "n1", "type": "grounds", "text": "evidence"}], '
            '"suggested_edges": []}\n```\n\n'
            "These suggestions are based on the argument structure."
        )
        result = extract_json_object(raw)
        assert result is not None
        assert result["candidates"][0]["type"] == "grounds"


# ── ledger 模拟：build_ledger 场景 ──────────────────────────────────


class TestLedgerJsonCompat:
    def test_t2_promise_extraction_with_suffix(self):
        """ledger: promise 提取带后缀。"""
        raw = '{"promises": [{"local_id": "p1", "kind": "contribution", "text": "test claim"}]}\n以上是识别到的承诺。'
        result = extract_json_object(raw)
        assert result is not None
        assert len(result["promises"]) == 1

    def test_t2b_promise_with_fence(self):
        """ledger: promise 提取带 fence。"""
        raw = '```json\n{"promises": [{"local_id": "p1", "kind": "contribution", "text": "claim"}]}\n```'
        result = extract_json_object(raw)
        assert result is not None

    def test_t3_discharge_array_with_preamble(self):
        """ledger: discharge 数组提取带前缀。"""
        raw = '兑付结果如下：\n[{"promise_local_id": "p1", "status": "discharged"}]'
        result = extract_json_array(raw)
        assert result is not None
        assert len(result) == 1
        assert result[0]["status"] == "discharged"

    def test_t3b_discharge_empty_array(self):
        """ledger: 空数组。"""
        raw = "No discharges found: []"
        result = extract_json_array(raw)
        assert result == []

    def test_t3c_discharge_with_fence(self):
        """ledger: fence 包裹的数组。"""
        raw = '```\n[{"promise_local_id": "p1", "status": "partial"}]\n```'
        result = extract_json_array(raw)
        assert result is not None
        assert result[0]["status"] == "partial"


# ── reviewer _parse_llm_points 场景 ────────────────────────────────


class TestReviewerJsonCompat:
    def test_t4_gemini_style_fence_with_prefix(self):
        """_parse_llm_points: Gemini 风格 fence + 前缀。"""
        raw = (
            "Here is the analysis:\n\n"
            "```json\n"
            '[{"severity": "major", "category": "method", "title": "T1", "detail": "D1"}]\n'
            "```\n\n"
            "Let me know if you need more details."
        )
        result = extract_json_array(raw)
        assert result is not None
        assert len(result) == 1
        assert result[0]["category"] == "method"

    def test_t5_fence_with_json_identifier(self):
        """_parse_llm_points: ```json 开头。"""
        raw = '```json\n[{"severity": "minor", "category": "writing", "title": "T", "detail": "D"}]\n```'
        result = extract_json_array(raw)
        assert result is not None
        assert result[0]["severity"] == "minor"

    def test_t6_empty_array_with_prefix(self):
        """_parse_llm_points: 前缀 + 空数组。"""
        raw = "No issues found: []"
        result = extract_json_array(raw)
        assert result == []

    def test_t7_import_reviews_pure_json(self):
        """import_real_reviews: 纯 JSON 回归。"""
        raw = json.dumps([
            {"quote_from_paper": "test quote", "point": "test point", "severity": "major"}
        ])
        result = extract_json_array(raw)
        assert result is not None
        assert len(result) == 1


# ── critique 模拟场景 ───────────────────────────────────────────────


class TestCritiqueJsonCompat:
    def test_array_with_explanation(self):
        """critique: 数组前后有说明文字。"""
        raw = (
            "I found the following issues:\n"
            '[{"node_id": "n1", "severity": "warning", "message": "weak claim"}]\n'
            "Please address these."
        )
        result = extract_json_array(raw)
        assert result is not None
        assert result[0]["node_id"] == "n1"
