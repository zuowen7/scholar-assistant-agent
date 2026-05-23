"""论证账本：build_ledger / rebuild_ledger SSE 流式实现。"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import time
from typing import Any, AsyncIterator

from .anchor import make_anchor_from_quote, relocate_all
from .companion_models import Ledger, Promise
from .companion_store import CompanionStore
from .llm_client import call_llm_chat

logger = logging.getLogger(__name__)

_STATUS_SEVERITY = {
    "unpaid": "error",
    "mismatch": "error",
    "partial": "warning",
    "paid": "info",
    "unknown": "info",
}

_PROMISE_SECTION_RE = re.compile(
    r"^#{1,3}\s*(abstract|introduction|intro)\b",
    re.IGNORECASE | re.MULTILINE,
)
_HEADER_RE = re.compile(r"^#{1,3}\s+", re.MULTILINE)


def _doc_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def _extract_promise_zone(text: str) -> tuple[str, str]:
    """Split text into (promise_zone, body_zone)."""
    m = _PROMISE_SECTION_RE.search(text)
    if not m:
        # Use up to 3000 chars as the promise zone (not a fixed fraction —
        # 1/4 of a short text would truncate mid-sentence and break extraction).
        cut = min(len(text), 3000)
        return text[:cut], text[cut:]
    start = m.start()
    # Find next same-level or higher header after abstract/intro
    headers_after = list(_HEADER_RE.finditer(text, m.end()))
    if headers_after:
        end = headers_after[0].start()
        return text[start:end], text[end:]
    return text[start:], ""


async def _call_with_retry(
    prompt: str,
    cloud_client: Any,
    ollama_client: Any,
    max_tokens: int,
    temperature: float,
) -> str:
    raw = await call_llm_chat(prompt, cloud_client, ollama_client,
                               max_tokens=max_tokens, temperature=temperature)
    return raw


async def build_ledger(
    doc_id: str,
    doc_title: str,
    text: str,
    store: CompanionStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: promise* → complete (或 error，不写脏数据)。"""
    promise_zone, body_zone = _extract_promise_zone(text)

    # ── LLM #1: extract promises ──────────────────────────────────────────────
    prompt1 = (
        "你是学术论证分析专家。从这篇论文提取作者立下的承诺（contribution, claim, hypothesis, gap_statement, scope 之一）。\n\n"
        f"文本：\n{promise_zone[:3000]}\n\n"
        "输出严格 JSON（不含其他文字）：\n"
        '{"promises":[{"local_id":"p1","kind":"contribution","text":"承诺原话(可适度归一)","verbatim_quote":"文中的精确子串"}]}'
    )

    raw1 = ""
    for attempt in range(2):
        try:
            raw1 = await _call_with_retry(
                prompt1 if attempt == 0
                else f"请只输出有效的 JSON 对象：\n{raw1[:500]}",
                cloud_client, ollama_client,
                max_tokens=4096, temperature=0.3,
            )
            if raw1.strip():
                m = re.search(r"\{[\s\S]*\}", raw1)
                if m:
                    json.loads(m.group())  # validate
                    break
        except (json.JSONDecodeError, ValueError):
            if attempt == 1:
                yield {"event": "error", "data": json.dumps({"message": "LLM 未返回有效 JSON，请重试"})}
                return
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"message": f"LLM 调用失败: {exc}"})}
            return

    if not raw1.strip():
        yield {"event": "error", "data": json.dumps({"message": "LLM 返回空响应，请重试"})}
        return

    try:
        m1 = re.search(r"\{[\s\S]*\}", raw1)
        if not m1:
            raise ValueError("no JSON object found")
        parsed1 = json.loads(m1.group())
    except (json.JSONDecodeError, ValueError):
        yield {"event": "error", "data": json.dumps({"message": "LLM 未返回有效 JSON，请重试"})}
        return

    raw_promises = parsed1.get("promises", [])
    if not raw_promises:
        # No promises found — complete with zero
        print(f"[companion] build_ledger LLM raw response (len={len(raw1)}): {raw1[:500]}", flush=True)
        logger.warning("companion build_ledger 0 promises raw1(500)=%s", raw1[:500])
        # No promises found — complete with zero
        ledger = Ledger(
            doc_id=doc_id,
            doc_title=doc_title,
            promises=[],
            anchors=[],
            doc_hash=_doc_hash(text),
            last_built_at=time.time(),
        )
        store.save_ledger(ledger)
        yield {"event": "complete", "data": json.dumps({
            "ledger_id": ledger.id,
            "promise_count": 0,
            "by_status": {},
            "warnings": ["LLM 未提取到承诺"],
        })}
        return

    # ── LLM #2: discharge resolution ─────────────────────────────────────────
    # Sample body: head + middle + tail so experiments/results sections are visible
    def _sample_body(body: str, total: int = 6000) -> str:
        if len(body) <= total:
            return body
        chunk = total // 3
        mid = len(body) // 2
        return (
            body[:chunk]
            + f"\n\n[... 中间省略 {mid - chunk} 字符 ...]\n\n"
            + body[mid - chunk // 2: mid + chunk // 2]
            + f"\n\n[... 省略至末尾 ...]\n\n"
            + body[-chunk:]
        )

    body_sample = _sample_body(body_zone)
    promises_summary = "\n".join(
        f"- (id={p.get('local_id','?')}) {p.get('text','')}"
        for p in raw_promises
    )
    prompt2 = (
        "你是严格的学术审稿人。对以下每条承诺，在论文正文里找兑现证据，按以下标准判断状态：\n\n"
        "状态标准（从严判断，不要宽泛认为'有相关内容'就算 paid）：\n"
        "- unpaid：正文里完全没有对应的实验/证明/数据，或该 section 尚未写出\n"
        "- partial：有相关内容但不完整——例如缺少消融实验、某基线没比较、某场景没覆盖\n"
        "- mismatch：正文给出的结果与承诺相矛盾，或结论被限定条件稀释到名存实亡\n"
        "- paid：正文有完整的实验结果/严格证明/充分数据直接支撑该承诺，审稿人挑不出漏洞\n\n"
        f"承诺列表：\n{promises_summary}\n\n"
        f"论文正文（首段+中段+末段采样）：\n{body_sample}\n\n"
        "输出严格 JSON 数组（不含其他文字），每项：\n"
        '{"promise_local_id":"p1","status":"unpaid|partial|mismatch|paid",'
        '"discharge_quotes":["正文精确子串，找不到则空数组"],'
        '"note":"一行具体说明：paid 时说证据在哪；unpaid/partial 时说缺什么"}'
    )

    raw2 = ""
    for attempt in range(2):
        try:
            raw2 = await _call_with_retry(
                prompt2 if attempt == 0
                else f"请只输出有效的 JSON 数组：\n{raw2[:500]}",
                cloud_client, ollama_client,
                max_tokens=4096, temperature=0.3,
            )
            if raw2.strip():
                m2 = re.search(r"\[[\s\S]*\]", raw2)
                if m2:
                    json.loads(m2.group())
                    break
        except (json.JSONDecodeError, ValueError):
            if attempt == 1:
                raw2 = "[]"
        except Exception:
            raw2 = "[]"

    discharge_map: dict[str, dict] = {}
    try:
        m2 = re.search(r"\[[\s\S]*\]", raw2)
        if m2:
            for item in json.loads(m2.group()):
                lid = str(item.get("promise_local_id", ""))
                discharge_map[lid] = item
    except Exception:
        pass

    # ── Assemble promises + anchors ───────────────────────────────────────────
    new_promises: list[Promise] = []
    new_anchors = []
    warnings: list[str] = []
    valid_kinds = {"contribution", "claim", "hypothesis", "gap_statement", "scope"}

    for rp in raw_promises:
        local_id = str(rp.get("local_id", ""))
        kind = str(rp.get("kind", ""))
        ptext = str(rp.get("text", "")).strip()
        verbatim = str(rp.get("verbatim_quote", "")).strip()

        if kind not in valid_kinds or not ptext:
            warnings.append(f"跳过无效承诺 kind={kind!r}")
            continue

        # Source anchor
        src_anchor = make_anchor_from_quote(doc_id, text, verbatim)
        new_anchors.append(src_anchor)
        # 先把锚点流给前端，否则 ledger.anchors 为空、定位按钮失效
        yield {"event": "anchor", "data": src_anchor.model_dump_json()}

        # Discharge
        dis_info = discharge_map.get(local_id, {})
        status = str(dis_info.get("status", "unknown"))
        if status not in ("paid", "partial", "unpaid", "mismatch"):
            status = "unknown"
        note = dis_info.get("note") or None
        dis_ids: list[str] = []
        for dq in dis_info.get("discharge_quotes", []):
            da = make_anchor_from_quote(doc_id, text, str(dq))
            new_anchors.append(da)
            dis_ids.append(da.id)
            yield {"event": "anchor", "data": da.model_dump_json()}

        severity = _STATUS_SEVERITY.get(status, "info")

        promise = Promise(
            text=ptext,
            kind=kind,  # type: ignore[arg-type]
            source_anchor_id=src_anchor.id,
            discharge_anchor_ids=dis_ids,
            status=status,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            note=note,
            created_by="ai",
        )
        new_promises.append(promise)
        yield {"event": "promise", "data": promise.model_dump_json()}

    # ── Save ledger ───────────────────────────────────────────────────────────
    by_status: dict[str, int] = {}
    for p in new_promises:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    ledger = Ledger(
        doc_id=doc_id,
        doc_title=doc_title,
        promises=new_promises,
        anchors=new_anchors,
        doc_hash=_doc_hash(text),
        last_built_at=time.time(),
    )
    store.save_ledger(ledger)
    yield {"event": "complete", "data": json.dumps({
        "ledger_id": ledger.id,
        "promise_count": len(new_promises),
        "by_status": by_status,
        "warnings": warnings,
    })}


async def rebuild_ledger(
    doc_id: str,
    doc_title: str,
    text: str,
    store: CompanionStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """同 build，但保留 user_overridden=True 的承诺，并对所有 anchor 跑 relocate_all。"""
    existing = store.get_ledger(doc_id)

    # Collect user-overridden promises (preserve)
    overridden: list[Promise] = []
    if existing:
        overridden = [p for p in existing.promises if p.user_overridden]
        # Relocate their anchors
        overridden_anchor_ids = set()
        for p in overridden:
            overridden_anchor_ids.add(p.source_anchor_id)
            overridden_anchor_ids.update(p.discharge_anchor_ids)
        if existing.anchors:
            relocated = relocate_all(
                [a for a in existing.anchors if a.id in overridden_anchor_ids],
                text,
            )
            # Build a lookup id → anchor
            relocated_map = {a.id: a for a in relocated}
            # Update overridden promises with relocated anchor references (anchors stay same id)
            existing_anchors_updated = [
                relocated_map.get(a.id, a) for a in existing.anchors
                if a.id in overridden_anchor_ids
            ]
        else:
            existing_anchors_updated = []
    else:
        existing_anchors_updated = []

    # Run fresh build (yields promise events and saves to store)
    new_promise_events: list[dict] = []
    last_event: dict | None = None

    async for ev in build_ledger(doc_id, doc_title, text, store, cloud_client, ollama_client):
        if ev["event"] == "error":
            yield ev
            return
        last_event = ev
        if ev["event"] == "anchor":
            yield ev
        elif ev["event"] == "promise":
            new_promise_events.append(ev)
            yield ev

    # Yield the complete event from build_ledger
    if last_event and last_event["event"] == "complete":
        yield last_event

    # Now patch in user-overridden promises
    if not overridden:
        return

    fresh_ledger = store.get_ledger(doc_id)
    if fresh_ledger is None:
        return

    # Merge: add overridden promises back (they survive)
    # Remove any AI-generated promises that were id-matched to overridden ones (shouldn't exist)
    overridden_ids = {p.id for p in overridden}
    fresh_ledger.promises = [p for p in fresh_ledger.promises if p.id not in overridden_ids]
    fresh_ledger.promises.extend(overridden)

    # Merge their anchors back
    existing_anchor_ids = {a.id for a in fresh_ledger.anchors}
    for a in existing_anchors_updated:
        if a.id not in existing_anchor_ids:
            fresh_ledger.anchors.append(a)

    store.save_ledger(fresh_ledger)


# ── Phase 5: suggest experiment ───────────────────────────────────────────────

async def suggest_experiment_for_promise(
    promise_text: str,
    promise_note: str | None,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> str:
    """Return an experiment suggestion for a partial/unpaid promise.

    Falls back to a non-empty placeholder string if the LLM is unavailable.
    """
    note_part = f"\n现有覆盖情况：{promise_note}" if promise_note else ""
    prompt = (
        f"这篇论文立了如下承诺但尚未完全兑付：\n「{promise_text}」{note_part}\n\n"
        "请给出实验设计建议，格式分三段：\n"
        "【当前已覆盖条件】...\n【还需要的条件】...\n【建议实验设计】..."
    )
    try:
        result = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=4096, temperature=0.4)
        return result or "（LLM 返回为空，请手动填写建议）"
    except Exception as exc:
        return f"（LLM 不可用：{exc}；请手动补充实验设计。）"
