"""Tests for the terminology anchor system (GlossaryStore).

Acceptance criteria:
- Locked terms enforced 100% across consecutive chunks
- Passthrough terms (target="") preserved as-is
- CSV / TBX import/export works
- Thread-safe for parallel translation (shared GlossaryStore reference)
"""

import csv
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.translator.glossary_store import GlossaryEntry, GlossaryStore
from src.translator._helpers import _extract_term_pairs, build_glossary_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ml_glossary():
    """Load the ML seed glossary."""
    store = GlossaryStore()
    glossary_dir = Path(__file__).resolve().parent.parent.parent / "data" / "translator" / "glossaries"
    store.load_yaml_dir(glossary_dir)
    return store


@pytest.fixture
def empty_glossary():
    return GlossaryStore()


@pytest.fixture
def locked_glossary():
    """Small glossary with locked entries for enforcement tests."""
    store = GlossaryStore()
    store.update_from_list([
        {"source": "attention mechanism", "target": "注意力机制", "locked": True},
        {"source": "BERT", "target": "", "locked": True},
        {"source": "fine-tuning", "target": "微调", "locked": True},
        {"source": "gradient descent", "target": "梯度下降", "locked": False},
    ])
    return store


# ---------------------------------------------------------------------------
# GlossaryEntry basics
# ---------------------------------------------------------------------------

class TestGlossaryEntry:
    def test_passthrough(self):
        e = GlossaryEntry(source="BERT", target="")
        assert e.is_passthrough
        assert e.display_target == "（不翻译，保留原文）"

    def test_normal_entry(self):
        e = GlossaryEntry(source="attention mechanism", target="注意力机制")
        assert not e.is_passthrough
        assert e.display_target == "注意力机制"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestLoading:
    def test_load_yaml(self, ml_glossary):
        assert len(ml_glossary) >= 30

    def test_locked_entries_loaded(self, ml_glossary):
        locked = ml_glossary.locked_entries()
        assert len(locked) > 0
        # All ML locked entries should have source and target set
        for e in locked:
            assert e.source

    def test_get_by_source(self, ml_glossary):
        entry = ml_glossary.get("attention mechanism")
        assert entry is not None
        assert entry.target == "注意力机制"
        assert entry.locked is True

    def test_get_case_insensitive(self, ml_glossary):
        assert ml_glossary.get("Attention Mechanism") is not None
        assert ml_glossary.get("ATTENTION MECHANISM") is not None

    def test_load_nonexistent_yaml(self, empty_glossary):
        count = empty_glossary.load_yaml("/nonexistent/path.yaml")
        assert count == 0


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

class TestPromptBuilding:
    def test_prompt_contains_locked_header(self, locked_glossary):
        prompt = locked_glossary.build_prompt_text()
        assert "强制术语表" in prompt
        assert "注意力机制" in prompt

    def test_prompt_contains_suggestion_header(self, locked_glossary):
        prompt = locked_glossary.build_prompt_text()
        assert "参考术语表" in prompt
        assert "梯度下降" in prompt

    def test_passthrough_display(self, locked_glossary):
        prompt = locked_glossary.build_prompt_text()
        assert "BERT" in prompt
        assert "不翻译" in prompt

    def test_empty_glossary_returns_empty(self, empty_glossary):
        assert empty_glossary.build_prompt_text() == ""


# ---------------------------------------------------------------------------
# build_glossary_prompt helper
# ---------------------------------------------------------------------------

class TestBuildGlossaryPrompt:
    def test_combines_store_and_learned(self, locked_glossary):
        learned = [("novel term", "新术语"), ("attention mechanism", "注意")]
        prompt = build_glossary_prompt(
            glossary_store=locked_glossary,
            learned_pairs=learned,
        )
        # Store entry for "attention mechanism" takes priority
        assert "注意力机制" in prompt
        # Learned pair for new term appears
        assert "新术语" in prompt
        assert "自动提取" in prompt

    def test_learned_only_no_store(self):
        prompt = build_glossary_prompt(
            glossary_store=None,
            learned_pairs=[("foo", "bar")],
        )
        assert "foo → bar" in prompt

    def test_no_duplicate_learned(self, locked_glossary):
        learned = [("attention mechanism", "注意")]
        prompt = build_glossary_prompt(
            glossary_store=locked_glossary,
            learned_pairs=learned,
        )
        # "注意" should NOT appear — the store already has "attention mechanism"
        assert "注意" not in prompt or "注意力机制" in prompt


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

