"""论证账本：build_ledger / rebuild_ledger SSE 流式实现。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.utils.json_extract import extract_json_array, extract_json_object

from .anchor import make_anchor_from_quote, relocate, relocate_all
from .companion_models import Ledger, Promise
from .companion_store import CompanionStore
from .llm_client import call_llm_chat
from .section_utils import SectionExcerpt, build_section_excerpt_envelope

logger = logging.getLogger(__name__)

_STATUS_SEVERITY = {
    "unpaid": "error",
    "mismatch": "error",
    "partial": "warning",
    "paid": "info",
    "unknown": "info",
}
_SUBSTANTIVE_STATUSES = frozenset({"paid", "partial", "unpaid", "mismatch"})

_PROMISE_SECTION_RE = re.compile(
    r"^(?:#{1,3}\s*)?(?:\d{1,2}(?:\.\d{1,2})*\.?\s*)?"
    r"(abstract|摘要|introduction|引言|研究背景|研究动机|intro|background|motivation)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"^(?:#{1,3}\s*)?(?:\d{1,2}(?:\.\d{1,2})*\.?\s*)?"
    r"(methods?|approach|methodology|方法|实验|experiments?)"
    r"(?:\s*[:\-–—]\s*[^\n]{0,100})?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_HEADER_RE = re.compile(r"^(?:#{1,3}\s+|\d{1,2}(?:\.\d{1,2})*\.?\s+)", re.MULTILINE)

_LEDGER_MAX_TOKENS = 4096
_LEDGER_TEMPERATURE = 0.3
_LEDGER_JSON_MODE = True
_LEDGER_ATTEMPTS = 2

LedgerLLMCall = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class LedgerStageRequest:
    """Exact production request inputs for one independently evaluable stage."""

    stage: str
    excerpt: SectionExcerpt
    prompt: str
    max_tokens: int = _LEDGER_MAX_TOKENS
    temperature: float = _LEDGER_TEMPERATURE
    json_mode: bool = _LEDGER_JSON_MODE

    @property
    def excerpt_sha256(self) -> str:
        return _sha256_text(self.excerpt.text)


@dataclass(frozen=True)
class LedgerStageAttempt:
    """One immutable attempt, including failures that production may retry."""

    attempt_number: int
    prompt: str
    raw_response: str | None
    parsed_output: Any
    status: str
    started_at: float
    ended_at: float
    error: dict[str, str] | None = None

    @property
    def prompt_sha256(self) -> str:
        return _sha256_text(self.prompt)

    @property
    def raw_response_sha256(self) -> str | None:
        return _sha256_text(self.raw_response) if self.raw_response is not None else None


@dataclass(frozen=True)
class LedgerStageResult:
    """Observable result of a production-equivalent Ledger LLM stage."""

    request: LedgerStageRequest
    attempts: tuple[LedgerStageAttempt, ...]
    raw_response: str
    parsed_output: list[Any]
    termination_status: str
    error_message: str | None = None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _doc_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def _extract_promise_zone(text: str) -> tuple[str, str]:
    """Split text into (promise_zone, body_zone).

    Promise zone covers everything from the start up to (but not including)
    the methods/approach section — typically abstract, introduction, motivation,
    and related work all contain claims and contributions.
    """
    # Try to find where methods/approach starts
    m_method = _METHOD_RE.search(text)
    if m_method:
        return text[: m_method.start()], text[m_method.start() :]

    # Fallback: find first promise-related section and go to next major section
    m = _PROMISE_SECTION_RE.search(text)
    if not m:
        cut = min(len(text), 6000)
        return text[:cut], text[cut:]
    start = m.start()
    # Collect subsequent headers until a non-promise section
    for h in _HEADER_RE.finditer(text, m.end()):
        h.group().strip().lstrip("#").strip()
        if _METHOD_RE.search(h.group()):
            return text[start : h.start()], text[h.start() :]
    # No method header found — use first 40% of text as promise zone
    cut = min(len(text), max(6000, len(text) * 2 // 5))
    return text[:cut], text[cut:]


async def _call_with_retry(
    prompt: str,
    cloud_client: Any,
    ollama_client: Any,
    max_tokens: int,
    temperature: float,
    *,
    json_mode: bool = False,
) -> str:
    raw = await call_llm_chat(
        prompt,
        cloud_client,
        ollama_client,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
    )
    return raw


def _parse_promise_payload(raw: str) -> list[dict]:
    """Accept the documented wrapper and a common top-level-array variant."""
    parsed = extract_json_object(raw)
    if parsed and isinstance(parsed.get("promises"), list):
        return [item for item in parsed["promises"] if isinstance(item, dict)]
    array = extract_json_array(raw)
    if array is not None:
        return [item for item in array if isinstance(item, dict)]
    return []


def _has_valid_promise_payload(raw: str) -> bool:
    parsed = extract_json_object(raw)
    if parsed is not None and isinstance(parsed.get("promises"), list):
        return True
    return extract_json_array(raw) is not None


def _build_extraction_prompt(promise_excerpt: str) -> str:
    return (
        "你是学术论证分析专家。从这篇论文的前半部分（摘要、引言、动机、研究背景等）全面提取作者立下的所有承诺。\n\n"
        "承诺类型说明：\n"
        "- contribution: 具体贡献声明（'我们提出了…'、'本文的贡献包括…'）\n"
        "- claim: 学术主张或断言（'X 优于 Y'、'该方法能解决…'）\n"
        "- hypothesis: 待验证假设（'我们假设…'、'预期…'）\n"
        "- gap_statement: 指出的研究空白（'现有方法未解决…'、'缺乏…'）\n"
        "- scope: 范围限定或边界声明（'本文聚焦于…'、'不包括…'）\n\n"
        "请仔细阅读全文，不要遗漏。一篇论文通常有 5-15 条承诺，分布在多个段落中。\n"
        "特别注意：贡献列表、'we propose'、'we demonstrate'、'our approach'、'主要创新'、"
        "'本文旨在'、'与现有方法不同'等表述都应提取。\n\n"
        f"文本：\n{promise_excerpt}\n\n"
        "输出严格 JSON（不含其他文字）：\n"
        '{"promises":[{"local_id":"p1","kind":"contribution","text":"承诺原话(可适度归一)","verbatim_quote":"文中的精确子串"}]}'
    )


def _build_discharge_prompt(promises: list[dict], body_excerpt: str) -> str:
    promises_summary = "\n".join(
        f"- (id={p.get('local_id', '?')}) {p.get('text', '')}" for p in promises
    )
    return (
        "你是严格的学术审稿人。对以下每条承诺，在论文正文里找兑现证据，按以下标准判断状态：\n\n"
        "状态标准（从严判断，不要宽泛认为'有相关内容'就算 paid）：\n"
        "- unpaid：正文里完全没有对应的实验/证明/数据，或该 section 尚未写出\n"
        "- partial：有相关内容但不完整——例如缺少消融实验、某基线没比较、某场景没覆盖\n"
        "- mismatch：正文给出的结果与承诺相矛盾，或结论被限定条件稀释到名存实亡\n"
        "- paid：正文有完整的实验结果/严格证明/充分数据直接支撑该承诺，审稿人挑不出漏洞\n\n"
        "重要边界：承诺原话已经出现在前半部分，不得写成“该主张/数值在整篇文档中未出现”。"
        "这里只判断后续正文是否提供了独立兑现证据。若后续正文为空，应准确写“未提供后续正文证据”，"
        "不得否认承诺原话本身的存在。\n\n"
        f"承诺列表：\n{promises_summary}\n\n"
        f"论文正文（首段+中段+末段采样）：\n{body_excerpt}\n\n"
        "输出严格 JSON 数组（不含其他文字），每项：\n"
        '{"promise_local_id":"p1","status":"unpaid|partial|mismatch|paid",'
        '"discharge_quotes":["正文精确子串，找不到则空数组"],'
        '"note":"一行具体说明：paid 时说证据在哪；unpaid/partial 时说缺什么"}'
    )


def prepare_ledger_extraction(text: str) -> LedgerStageRequest:
    """Create the byte-identical extraction request used by ``build_ledger``."""
    promise_zone, _body_zone = _extract_promise_zone(text)
    excerpt = build_section_excerpt_envelope(promise_zone, max_chars=16000)
    return LedgerStageRequest(
        stage="extraction",
        excerpt=excerpt,
        prompt=_build_extraction_prompt(excerpt.text),
    )


def prepare_ledger_classification(text: str, promises: list[dict]) -> LedgerStageRequest:
    """Create the production classification request for explicit promises.

    Evaluation code may pass frozen gold promises here. This function never
    invokes extraction and therefore keeps gold-conditioned classification
    identifiable.
    """
    _promise_zone, body_zone = _extract_promise_zone(text)
    excerpt = build_section_excerpt_envelope(body_zone, max_chars=48000)
    return LedgerStageRequest(
        stage="gold_conditioned_status",
        excerpt=excerpt,
        prompt=_build_discharge_prompt(promises, excerpt.text),
    )


def _attempt_status(raw: str, parsed: list[Any] | None) -> str:
    if not raw.strip():
        return "empty_response"
    if parsed is None:
        return "invalid_json"
    if not parsed:
        return "legal_empty"
    return "success"


def _attempt_error(status: str) -> dict[str, str] | None:
    """Return schema-ready diagnostics for response-level failures."""
    if status == "empty_response":
        return {"type": "EmptyResponse", "message": "LLM returned an empty response"}
    if status == "invalid_json":
        return {"type": "InvalidJSONResponse", "message": "LLM response was not valid JSON"}
    return None


async def run_ledger_extraction_stage(
    text: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    llm_call: LedgerLLMCall | None = None,
) -> LedgerStageResult:
    """Run only production Promise extraction and retain every attempt."""
    request = prepare_ledger_extraction(text)
    caller = llm_call or _call_with_retry
    raw = ""
    attempts: list[LedgerStageAttempt] = []

    for attempt_index in range(_LEDGER_ATTEMPTS):
        prompt = (
            request.prompt if attempt_index == 0 else f"请只输出有效的 JSON 对象：\n{raw[:500]}"
        )
        started_at = time.time()
        try:
            raw = await caller(
                prompt,
                cloud_client,
                ollama_client,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                json_mode=request.json_mode,
            )
            parsed = _parse_promise_payload(raw) if _has_valid_promise_payload(raw) else None
            status = _attempt_status(raw, parsed)
            attempts.append(
                LedgerStageAttempt(
                    attempt_number=attempt_index + 1,
                    prompt=prompt,
                    raw_response=raw,
                    parsed_output=parsed,
                    status=status,
                    started_at=started_at,
                    ended_at=time.time(),
                    error=_attempt_error(status),
                )
            )
            if raw.strip() and parsed is not None:
                return LedgerStageResult(
                    request=request,
                    attempts=tuple(attempts),
                    raw_response=raw,
                    parsed_output=parsed,
                    termination_status=status,
                )
        except (json.JSONDecodeError, ValueError) as exc:
            attempts.append(
                LedgerStageAttempt(
                    attempt_number=attempt_index + 1,
                    prompt=prompt,
                    raw_response=None,
                    parsed_output=None,
                    status="invalid_json",
                    started_at=started_at,
                    ended_at=time.time(),
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            )
            if attempt_index == _LEDGER_ATTEMPTS - 1:
                return LedgerStageResult(
                    request=request,
                    attempts=tuple(attempts),
                    raw_response=raw,
                    parsed_output=[],
                    termination_status="invalid_json",
                    error_message="LLM 未返回有效 JSON，请重试",
                )
        except Exception as exc:
            status = "timeout" if isinstance(exc, TimeoutError) else "provider_error"
            attempts.append(
                LedgerStageAttempt(
                    attempt_number=attempt_index + 1,
                    prompt=prompt,
                    raw_response=None,
                    parsed_output=None,
                    status=status,
                    started_at=started_at,
                    ended_at=time.time(),
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            )
            return LedgerStageResult(
                request=request,
                attempts=tuple(attempts),
                raw_response=raw,
                parsed_output=[],
                termination_status=status,
                error_message=f"LLM 调用失败: {exc}",
            )

    status = "empty_response" if not raw.strip() else "invalid_json"
    message = (
        "LLM 返回空响应，请重试" if status == "empty_response" else "LLM 未返回有效 JSON，请重试"
    )
    return LedgerStageResult(
        request=request,
        attempts=tuple(attempts),
        raw_response=raw,
        parsed_output=[],
        termination_status=status,
        error_message=message,
    )


async def run_ledger_classification_stage(
    text: str,
    promises: list[dict],
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    llm_call: LedgerLLMCall | None = None,
) -> LedgerStageResult:
    """Run only production discharge classification for explicit promises."""
    request = prepare_ledger_classification(text, promises)
    caller = llm_call or _call_with_retry
    raw = ""
    attempts: list[LedgerStageAttempt] = []
    forced_terminal: tuple[str, str] | None = None

    for attempt_index in range(_LEDGER_ATTEMPTS):
        prompt = (
            request.prompt if attempt_index == 0 else f"请只输出有效的 JSON 数组：\n{raw[:500]}"
        )
        started_at = time.time()
        try:
            raw = await caller(
                prompt,
                cloud_client,
                ollama_client,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                json_mode=request.json_mode,
            )
            parsed = extract_json_array(raw) if raw.strip() else None
            status = _attempt_status(raw, parsed)
            attempts.append(
                LedgerStageAttempt(
                    attempt_number=attempt_index + 1,
                    prompt=prompt,
                    raw_response=raw,
                    parsed_output=parsed,
                    status=status,
                    started_at=started_at,
                    ended_at=time.time(),
                    error=_attempt_error(status),
                )
            )
            forced_terminal = None
            if raw.strip() and parsed is not None:
                return LedgerStageResult(
                    request=request,
                    attempts=tuple(attempts),
                    raw_response=raw,
                    parsed_output=parsed,
                    termination_status=status,
                )
        except (json.JSONDecodeError, ValueError) as exc:
            attempts.append(
                LedgerStageAttempt(
                    attempt_number=attempt_index + 1,
                    prompt=prompt,
                    raw_response=None,
                    parsed_output=None,
                    status="invalid_json",
                    started_at=started_at,
                    ended_at=time.time(),
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            )
            forced_terminal = ("invalid_json", str(exc))
            if attempt_index == _LEDGER_ATTEMPTS - 1:
                raw = "[]"
        except Exception as exc:
            status = "timeout" if isinstance(exc, TimeoutError) else "provider_error"
            logger.warning("discharge extraction unexpected error: %s", exc)
            attempts.append(
                LedgerStageAttempt(
                    attempt_number=attempt_index + 1,
                    prompt=prompt,
                    raw_response=None,
                    parsed_output=None,
                    status=status,
                    started_at=started_at,
                    ended_at=time.time(),
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            )
            forced_terminal = (status, str(exc))
            raw = "[]"

    if forced_terminal is not None:
        status, message = forced_terminal
        return LedgerStageResult(
            request=request,
            attempts=tuple(attempts),
            raw_response=raw,
            parsed_output=[],
            termination_status=status,
            error_message=message,
        )

    parsed = extract_json_array(raw) if raw.strip() else None
    status = _attempt_status(raw, parsed)
    return LedgerStageResult(
        request=request,
        attempts=tuple(attempts),
        raw_response=raw,
        parsed_output=parsed or [],
        termination_status=status,
        error_message=None if parsed is not None else status,
    )


def _discharge_map(parsed_output: list[Any]) -> dict[str, dict]:
    """Apply the production parser/map semantics, including partial maps."""
    discharge_map: dict[str, dict] = {}
    try:
        if parsed_output:
            for item in parsed_output:
                lid = str(item.get("promise_local_id", ""))
                discharge_map[lid] = item
    except Exception as exc:
        logger.warning("discharge map parsing failed: %s", exc)
    return discharge_map


def materialize_discharge_classifications(
    promises: list[dict],
    parsed_output: list[Any],
) -> list[dict[str, Any]]:
    """Expose production status mapping while preserving missing/invalid reasons."""
    by_local_id = _discharge_map(parsed_output)
    classifications: list[dict[str, Any]] = []
    for promise in promises:
        local_id = str(promise.get("local_id", ""))
        is_missing = local_id not in by_local_id
        item = by_local_id.get(local_id, {})
        raw_status = str(item.get("status", "unknown"))
        status = raw_status if raw_status in _SUBSTANTIVE_STATUSES else "unknown"
        classifications.append(
            {
                "promise_local_id": local_id,
                "status": status,
                "raw_status": raw_status,
                "discharge_quotes": item.get("discharge_quotes", []),
                "note": item.get("note") or None,
                "failure_reason": (
                    "missing_classification"
                    if is_missing
                    else "unknown_status"
                    if status == "unknown"
                    else None
                ),
            }
        )
    return classifications


async def build_ledger(
    doc_id: str,
    doc_title: str,
    text: str,
    store: CompanionStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: promise* → complete (或 error，不写脏数据)。"""
    # ── LLM #1: extract promises ──────────────────────────────────────────────
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "extracting_promises"}),
    }
    extraction = await run_ledger_extraction_stage(text, cloud_client, ollama_client)
    if extraction.termination_status not in {"success", "legal_empty"}:
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": extraction.error_message or "LLM 未返回有效 JSON，请重试"}
            ),
        }
        return
    raw_promises = extraction.parsed_output
    if not raw_promises:
        # No promises found — complete with zero
        logger.warning(
            "companion build_ledger 0 promises raw1(500)=%s",
            extraction.raw_response[:500],
        )
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
        yield {
            "event": "complete",
            "data": json.dumps(
                {
                    "ledger_id": ledger.id,
                    "promise_count": 0,
                    "by_status": {},
                    "warnings": ["LLM 未提取到承诺"],
                }
            ),
        }
        return

    # ── LLM #2: discharge resolution ─────────────────────────────────────────
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "matching_evidence"}),
    }
    classification = await run_ledger_classification_stage(
        text,
        raw_promises,
        cloud_client,
        ollama_client,
    )
    discharge_map = _discharge_map(classification.parsed_output)

    # ── Assemble promises + anchors ───────────────────────────────────────────
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "saving_ledger"}),
    }
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
        if status not in _SUBSTANTIVE_STATUSES:
            status = "unknown"
        note = dis_info.get("note") or None
        dis_ids: list[str] = []
        for dq in dis_info.get("discharge_quotes", []):
            da = make_anchor_from_quote(doc_id, text, str(dq))
            if da.status == "lost" and dq:  # LLM quote is paraphrase, try fuzzy
                da = relocate(da, text)
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
    yield {
        "event": "complete",
        "data": json.dumps(
            {
                "ledger_id": ledger.id,
                "promise_count": len(new_promises),
                "by_status": by_status,
                "warnings": warnings,
            }
        ),
    }


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
                relocated_map.get(a.id, a)
                for a in existing.anchors
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

    # Now patch in user-overridden promises
    if not overridden:
        if last_event and last_event["event"] == "complete":
            yield last_event
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
    by_status: dict[str, int] = {}
    for promise in fresh_ledger.promises:
        by_status[promise.status] = by_status.get(promise.status, 0) + 1
    previous_data = json.loads(last_event["data"]) if last_event else {}
    yield {
        "event": "complete",
        "data": json.dumps(
            {
                "ledger_id": fresh_ledger.id,
                "promise_count": len(fresh_ledger.promises),
                "by_status": by_status,
                "warnings": previous_data.get("warnings", []),
            }
        ),
    }


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
        result = await call_llm_chat(
            prompt, cloud_client, ollama_client, max_tokens=4096, temperature=0.4
        )
        return result or "（LLM 返回为空，请手动填写建议）"
    except Exception as exc:
        return f"（LLM 不可用：{exc}；请手动补充实验设计。）"
