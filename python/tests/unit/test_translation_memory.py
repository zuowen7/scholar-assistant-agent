"""Unit tests for Translation Memory (TM) — store, lookup, TMX import/export."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.translator.memory_store import TranslationMemory, TMHit, FUZZY_THRESHOLD


def _unit_vec(*components):
    v = np.array(components, dtype=np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def tm(tmp_path):
    """TM store with mocked encoder (no model download needed)."""
    store = TranslationMemory(tmp_path / "test_tm.db")

    def mock_embed(texts):
        if isinstance(texts, str):
            texts = [texts]
        # Deterministic: hash each text to a seed
        vecs = []
        for t in texts:
            seed = int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)
            v = rng.randn(10).astype(np.float32)
            v = v / np.linalg.norm(v)
            vecs.append(v)
        return np.array(vecs, dtype=np.float32)

    store._embed = mock_embed
    yield store
    store.close()


# ---------------------------------------------------------------------------
# Exact match
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_store_and_lookup_exact(self, tm):
        tm.store("Hello world", "你好世界")
        hit = tm.lookup("Hello world")
        assert hit.match_type == "exact"
        assert hit.target == "你好世界"
        assert hit.score == 1.0

    def test_lookup_miss(self, tm):
        tm.store("Hello world", "你好世界")
        hit = tm.lookup("Something else entirely", fuzzy=False)
        assert hit.match_type == "none"
        assert hit.target == ""

    def test_overwrite_pair(self, tm):
        tm.store("Hello", "你好")
        tm.store("Hello", "您好")
        hit = tm.lookup("Hello")
        assert hit.target == "您好"

    def test_second_translate_no_llm(self, tm):
        """Acceptance: same sentence second time should hit exact match (no LLM needed)."""
        tm.store("The cat sat on the mat.", "猫坐在垫子上。")
        hit = tm.lookup("The cat sat on the mat.")
        assert hit.match_type == "exact"
        assert hit.target == "猫坐在垫子上。"


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------


class TestFuzzyMatch:
    def test_edit_distance_1_fuzzy(self, tm):
        """Acceptance: edit distance 1 sentence hits fuzzy."""
        vec_stored = _unit_vec(1.0, 0.0, 0.0)
        # cosine similarity = 0.85 — below EXACT_THRESHOLD (0.98) but above FUZZY_THRESHOLD (0.70)
        vec_query = _unit_vec(0.85, 0.527, 0.0)

        def mock_embed(texts):
            if isinstance(texts, str):
                texts = [texts]
            vecs = []
            for t in texts:
                if t == "Hello world":
                    vecs.append(vec_stored)
                else:
                    vecs.append(vec_query)
            return np.array(vecs, dtype=np.float32)

        tm._embed = mock_embed
        tm._fuzzy_ok = True
        tm._encoder = True  # bypass _get_encoder check

        # Insert stored pair directly with known embedding
        source_hash = hashlib.sha256("Hello world".encode()).hexdigest()
        blob = tm._vec_to_blob(vec_stored)
        tm._conn.execute(
            "INSERT OR REPLACE INTO tm_entries "
            "(source_hash, source_text, target_text, source_lang, target_lang, embedding) "
            "VALUES (?, ?, ?, 'en', 'zh', ?)",
            (source_hash, "Hello world", "你好世界", blob),
        )
        tm._conn.commit()

        hit = tm.lookup("Hello worlds")
        assert hit.match_type == "fuzzy"
        assert hit.score > FUZZY_THRESHOLD
        assert hit.target == "你好世界"

    def test_no_fuzzy_below_threshold(self, tm):
        vec_a = _unit_vec(1.0, 0.0)
        vec_b = _unit_vec(0.0, 1.0)

        def mock_embed(texts):
            if isinstance(texts, str):
                texts = [texts]
            return np.array([vec_b if t == "query" else vec_a for t in texts], dtype=np.float32)

        tm._embed = mock_embed
        tm._fuzzy_ok = True
        tm._encoder = True
        source_hash = hashlib.sha256("stored text".encode()).hexdigest()
        blob = tm._vec_to_blob(vec_a)
        tm._conn.execute(
            "INSERT OR REPLACE INTO tm_entries "
            "(source_hash, source_text, target_text, source_lang, target_lang, embedding) "
            "VALUES (?, ?, ?, 'en', 'zh', ?)",
            (source_hash, "stored text", "存储文本", blob),
        )
        tm._conn.commit()

        hit = tm.lookup("query")
        assert hit.match_type == "none"


# ---------------------------------------------------------------------------
# TMX export
# ---------------------------------------------------------------------------


class TestTMXExport:
    def test_export_and_roundtrip(self, tm, tmp_path):
        tm.store("Hello", "你好")
        tm.store("Goodbye", "再见")

        tmx_path = tmp_path / "export.tmx"
        count = tm.export_tmx(tmx_path)
        assert count == 2
        assert tmx_path.exists()

        import xml.etree.ElementTree as ET
        tree = ET.parse(str(tmx_path))
        root = tree.getroot()
        assert root.tag == "tmx"
        assert root.get("version") == "1.4"
        header = root.find("header")
        assert header is not None
        assert header.get("srclang") == "en"
        body = root.find("body")
        assert body is not None
        tus = body.findall("tu")
        assert len(tus) == 2

    def test_export_omegat_compatible(self, tm, tmp_path):
        """Export produces XML with xml:lang attributes (OmegaT standard)."""
        tm.store("Test sentence", "测试句子")
        tmx_path = tmp_path / "omegat.tmx"
        tm.export_tmx(tmx_path)

        import xml.etree.ElementTree as ET
        tree = ET.parse(str(tmx_path))
        root = tree.getroot()
        ns = "{http://www.w3.org/XML/1998/namespace}"
        tu = root.find("body/tu")
        tuvs = tu.findall("tuv")
        for tuv in tuvs:
            lang = tuv.get(f"{ns}lang")
            assert lang is not None, "Missing xml:lang attribute on tuv"


# ---------------------------------------------------------------------------
# TMX import
# ---------------------------------------------------------------------------


class TestTMXImport:
    def test_import_standard_tmx(self, tm, tmp_path):
        tmx_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tmx SYSTEM "tmx14.dtd">
<tmx version="1.4">
  <header creationtool="OmegaT" datatype="plaintext" segtype="sentence"
          adminlang="en" srclang="EN-US" o-tmf="unknown"/>
  <body>
    <tu>
      <tuv xml:lang="EN-US"><seg>The quick brown fox</seg></tuv>
      <tuv xml:lang="ZH-CN"><seg>敏捷的棕色狐狸</seg></tuv>
    </tu>
    <tu>
      <tuv xml:lang="EN-US"><seg>Hello world</seg></tuv>
      <tuv xml:lang="ZH-CN"><seg>你好世界</seg></tuv>
    </tu>
  </body>
</tmx>"""
        tmx_path = tmp_path / "import.tmx"
        tmx_path.write_text(tmx_content, encoding="utf-8")

        count = tm.import_tmx(tmx_path)
        assert count == 2

        hit = tm.lookup("The quick brown fox", fuzzy=False)
        assert hit.match_type == "exact"
        assert hit.target == "敏捷的棕色狐狸"

    def test_import_with_lang_attribute(self, tm, tmp_path):
        """Handle TMX files using plain 'lang' instead of xml:lang."""
        tmx_content = """<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="test" srclang="en" datatype="plaintext"/>
  <body>
    <tu>
      <tuv lang="en"><seg>Apple</seg></tuv>
      <tuv lang="zh"><seg>苹果</seg></tuv>
    </tu>
  </body>
</tmx>"""
        tmx_path = tmp_path / "import2.tmx"
        tmx_path.write_text(tmx_content, encoding="utf-8")

        count = tm.import_tmx(tmx_path)
        assert count == 1
        hit = tm.lookup("Apple", fuzzy=False)
        assert hit.match_type == "exact"
        assert hit.target == "苹果"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestTMStats:
    def test_empty_stats(self, tm):
        stats = tm.stats()
        assert stats.total_pairs == 0

    def test_stats_after_stores(self, tm):
        tm.store("Hello", "你好")
        tm.store("World", "世界")
        stats = tm.stats()
        assert stats.total_pairs == 2


# ---------------------------------------------------------------------------
# DB path
# ---------------------------------------------------------------------------


class TestDBPath:
    def test_db_at_runtime_dir(self, tmp_path):
        db_path = tmp_path / "tm.db"
        store = TranslationMemory(db_path)
        assert db_path.exists()
        store.close()

    def test_db_in_subdirectory(self, tmp_path):
        sub = tmp_path / "nested" / "dir"
        store = TranslationMemory(sub / "tm.db")
        assert (sub / "tm.db").exists()
        store.close()