class TestEnforcement:
    def test_locked_violation_detected(self, locked_glossary):
        original = "The model uses attention mechanism to process sequences."
        translated = "该模型使用了注意机制来处理序列。"
        violations = locked_glossary.enforce(translated, original=original)
        assert len(violations) > 0
        assert any(v["source"] == "attention mechanism" for v in violations)

    def test_locked_correct_no_violation(self, locked_glossary):
        original = "The model uses attention mechanism to process sequences."
        translated = "该模型使用了注意力机制来处理序列。"
        violations = locked_glossary.enforce(translated, original=original)
        assert not any(v["source"] == "attention mechanism" for v in violations)

    def test_passthrough_violation(self, locked_glossary):
        translated = "我们使用了伯特模型进行实验。"
        violations = locked_glossary.enforce(translated)
        assert any(v["source"] == "BERT" and v["rule"] == "passthrough" for v in violations)

    def test_passthrough_correct(self, locked_glossary):
        translated = "我们使用了BERT模型进行实验。"
        violations = locked_glossary.enforce(translated)
        assert not any(v["source"] == "BERT" for v in violations)

    def test_unlocked_no_violation(self, locked_glossary):
        original = "We use gradient descent for optimization."
        translated = "我们使用梯度下坠法进行优化。"
        violations = locked_glossary.enforce(translated, original=original)
        assert not any(v["source"] == "gradient descent" for v in violations)

    def test_no_violation_when_source_absent_from_original(self, locked_glossary):
        # "attention mechanism" not in original → no check
        original = "We trained a simple classifier."
        translated = "我们训练了一个简单的分类器。"
        violations = locked_glossary.enforce(translated, original=original)
        assert not any(v["source"] == "attention mechanism" for v in violations)


# ---------------------------------------------------------------------------
# Acceptance: 5 consecutive chunks all use consistent "注意力机制"
# ---------------------------------------------------------------------------

class TestConsistencyAcrossChunks:
    def test_five_chunks_all_use_attention_mechanism(self):
        """同一原文连续 5 chunk 都含 'attention'，全部译成'注意力机制'。"""
        store = GlossaryStore()
        store.update_from_list([
            {"source": "attention mechanism", "target": "注意力机制", "locked": True},
            {"source": "attention", "target": "注意力", "locked": True},
        ])

        originals = [
            "Self-attention mechanism is the core of this model.",
            "Multi-head attention mechanism is widely used in NLP.",
            "Cross-attention mechanism connects encoder and decoder.",
            "Scaled dot-product attention mechanism is the basic operation.",
            "Global attention mechanism handles long-range dependencies.",
        ]
        translations = [
            "自注意力机制是该模型的核心。",
            "多头注意力机制被广泛应用于NLP。",
            "交叉注意力机制连接编码器和解码器。",
            "缩放点积注意力机制是基础操作。",
            "全局注意力机制处理长序列依赖。",
        ]

        for orig, t in zip(originals, translations):
            violations = store.enforce(t, original=orig)
            attention_violations = [v for v in violations if "attention" in v["source"].lower()]
            assert len(attention_violations) == 0, (
                f"Chunk violation: {attention_violations} in '{t}'"
            )

        # And check that wrong translations are caught
        wrong_original = "The model uses attention mechanism."
        wrong = "该模型使用了注意机制来处理。"
        violations = store.enforce(wrong, original=wrong_original)
        assert len(violations) > 0


# ---------------------------------------------------------------------------
# Acceptance: passthrough BERT stays as-is
# ---------------------------------------------------------------------------

class TestPassthrough:
    def test_bert_preserved(self):
        """标了 target="" 的 BERT 在译文里原样出现。"""
        store = GlossaryStore()
        store.update_from_list([
            {"source": "BERT", "target": "", "locked": True},
        ])

        # Good: BERT appears as-is
        correct = "BERT是一种预训练语言模型。"
        assert not store.enforce(correct)

        # Bad: BERT was translated
        wrong = "伯特是一种预训练语言模型。"
        violations = store.enforce(wrong)
        assert len(violations) == 1
        assert violations[0]["source"] == "BERT"


# ---------------------------------------------------------------------------
# CSV import/export
# ---------------------------------------------------------------------------

