"""Translation Memory (TM) — sentence-level translation cache with fuzzy matching.

Stores source→target pairs in SQLite with pre-computed embeddings from
all-MiniLM-L6-v2. Supports exact match, fuzzy match (cosine similarity),
and TMX 1.4 import/export for interoperability with OmegaT and other CAT tools.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

# Cosine similarity thresholds
EXACT_THRESHOLD = 0.98
FUZZY_THRESHOLD = 0.70


@dataclass
class TMHit:
    source: str
    target: str
    score: float  # cosine similarity 0-1
    match_type: str  # "exact" | "fuzzy" | "none"
    metadata: dict | None = None


@dataclass
class TMStats:
    total_pairs: int
    source_lang: str
    target_lang: str


class TranslationMemory:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        self._encoder = None
        self._encoder_dim: int | None = None

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tm_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_hash TEXT NOT NULL,
                source_text TEXT NOT NULL,
                target_text TEXT NOT NULL,
                source_lang TEXT NOT NULL DEFAULT 'en',
                target_lang TEXT NOT NULL DEFAULT 'zh',
                metadata TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_source_hash
                ON tm_entries(source_hash);
            CREATE INDEX IF NOT EXISTS idx_source_lang
                ON tm_entries(source_lang, target_lang);
        """)
        self._conn.commit()

    def _get_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self._encoder_dim = self._encoder.get_sentence_embedding_dimension()
        return self._encoder

    def _embed(self, texts: str | list[str]) -> "numpy.ndarray":
        import numpy as np
        encoder = self._get_encoder()
        if isinstance(texts, str):
            texts = [texts]
        vectors = encoder.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)

    @staticmethod
    def _blob_to_vec(blob: bytes) -> "numpy.ndarray":
        import numpy as np
        return np.frombuffer(blob, dtype=np.float32)

    @staticmethod
    def _vec_to_blob(vec: "numpy.ndarray") -> bytes:
        import numpy as np
        return np.asarray(vec, dtype=np.float32).tobytes()

    @staticmethod
    def _cosine_similarity(a: "numpy.ndarray", b: "numpy.ndarray") -> float:
        import numpy as np
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def lookup(self, source_text: str, *,
               source_lang: str = "en", target_lang: str = "zh",
               fuzzy: bool = True) -> TMHit:
        """Look up a source sentence in the TM.

        Returns the best match found, or a TMHit with match_type="none".
        """
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()

        # Exact hash match
        row = self._conn.execute(
            "SELECT target_text, metadata FROM tm_entries WHERE source_hash = ?",
            (source_hash,),
        ).fetchone()
        if row:
            import json
            return TMHit(
                source=source_text,
                target=row[0],
                score=1.0,
                match_type="exact",
                metadata=json.loads(row[1]) if row[1] else None,
            )

        if not fuzzy:
            return TMHit(source=source_text, target="", score=0.0, match_type="none")

        # Fuzzy match via embeddings
        query_vec = self._embed(source_text)[0]
        rows = self._conn.execute(
            "SELECT source_text, target_text, embedding, metadata "
            "FROM tm_entries WHERE source_lang = ? AND target_lang = ?",
            (source_lang, target_lang),
        ).fetchall()

        best_hit: TMHit | None = None
        best_score = 0.0

        for src, tgt, emb_blob, meta_str in rows:
            if emb_blob is None:
                continue
            import json
            stored_vec = self._blob_to_vec(emb_blob)
            sim = self._cosine_similarity(query_vec, stored_vec)
            if sim > best_score:
                best_score = sim
                best_hit = TMHit(
                    source=src,
                    target=tgt,
                    score=sim,
                    match_type="fuzzy" if sim >= FUZZY_THRESHOLD else "none",
                    metadata=json.loads(meta_str) if meta_str else None,
                )

        if best_hit and best_hit.score >= FUZZY_THRESHOLD:
            if best_hit.score >= EXACT_THRESHOLD:
                best_hit.match_type = "exact"
            return best_hit

        return TMHit(source=source_text, target="", score=0.0, match_type="none")

    def store(self, source_text: str, target_text: str, *,
              source_lang: str = "en", target_lang: str = "zh",
              metadata: dict | None = None) -> None:
        """Store a source→target pair in the TM."""
        import json

        source_hash = hashlib.sha256(source_text.encode()).hexdigest()
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None

        vec = self._embed(source_text)[0]
        emb_blob = self._vec_to_blob(vec)

        self._conn.execute(
            """INSERT OR REPLACE INTO tm_entries
               (source_hash, source_text, target_text, source_lang, target_lang, metadata, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_hash, source_text, target_text, source_lang, target_lang, meta_str, emb_blob),
        )
        self._conn.commit()

    def stats(self) -> TMStats:
        row = self._conn.execute(
            "SELECT COUNT(*), source_lang, target_lang FROM tm_entries LIMIT 1"
        ).fetchone()
        if row and row[0] > 0:
            lang_row = self._conn.execute(
                "SELECT source_lang, target_lang FROM tm_entries LIMIT 1"
            ).fetchone()
            return TMStats(
                total_pairs=row[0],
                source_lang=lang_row[0] if lang_row else "en",
                target_lang=lang_row[1] if lang_row else "zh",
            )
        return TMStats(total_pairs=0, source_lang="en", target_lang="zh")

    def import_tmx(self, tmx_path: str | Path) -> int:
        """Import translations from a TMX 1.4 file. Returns number of imported pairs."""
        tree = ET.parse(str(tmx_path))
        root = tree.getroot()
        header = root.find("header")
        src_lang = (header.get("srclang") or "en")[:2].lower() if header is not None else "en"

        count = 0
        for tu in root.iter("tu"):
            tuvs = tu.findall("tuv")
            if len(tuvs) < 2:
                continue
            src_tuv = None
            tgt_tuv = None
            for tuv in tuvs:
                lang = (tuv.get("{http://www.w3.org/XML/1998/namespace}lang")
                        or tuv.get("lang") or "")[:2].lower()
                if lang == src_lang and src_tuv is None:
                    src_tuv = tuv
                elif lang != src_lang and tgt_tuv is None:
                    tgt_tuv = tuv
            if tgt_tuv is None and len(tuvs) >= 2:
                src_tuv, tgt_tuv = tuvs[0], tuvs[1]

            src_seg = src_tuv.find("seg") if src_tuv is not None else None
            tgt_seg = tgt_tuv.find("seg") if tgt_tuv is not None else None
            if src_seg is None or tgt_seg is None:
                continue
            src_text = (src_seg.text or "").strip()
            tgt_text = (tgt_seg.text or "").strip()
            if not src_text or not tgt_text:
                continue

            tgt_lang = "zh"
            if tgt_tuv is not None:
                raw = (tgt_tuv.get("{http://www.w3.org/XML/1998/namespace}lang")
                       or tgt_tuv.get("lang") or "zh")
                tgt_lang = raw[:2].lower()

            self.store(src_text, tgt_text, source_lang=src_lang, target_lang=tgt_lang)
            count += 1

        logger.info("TMX import: %d pairs from %s", count, tmx_path)
        return count

    def export_tmx(self, tmx_path: str | Path, *,
                   source_lang: str = "en", target_lang: str = "zh") -> int:
        """Export all pairs as a TMX 1.4 file compatible with OmegaT."""
        rows = self._conn.execute(
            "SELECT source_text, target_text FROM tm_entries "
            "WHERE source_lang = ? AND target_lang = ?",
            (source_lang, target_lang),
        ).fetchall()

        tmx = ET.Element("tmx", version="1.4")
        header = ET.SubElement(tmx, "header",
                               creationtool="ScholarAssistant",
                               creationtoolversion="0.4.2",
                               datatype="plaintext",
                               segtype="sentence",
                               adminlang="en",
                               srclang=source_lang,
                               o_tmf="unknown")
        ET.SubElement(header, "note").text = "Exported from Scholar Assistant Translation Memory"

        body = ET.SubElement(tmx, "body")

        ns = "http://www.w3.org/XML/1998/namespace"
        ns_attr = f"{{{ns}}}lang"

        for src, tgt in rows:
            tu = ET.SubElement(body, "tu")
            src_tuv = ET.SubElement(tu, "tuv", **{ns_attr: source_lang})
            ET.SubElement(src_tuv, "seg").text = src
            tgt_tuv = ET.SubElement(tu, "tuv", **{ns_attr: target_lang})
            ET.SubElement(tgt_tuv, "seg").text = tgt

        tree = ET.ElementTree(tmx)
        ET.indent(tree, space="  ")
        tree.write(str(tmx_path), encoding="utf-8", xml_declaration=True)

        logger.info("TMX export: %d pairs to %s", len(rows), tmx_path)
        return len(rows)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
