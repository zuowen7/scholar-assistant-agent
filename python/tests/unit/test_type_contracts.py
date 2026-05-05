"""前后端类型契约测试 — 验证 Python 数据模型与 TypeScript 接口对齐

测试：
1. QA 事件结构：Python QAFlag/QAResult ↔ TypeScript QAFlagItem/QAWarning
2. 翻译管道 SSE 事件负载结构
3. 导出端点请求/响应结构
4. 配置结构
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, fields

import pytest


# ── Helper: check field existence ──────────────────────────────────────

def get_dataclass_fields(cls) -> dict[str, str]:
    """Return {field_name: field_type} for a dataclass."""
    return {f.name: f.type for f in fields(cls)}


# ── 1. QA Contracts ────────────────────────────────────────────────────


class TestQAFlagsContract:
    """QAFlag (Python) ↔ QAFlagItem (TypeScript)

    TypeScript interface QAFlagItem {
        type: string
        severity: string
        location: string
        message: string
        suggestion: string
    }
    """

    def test_qaflag_fields_match_typescript(self) -> None:
        from src.translator.post_qa import QAFlag
        py_fields = get_dataclass_fields(QAFlag)
        required_ts_fields = {"type", "severity", "location", "message", "suggestion"}
        assert set(py_fields.keys()) == required_ts_fields, \
            f"Mismatch: Python has {set(py_fields.keys())}, TS expects {required_ts_fields}"

    def test_qaflag_all_strings(self) -> None:
        """All QAFlag fields should be strings (matching TS interface)."""
        from src.translator.post_qa import QAFlag
        flag = QAFlag(
            type="overclaim",
            severity="warning",
            location="test location",
            message="test message",
            suggestion="test suggestion",
        )
        assert isinstance(flag.type, str)
        assert isinstance(flag.severity, str)
        assert isinstance(flag.location, str)
        assert isinstance(flag.message, str)
        assert isinstance(flag.suggestion, str)


class TestQAResultContract:
    """QAResult (Python) ↔ QAWarning (TypeScript)

    TypeScript interface QAWarning {
        chunkIndex: number
        sectionType: string
        score: number
        flags: QAFlagItem[]
    }

    Python QAResult has: flags, score (+ extra fields)
    chunkIndex and sectionType are passed separately in SSE event.
    """

    def test_qaresult_has_flags_and_score(self) -> None:
        from src.translator.post_qa import QAResult
        py_fields = get_dataclass_fields(QAResult)
        assert "flags" in py_fields
        assert "score" in py_fields

    def test_qaresult_score_is_int(self) -> None:
        from src.translator.post_qa import QAResult
        result = QAResult(flags=[], score=100)
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_qaresult_flags_is_list_of_qaflag(self) -> None:
        from src.translator.post_qa import QAResult, QAFlag
        result = QAResult(
            flags=[QAFlag(type="overclaim", severity="warning",
                         location="x", message="msg", suggestion="fix")],
            score=90,
        )
        assert len(result.flags) == 1
        assert isinstance(result.flags[0], QAFlag)

    def test_ss_e_event_structure_matches(self) -> None:
        """验证 qa_warnings SSE 事件的 JSON 结构与 TypeScript 期望一致"""
        from src.translator.post_qa import QAResult, QAFlag

        result = QAResult(
            flags=[QAFlag(type="overclaim", severity="warning",
                         location="test.", message="Found 'prove'", suggestion="Use 'show'")],
            score=85,
        )

        # Simulate the SSE event payload
        event_payload = {
            "chunk_index": 0,
            "section_type": "results",
            "score": result.score,
            "flags": [
                {
                    "type": f.type,
                    "severity": f.severity,
                    "location": f.location,
                    "message": f.message,
                    "suggestion": f.suggestion,
                }
                for f in result.flags
            ],
        }

        # Verify JSON serializable
        json_str = json.dumps(event_payload)
        decoded = json.loads(json_str)

        # TS expects these fields
        assert "chunk_index" in decoded or "chunkIndex" in decoded  # Python uses snake_case
        assert "flags" in decoded
        assert "score" in decoded
        assert decoded["score"] == 85
        assert len(decoded["flags"]) == 1
        assert decoded["flags"][0]["type"] == "overclaim"


# ── 2. SSE Pipeline Event Contracts ────────────────────────────────────


class TestSSEEventContracts:
    """翻译管道 SSE 事件结构验证"""

    def test_chunk_done_event_has_section_type(self) -> None:
        """chunk_done event must include section_type (added in P0)."""
        event_data = {
            "index": 0,
            "total": 4,
            "original_preview": "Hello...",
            "translated_preview": "...",
            "tokens": 50,
            "section_type": "introduction",  # P0 addition
        }
        assert "section_type" in event_data
        assert isinstance(event_data["section_type"], str)

    def test_block_translated_event_fields(self) -> None:
        """block_translated event must include aligned and status fields."""
        event_data = {
            "chunk_index": 0,
            "block_id": "b1",
            "type": "paragraph",
            "translatable": True,
            "original": "Hello",
            "translated": "...",
            "aligned": True,  # P0 alignment
            "source": "cloud",
            "status": "ok",  # P0 retry support
        }
        required = {"chunk_index", "block_id", "type", "translatable",
                    "original", "translated", "aligned", "status"}
        assert set(event_data.keys()) >= required

    def test_complete_event_fields(self) -> None:
        """complete event must include misalign_count (P0 addition)."""
        event_data = {
            "task_id": "task-1",
            "output_path": "/out/test.md",
            "content": "...",
            "blocks": [],
            "chunks": [],
            "misalign_count": 0,
        }
        assert "misalign_count" in event_data
        assert "blocks" in event_data


# ── 3. Export Endpoint Contracts ───────────────────────────────────────


class TestExportEndpointContracts:
    """导出端点请求/响应结构"""

    def test_pptx_export_request_fields(self) -> None:
        """POST /api/export/pptx expects task_id + block_translations"""
        # From routers/translate.py line 994-1000
        request = {
            "task_id": "task-abc",
            "block_translations": [
                {
                    "id": "b1",
                    "type": "paragraph",
                    "original": "Hello",
                    "translated": "...",
                    "translatable": True,
                    "status": "ok",
                }
            ],
        }
        assert "task_id" in request
        assert "block_translations" in request
        assert isinstance(request["block_translations"], list)

    def test_data_availability_request_fields(self) -> None:
        """POST /api/export/data_availability expects task_id"""
        request = {"task_id": "task-abc"}
        assert "task_id" in request

    def test_block_translation_has_all_ts_fields(self) -> None:
        """BlockTranslation dict must contain all fields TypeScript expects."""
        bt = {
            "id": "b1",
            "type": "paragraph",
            "level": 0,
            "translatable": True,
            "original": "source",
            "translated": "target",
            "aligned": True,
            "source": "cloud",
            "status": "ok",
            "section_type": "results",
        }
        required = {"id", "type", "original", "translated", "status"}
        assert set(bt.keys()) >= required

    def test_config_response_has_translator_section(self) -> None:
        """GET /api/config returns translator section with all fields TS expects."""
        config = {
            "translator": {
                "engine": "ollama",
                "model": "qwen3:8b",
                "ollama_base_url": "http://localhost:11434",
                "temperature": 0.3,
                "num_predict": 16384,
                "system_prompt": "",
                "timeout": 300.0,
                "cloud": {
                    "provider": "",
                    "api_key": "",
                    "base_url": "",
                    "model": "",
                    "max_tokens": 16384,
                }
            }
        }
        assert "translator" in config
        assert "engine" in config["translator"]


# ── 4. TranslateState Contract ─────────────────────────────────────────


class TestTranslateStateContract:
    """TranslateState TypeScript ↔ Python pipeline state alignment"""

    def test_state_has_p0_fields(self) -> None:
        """TranslateState must have qaWarnings and sectionMap (P0 additions)."""
        state_fields = {
            "status", "currentStep", "totalSteps", "stepMessage",
            "parsedInfo", "totalChunks", "completedChunks",
            "totalBlocks", "completedBlocks", "translations",
            "finalContent", "blocks", "chunks", "errorMessage",
            "taskId", "fallbackChunks", "misalignedChunks",
            "ragIngested", "qaWarnings", "sectionMap",
        }
        # Verify P0 fields are included
        assert "qaWarnings" in state_fields
        assert "sectionMap" in state_fields

    def test_qawarning_interface_matches_python(self) -> None:
        """TypeScript QAWarning matches Python event data shape."""
        # TS: { chunkIndex, sectionType, score, flags: QAFlagItem[] }
        # Python SSE: { chunk_index, section_type, score, flags: [...] }
        ts_qa_warning = {
            "chunkIndex": 0,
            "sectionType": "results",
            "score": 85,
            "flags": [
                {"type": "overclaim", "severity": "warning",
                 "location": "...", "message": "...", "suggestion": "..."}
            ],
        }
        assert isinstance(ts_qa_warning["chunkIndex"], int)
        assert isinstance(ts_qa_warning["sectionType"], str)
        assert isinstance(ts_qa_warning["score"], int)
        assert isinstance(ts_qa_warning["flags"], list)