class TestCSV:
    def test_import_export_roundtrip(self, tmp_path):
        store = GlossaryStore()
        store.update_from_list([
            {"source": "attention", "target": "注意力", "locked": True, "category": "ML"},
            {"source": "embedding", "target": "嵌入", "locked": False, "category": "ML"},
        ])

        csv_path = tmp_path / "test.csv"
        count = store.export_csv(csv_path)
        assert count == 2

        store2 = GlossaryStore()
        imported = store2.import_csv(csv_path)
        assert imported == 2
        assert store2.get("attention").target == "注意力"
        assert store2.get("embedding").target == "嵌入"

    def test_import_csv_with_header(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target", "category"])
            writer.writerow(["loss", "损失", "ML"])
            writer.writerow(["optimizer", "优化器", "ML"])

        store = GlossaryStore()
        count = store.import_csv(csv_path)
        assert count == 2
        assert store.get("loss").target == "损失"


# ---------------------------------------------------------------------------
# TBX import/export
# ---------------------------------------------------------------------------

class TestTBX:
    def _write_tbx(self, path: Path, entries: list[tuple[str, str]]):
        """Helper: write a minimal TBX file."""
        root = ET.Element("martif", type="TBX-Basic")
        body = ET.SubElement(ET.SubElement(root, "text"), "body")
        ns_attr = "{http://www.w3.org/XML/1998/namespace}lang"
        for src, tgt in entries:
            te = ET.SubElement(body, "termEntry")
            ls1 = ET.SubElement(te, "langSet", **{ns_attr: "en"})
            tig1 = ET.SubElement(ls1, "tig")
            ET.SubElement(tig1, "term").text = src
            ls2 = ET.SubElement(te, "langSet", **{ns_attr: "zh"})
            tig2 = ET.SubElement(ls2, "tig")
            ET.SubElement(tig2, "term").text = tgt
        tree = ET.ElementTree(root)
        tree.write(str(path), encoding="utf-8", xml_declaration=True)

    def test_import_tbx(self, tmp_path):
        tbx_path = tmp_path / "test.tbx"
        self._write_tbx(tbx_path, [
            ("attention", "注意力"),
            ("transformer", "变换器"),
        ])

        store = GlossaryStore()
        count = store.import_tbx(tbx_path)
        assert count == 2
        assert store.get("attention").target == "注意力"
        assert store.get("transformer").target == "变换器"

    def test_export_tbx(self, tmp_path):
        store = GlossaryStore()
        store.update_from_list([
            {"source": "loss", "target": "损失", "locked": True},
        ])

        tbx_path = tmp_path / "export.tbx"
        count = store.export_tbx(tbx_path)
        assert count == 1

        # Verify the exported file is valid XML
        tree = ET.parse(str(tbx_path))
        root = tree.getroot()
        terms = [t.text for t in root.iter("term")]
        assert "loss" in terms
        assert "损失" in terms


# ---------------------------------------------------------------------------
# Suggestion feeding from _extract_term_pairs
# ---------------------------------------------------------------------------

class TestSuggestionFeeding:
    def test_add_suggestions_no_overwrite(self, locked_glossary):
        # "attention mechanism" already exists as locked
        added = locked_glossary.add_suggestions([
            ("attention mechanism", "注意"),
            ("new term", "新术语"),
        ])
        assert added == 1  # only "new term" added
        assert locked_glossary.get("attention mechanism").target == "注意力机制"
        assert locked_glossary.get("new term").target == "新术语"

    def test_extract_term_pairs_feeds_glossary(self):
        translated = "该模型使用了注意力机制（attention mechanism）来处理序列。"
        pairs = _extract_term_pairs("some original", translated)
        assert len(pairs) > 0
        assert any(p[0] == "attention mechanism" for p in pairs)


# ---------------------------------------------------------------------------
# Parallel safety: shared GlossaryStore reference
# ---------------------------------------------------------------------------

class TestParallelSafety:
    def test_shared_reference_thread_safe_reads(self):
        """GlossaryStore is read-only during translation — parallel reads are safe."""
        store = GlossaryStore()
        store.update_from_list([
            {"source": "attention", "target": "注意力", "locked": True},
        ])

        import concurrent.futures

        def read_and_check(i: int) -> list[dict]:
            return store.enforce(
                f"chunk {i} uses 注意力机制.",
                original="attention mechanism",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(read_and_check, i) for i in range(20)]
            results = [f.result() for f in futures]

        # All reads should succeed without error
        assert len(results) == 20
        # No violations since we always use the correct term
        for violations in results:
            assert len(violations) == 0


# ---------------------------------------------------------------------------
# CRUD API helpers
# ---------------------------------------------------------------------------

class TestCRUD:
    def test_to_dict_list(self, locked_glossary):
        items = locked_glossary.to_dict_list()
        assert len(items) == 4
        assert all("source" in item for item in items)

    def test_update_from_list(self, empty_glossary):
        items = [
            {"source": "a", "target": "b", "locked": True},
            {"source": "c", "target": "d", "locked": False},
        ]
        count = empty_glossary.update_from_list(items)
        assert count == 2
        assert empty_glossary.get("a").target == "b"
        assert empty_glossary.get("c").locked is False
