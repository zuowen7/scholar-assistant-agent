"""CompanionStore — JSON 持久化：Ledger + ReviewSession。

风格照搬 ArgGraphStore：内存 dict + 每对象一个 JSON，tmp+os.replace 原子写。
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from .companion_models import Ledger, Promise, RebuttalTurn, ReviewPoint, ReviewSession


def _safe(doc_id: str) -> str:
    return re.sub(r"[^\w.-]", "_", doc_id)


class CompanionStore:
    def __init__(self, runtime_dir: Path | str) -> None:
        self._root = Path(runtime_dir)
        self._ledger_dir = self._root / "companion" / "ledgers"
        self._review_dir = self._root / "companion" / "reviews"
        self._ledger_dir.mkdir(parents=True, exist_ok=True)
        self._review_dir.mkdir(parents=True, exist_ok=True)

        self._ledgers: dict[str, Ledger] = {}
        self._reviews: dict[str, ReviewSession] = {}
        self._lock = threading.RLock()
        self._load_all()

    # ── internal ──────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        for fp in self._ledger_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                ledger = Ledger.model_validate(data)
                self._ledgers[ledger.doc_id] = ledger
            except Exception:
                pass
        for fp in self._review_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                session = ReviewSession.model_validate(data)
                self._reviews[session.id] = session
            except Exception:
                pass

    def _flush_ledger(self, ledger: Ledger) -> None:
        path = self._ledger_dir / f"{_safe(ledger.doc_id)}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(ledger.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def _flush_review(self, session: ReviewSession) -> None:
        path = self._review_dir / f"{session.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(session.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ── Ledger API ────────────────────────────────────────────────────────────

    def get_ledger(self, doc_id: str) -> Optional[Ledger]:
        return self._ledgers.get(doc_id)

    def get_ledger_by_path(self, file_path: str) -> Optional[Ledger]:
        """按文件路径查找账本（doc_id 对已打开文件即为其路径）。

        先精确匹配，再 resolve 后比较，吸收 / vs \\ 和相对/绝对差异。
        """
        if not file_path:
            return None
        direct = self._ledgers.get(file_path)
        if direct is not None:
            return direct
        from pathlib import Path
        try:
            target = Path(file_path).resolve()
        except Exception:
            return None
        for doc_id, ledger in self._ledgers.items():
            try:
                if Path(doc_id).resolve() == target:
                    return ledger
            except Exception:
                continue
        return None

    def save_ledger(self, ledger: Ledger) -> None:
        with self._lock:
            self._ledgers[ledger.doc_id] = ledger
            self._flush_ledger(ledger)

    def list_ledgers(self) -> list[dict]:
        result = []
        for ledger in self._ledgers.values():
            result.append({
                "doc_id": ledger.doc_id,
                "doc_title": ledger.doc_title,
                "promise_count": len(ledger.promises),
                "last_built_at": ledger.last_built_at,
            })
        return result

    def delete_ledger(self, doc_id: str) -> None:
        with self._lock:
            self._ledgers.pop(doc_id, None)
            path = self._ledger_dir / f"{_safe(doc_id)}.json"
            path.unlink(missing_ok=True)

    def upsert_promise(self, doc_id: str, promise: Promise) -> None:
        with self._lock:
            ledger = self._ledgers.get(doc_id)
            if ledger is None:
                raise KeyError(f"Ledger not found for doc_id={doc_id!r}")
            existing = {p.id: i for i, p in enumerate(ledger.promises)}
            if promise.id in existing:
                ledger.promises[existing[promise.id]] = promise
            else:
                ledger.promises.append(promise)
            self._flush_ledger(ledger)

    def delete_promise(self, doc_id: str, pid: str) -> None:
        with self._lock:
            ledger = self._ledgers.get(doc_id)
            if ledger is None:
                return
            ledger.promises = [p for p in ledger.promises if p.id != pid]
            self._flush_ledger(ledger)

    # ── Review API ────────────────────────────────────────────────────────────

    def get_review(self, session_id: str) -> Optional[ReviewSession]:
        return self._reviews.get(session_id)

    def save_review(self, session: ReviewSession) -> None:
        with self._lock:
            self._reviews[session.id] = session
            self._flush_review(session)

    def list_reviews(self, doc_id: str) -> list[dict]:
        result = []
        for s in self._reviews.values():
            if s.doc_id != doc_id:
                continue
            open_count = sum(1 for p in s.points if p.status == "open")
            result.append({
                "session_id": s.id,
                "venue": s.venue,
                "persona": s.persona,
                "point_count": len(s.points),
                "open_count": open_count,
                "created_at": s.created_at,
            })
        return result

    def delete_review(self, session_id: str) -> None:
        with self._lock:
            self._reviews.pop(session_id, None)
            path = self._review_dir / f"{session_id}.json"
            path.unlink(missing_ok=True)

    def update_point(self, session_id: str, pid: str, status: str) -> None:
        with self._lock:
            session = self._reviews.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id!r}")
            for p in session.points:
                if p.id == pid:
                    p.status = status  # type: ignore[assignment]
                    self._flush_review(session)
                    return
            raise KeyError(f"Point not found: {pid!r}")

    def append_turns(
        self, session_id: str, pid: str, turns: list[RebuttalTurn]
    ) -> None:
        with self._lock:
            session = self._reviews.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id!r}")
            for p in session.points:
                if p.id == pid:
                    p.thread.extend(turns)
                    self._flush_review(session)
                    return
            raise KeyError(f"Point not found: {pid!r}")
