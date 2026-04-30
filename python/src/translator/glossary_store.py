"""Authoritative terminology glossary — pre-loaded seed entries with enforcement.

Replaces the ad-hoc ``_extract_term_pairs`` learning with a structured glossary that
supports locked (mandatory) and suggestion entries, CSV/TBX import/export, and
post-translation enforcement.

Thread-safe for concurrent reads (parallel translation shares a single GlossaryStore
instance). Writes (import/add) are not concurrent in normal usage.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import yaml

logger = logging.getLogger(__name__)


@dataclass
class GlossaryEntry:
    source: str          # e.g. "attention mechanism"
    target: str          # e.g. "注意力机制"; "" means "do not translate"
    locked: bool = False  # locked → must appear exactly; unlocked → suggestion
    category: str = ""    # optional grouping (e.g. "ML", "NLP")
    note: str = ""        # optional usage note

    @property
    def is_passthrough(self) -> bool:
        """True when target is empty → source term must appear unchanged."""
        return self.target == ""

    @property
    def display_target(self) -> str:
        """Target for prompt display; passthrough entries show '(do not translate)'."""
        return self.target if self.target else f"（不翻译，保留原文）"


class GlossaryStore:
    """In-memory terminology store loaded from YAML seed files.

    Usage:
        store = GlossaryStore()
        store.load_yaml("glossaries/ml.yaml")
        prompt = store.build_prompt_text()
        violations = store.enforce(translated_text)
    """

    def __init__(self) -> None:
        # source.lower() → GlossaryEntry
        self._entries: dict[str, GlossaryEntry] = {}

    # ── Loading ────────────────────────────────────────────────────────

    def load_yaml(self, path: str | Path) -> int:
        """Load entries from a YAML glossary file. Returns count of loaded entries."""
        path = Path(path)
        if not path.exists():
            logger.warning("Glossary YAML not found: %s", path)
            return 0
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        category = data.get("category", "")
        count = 0
        for item in data.get("entries", []):
            entry = GlossaryEntry(
                source=item.get("source", ""),
                target=item.get("target", ""),
                locked=item.get("locked", False),
                category=item.get("category", category),
                note=item.get("note", ""),
            )
            if not entry.source:
                continue
            key = entry.source.lower()
            # Loaded entries are authoritative; only overwrite if new entry is locked
            existing = self._entries.get(key)
            if existing and not entry.locked and existing.locked:
                continue
            self._entries[key] = entry
            count += 1
        logger.info("Loaded %d glossary entries from %s", count, path)
        return count

    def load_yaml_dir(self, dir_path: str | Path) -> int:
        """Load all .yaml/.yml files from a directory. Returns total count."""
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            return 0
        total = 0
        for p in sorted(dir_path.glob("*.yaml")):
            total += self.load_yaml(p)
        for p in sorted(dir_path.glob("*.yml")):
            total += self.load_yaml(p)
        return total

    # ── Accessors ──────────────────────────────────────────────────────

    def get(self, source: str) -> GlossaryEntry | None:
        return self._entries.get(source.lower())

    def all_entries(self) -> list[GlossaryEntry]:
        return sorted(self._entries.values(), key=lambda e: e.source.lower())

    def locked_entries(self) -> list[GlossaryEntry]:
        return [e for e in self._entries.values() if e.locked]

    def __len__(self) -> int:
        return len(self._entries)

    # ── Prompt building ────────────────────────────────────────────────

    def build_prompt_text(self, max_entries: int = 50) -> str:
        """Build a prompt section for system prompt injection.

        Locked entries are listed first with a "must follow" header,
        suggestions follow with a "should follow" header.
        """
        if not self._entries:
            return ""

        locked = [e for e in self._entries.values() if e.locked]
        suggestions = [e for e in self._entries.values() if not e.locked]

        parts: list[str] = []

        if locked:
            locked = sorted(locked, key=lambda e: e.source.lower())[:max_entries]
            parts.append("## 强制术语表（必须严格遵循，不可替换）")
            for e in locked:
                parts.append(f"- {e.source} → {e.display_target}")

        sug_slots = max_entries - len(locked)
        if suggestions and sug_slots > 0:
            suggestions = sorted(suggestions, key=lambda e: e.source.lower())[:sug_slots]
            parts.append("## 参考术语表（建议沿用，保持一致）")
            for e in suggestions:
                parts.append(f"- {e.source} → {e.display_target}")

        return "\n".join(parts)

    # ── Enforcement ────────────────────────────────────────────────────

    def enforce(self, translated: str, original: str = "") -> list[dict]:
        """Check locked term violations in translated text.

        Args:
            translated: the translated output text
            original: optional source text — if provided, only enforces entries
                      whose source term appears in the original

        Returns a list of violation dicts:
            [{"source": "attention", "expected": "注意力机制", "rule": "locked"}]
        """
        violations: list[dict] = []
        for entry in self._entries.values():
            if not entry.locked:
                continue

            if entry.is_passthrough:
                # Source term must appear as-is in the translation
                if not self._source_present(translated, entry.source):
                    violations.append({
                        "source": entry.source,
                        "expected": entry.source,
                        "rule": "passthrough",
                        "message": f"未保留原文术语 '{entry.source}'",
                    })
            else:
                # If original is provided, only enforce when source appears in original
                source_in_original = self._source_present(original, entry.source) if original else True
                if not source_in_original:
                    continue
                # Target term must be present in the translation
                if not self._target_present(translated, entry.target):
                    violations.append({
                        "source": entry.source,
                        "expected": entry.target,
                        "rule": "locked",
                        "message": f"术语 '{entry.source}' 应译为 '{entry.target}'",
                    })
        return violations

    @staticmethod
    def _source_present(text: str, source: str) -> bool:
        """Check if source term appears in text (case-insensitive)."""
        return bool(re.search(re.escape(source), text, re.IGNORECASE))

    @staticmethod
    def _target_present(text: str, target: str) -> bool:
        """Check if target term appears in text."""
        return target in text

    # ── Suggestion feeding (from _extract_term_pairs) ──────────────────

    def add_suggestions(self, pairs: list[tuple[str, str]]) -> int:
        """Add non-locked suggestion entries from _extract_term_pairs output.

        Only adds if no existing entry (locked or suggestion) for the source.
        Returns count of newly added entries.
        """
        added = 0
        for source, target in pairs:
            key = source.lower()
            if key in self._entries:
                continue
            self._entries[key] = GlossaryEntry(
                source=source,
                target=target,
                locked=False,
            )
            added += 1
        return added

    # ── Import ─────────────────────────────────────────────────────────

    def import_csv(self, csv_path: str | Path, *,
                   locked: bool = False,
                   source_col: int = 0,
                   target_col: int = 1,
                   category: str = "") -> int:
        """Import entries from CSV. Returns count of imported entries.

        Expected format: source,target[,category] per row. First row treated as header
        if it contains non-CJK text.
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        count = 0
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0 and row and not any("一" <= c <= "鿿" for c in row[0]):
                    continue  # skip header
                if len(row) <= source_col:
                    continue
                source = row[source_col].strip()
                if not source:
                    continue
                target = row[target_col].strip() if len(row) > target_col else ""
                cat = row[2].strip() if len(row) > 2 and row[2].strip() else category
                entry = GlossaryEntry(source=source, target=target, locked=locked, category=cat)
                key = source.lower()
                existing = self._entries.get(key)
                if existing and existing.locked and not locked:
                    continue
                self._entries[key] = entry
                count += 1
        logger.info("CSV import: %d entries from %s", count, path)
        return count

    def import_tbx(self, tbx_path: str | Path, *,
                    locked: bool = False,
                    source_lang: str = "en",
                    target_lang: str = "zh") -> int:
        """Import entries from TBX (TermBase eXchange) file. Returns count."""
        path = Path(tbx_path)
        if not path.exists():
            raise FileNotFoundError(f"TBX file not found: {path}")

        count = 0
        tree = ET.parse(str(path))
        root = tree.getroot()

        # TBX namespace handling
        ns = {"tbx": "urn:iso:std:iso:30042:ed-2"}

        # Try with and without namespace
        for termEntry in root.iter("termEntry"):
            count += self._parse_tbx_entry(termEntry, locked, source_lang, target_lang)
        for termEntry in root.iter("{urn:iso:std:iso:30042:ed-2}termEntry"):
            count += self._parse_tbx_entry(termEntry, locked, source_lang, target_lang)

        logger.info("TBX import: %d entries from %s", count, path)
        return count

    def _parse_tbx_entry(self, termEntry, locked: bool,
                         source_lang: str, target_lang: str) -> int:
        """Parse a single termEntry element."""
        src_term = ""
        tgt_term = ""
        for langSet in termEntry.iter("langSet"):
            lang = (langSet.get("xml:lang", "")
                    or langSet.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    or langSet.get("lang", ""))
            lang = lang[:2].lower()
            for tg in langSet.iter("termGroup"):
                for term_el in tg.iter("term"):
                    text = (term_el.text or "").strip()
                    if not text:
                        continue
                    if lang == source_lang and not src_term:
                        src_term = text
                    elif lang == target_lang and not tgt_term:
                        tgt_term = text
            # Also check direct term children
            for term_el in langSet.iter("term"):
                text = (term_el.text or "").strip()
                if not text:
                    continue
                if lang == source_lang and not src_term:
                    src_term = text
                elif lang == target_lang and not tgt_term:
                    tgt_term = text

        if not src_term:
            return 0

        key = src_term.lower()
        existing = self._entries.get(key)
        if existing and existing.locked and not locked:
            return 0
        self._entries[key] = GlossaryEntry(source=src_term, target=tgt_term, locked=locked)
        return 1

    # ── Export ──────────────────────────────────────────────────────────

    def export_csv(self, path: str | Path) -> int:
        """Export all entries to CSV. Returns count."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = self.all_entries()
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target", "locked", "category", "note"])
            for e in entries:
                writer.writerow([e.source, e.target, e.locked, e.category, e.note])
        logger.info("CSV export: %d entries to %s", len(entries), path)
        return len(entries)

    def export_tbx(self, path: str | Path, *,
                   source_lang: str = "en", target_lang: str = "zh") -> int:
        """Export all entries to TBX format. Returns count."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = self.all_entries()

        root = ET.Element("martif", type="TBX-Basic")
        header = ET.SubElement(root, "martifHeader")
        fileDesc = ET.SubElement(header, "fileDesc")
        titleStmt = ET.SubElement(fileDesc, "titleStmt")
        ET.SubElement(titleStmt, "title").text = "研墨 Glossary"
        sourceDesc = ET.SubElement(fileDesc, "sourceDesc")
        ET.SubElement(sourceDesc, "p").text = "Exported from 研墨"

        body = ET.SubElement(root, "text")
        body_el = ET.SubElement(body, "body")

        ns_attr = "{http://www.w3.org/XML/1998/namespace}lang"

        for e in entries:
            termEntry = ET.SubElement(body_el, "termEntry")
            src_langSet = ET.SubElement(termEntry, "langSet", **{ns_attr: source_lang})
            src_tig = ET.SubElement(src_langSet, "tig")
            ET.SubElement(src_tig, "term").text = e.source

            if e.target:
                tgt_langSet = ET.SubElement(termEntry, "langSet", **{ns_attr: target_lang})
                tgt_tig = ET.SubElement(tgt_langSet, "tig")
                ET.SubElement(tgt_tig, "term").text = e.target

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(str(path), encoding="utf-8", xml_declaration=True)

        logger.info("TBX export: %d entries to %s", len(entries), path)
        return len(entries)

    # ── CRUD for API routes ────────────────────────────────────────────

    def to_dict_list(self) -> list[dict]:
        """Serialize all entries for JSON API response."""
        return [
            {
                "source": e.source,
                "target": e.target,
                "locked": e.locked,
                "category": e.category,
                "note": e.note,
            }
            for e in self.all_entries()
        ]

    def update_from_list(self, items: list[dict]) -> int:
        """Replace entries from a list of dicts (PUT API). Returns count."""
        self._entries.clear()
        count = 0
        for item in items:
            entry = GlossaryEntry(
                source=item.get("source", ""),
                target=item.get("target", ""),
                locked=item.get("locked", False),
                category=item.get("category", ""),
                note=item.get("note", ""),
            )
            if not entry.source:
                continue
            self._entries[entry.source.lower()] = entry
            count += 1
        return count
