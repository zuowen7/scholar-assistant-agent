from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.translate import register_translate
from src.translator._helpers import TranslationResult


class _RetryClient:
    def set_document_context(self, _context: str) -> None:
        pass

    def translate(self, text: str, _context: str) -> TranslationResult:
        return TranslationResult(
            original=text,
            translated="该结果表明，重试后的真实译文已经同步到最终输出和导出数据。",
            model="test-provider",
        )

    def close(self) -> None:
        pass


def test_retry_refreshes_chunk_content_and_qa(tmp_path: Path) -> None:
    app = FastAPI()
    config = {
        "translator": {
            "engine": "cloud",
            "source_lang": "en",
            "cloud": {"api_key": "test-key"},
        },
        "formatter": {"output_format": "bilingual"},
    }
    state = register_translate(
        app,
        cloud_only=True,
        load_config=lambda: config,
        save_config=lambda _value: None,
        build_cloud_client=lambda _trans, _cloud: _RetryClient(),
        mask_api_key=lambda value: value,
        is_masked=lambda _value: False,
        validate_file_path=lambda value: Path(value),
        runtime_dir=tmp_path,
        rag_store_getter=lambda: None,
    )

    original = "This result demonstrates that the retry path updates every derived translation artifact."
    output_path = tmp_path / "data_cloud" / "output" / "task-retry_translated.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("stale output", encoding="utf-8")
    state["tasks"]["task-retry"] = {
        "status": "done_with_warnings",
        "block_translations": [{
            "id": "b1",
            "type": "paragraph",
            "translatable": True,
            "original": original,
            "translated": "",
            "status": "failed",
        }],
        "block_chunk_map": {"b1": 0},
        "chunk_blocks": {"0": ["b1"]},
        "chunk_sections": {"0": "results"},
        "chunks": [{"original": original, "translated": original}],
        "output_path": str(output_path),
        "fallback_count": 1,
        "misalign_count": 0,
        "source_lang": "en",
    }

    response = TestClient(app).post(
        "/api/translate/task-retry/retry_block",
        json={"block_id": "b1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["chunk_index"] == 0
    assert payload["chunks"][0]["translated"] == payload["translated"]
    assert payload["qa_warning"]["chunk_index"] == 0
    assert payload["qa_warning"]["section_type"] == "results"
    assert payload["fallback_count"] == 0
    assert payload["translated"] in payload["content"]
    assert output_path.read_text(encoding="utf-8") == payload["content"]
    assert state["tasks"]["task-retry"]["status"] == "done"

    repeated = TestClient(app).post(
        "/api/translate/task-retry/retry_block",
        json={"block_id": "b1"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["fallback_count"] == 0
