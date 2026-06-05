"""Trident Compaction — 3-stage context compression.

Port of claw-code rust/crates/runtime/src/trident.rs.

Stages:
  1. Supersede — remove obsolete file operations (keep only latest write per file)
  2. Collapse — summarize chatty exchanges (consecutive short non-tool messages)
  3. Cluster — semantic grouping of similar messages
"""
from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field

from src.agent_v2.runtime.compact import CompactionConfig, compact_session, estimate_session_tokens
from src.agent_v2.runtime.session import Session
from src.agent_v2.types import (
    ContentBlock,
    Message,
    MessageRole,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


# ---------------------------------------------------------------------------
# Config & Stats
# ---------------------------------------------------------------------------

@dataclass
class TridentConfig:
    supersede_enabled: bool = True
    collapse_enabled: bool = True
    cluster_enabled: bool = True
    collapse_threshold: int = 4
    cluster_min_size: int = 3
    cluster_similarity_threshold: float = 0.6
    max_file_operations: int = 100


@dataclass
class TridentStats:
    superseded_count: int = 0
    collapsed_chains: int = 0
    messages_collapsed: int = 0
    clusters_found: int = 0
    messages_clustered: int = 0
    tokens_saved_estimate: int = 0
    original_message_count: int = 0
    final_message_count: int = 0

    def format_report(self) -> str:
        compression = (
            self.original_message_count / self.final_message_count
            if self.final_message_count > 0 else 1.0
        )
        lines = [
            "Trident Compaction Complete",
            f"  Stage 1 (Supersede): {self.superseded_count} obsolete removed",
            f"  Stage 2 (Collapse):  {self.messages_collapsed} -> {self.collapsed_chains} summaries",
            f"  Stage 3 (Cluster):   {self.messages_clustered} -> {self.clusters_found} clusters",
            f"  Original: {self.original_message_count} messages",
            f"  Final:    {self.final_message_count} messages",
            f"  Compression: {compression:.1f}x",
            f"  Tokens saved: ~{self.tokens_saved_estimate}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FILE_TOOLS = {"read_file", "write_file", "str_replace", "Read", "Write", "Edit"}
_WRITE_TOOLS = {"write_file", "str_replace", "Write", "Edit"}


class _FileOp:
    READ = "read"
    WRITE = "write"


def _extract_file_path_from_block(block: ContentBlock) -> tuple[str, str] | None:
    """Extract (file_path, op_type) from a tool use or tool result block."""
    if isinstance(block, ToolUseBlock):
        if block.name not in _FILE_TOOLS:
            return None
        path = _path_from_input(block.name, block.input)
        if not path:
            return None
        op = _FileOp.WRITE if block.name in _WRITE_TOOLS else _FileOp.READ
        return (path, op)
    if isinstance(block, ToolResultBlock):
        if block.tool_name not in _FILE_TOOLS:
            return None
        path = _path_from_output(block.output)
        if not path:
            return None
        op = _FileOp.WRITE if block.tool_name in _WRITE_TOOLS else _FileOp.READ
        return (path, op)
    return None


def _path_from_input(tool_name: str, input_str: str) -> str | None:
    try:
        obj = json.loads(input_str) if isinstance(input_str, str) else input_str
        if isinstance(obj, dict):
            return obj.get("file_path") or obj.get("path")
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _path_from_output(output: str) -> str | None:
    try:
        obj = json.loads(output)
        if isinstance(obj, dict):
            return obj.get("file_path") or obj.get("path")
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: first line "path: xxx" or "ok: wrote xxx"
    for line in output.splitlines()[:1]:
        if line.startswith("ok: wrote "):
            return line.split("wrote ", 1)[-1].split(" ")[0]
    return None


# ---------------------------------------------------------------------------
# Stage 1: Supersede
# ---------------------------------------------------------------------------

def stage1_supersede(messages: list[Message]) -> tuple[list[Message], int]:
    """Remove obsolete file operations — keep only the latest write per file.

    When a message at index i is superseded, the next message (tool result)
    at index i+1 is also superseded if it's a TOOL role message for the same tool.
    """
    # Collect all file operations per path
    file_ops: dict[str, list[tuple[int, str]]] = {}  # path -> [(index, op_type)]
    for i, msg in enumerate(messages):
        for block in msg.blocks:
            result = _extract_file_path_from_block(block)
            if result:
                path, op = result
                file_ops.setdefault(path, []).append((i, op))

    # Find obsolete indices
    obsolete: set[int] = set()
    for path, ops in file_ops.items():
        if len(ops) < 2:
            continue
        # Find last write index
        last_write_idx = None
        for idx, op in reversed(ops):
            if op == _FileOp.WRITE:
                last_write_idx = idx
                break
        if last_write_idx is None:
            continue
        # Everything before the last write for this path is obsolete
        for idx, op in ops:
            if idx < last_write_idx:
                obsolete.add(idx)
                # Also supersede the corresponding tool result message
                if idx + 1 < len(messages) and messages[idx + 1].role == MessageRole.TOOL:
                    obsolete.add(idx + 1)

    superseded_count = len(obsolete)
    kept = [msg for i, msg in enumerate(messages) if i not in obsolete]
    return kept, superseded_count


# ---------------------------------------------------------------------------
# Stage 2: Collapse
# ---------------------------------------------------------------------------

def stage2_collapse(
    messages: list[Message], threshold: int = 4,
) -> tuple[list[Message], int, int]:
    """Collapse consecutive chatty (short, non-tool) messages into summaries."""
    if len(messages) < threshold:
        return messages, 0, 0

    def _is_chatty(msg: Message) -> bool:
        has_tool = any(isinstance(b, (ToolUseBlock, ToolResultBlock)) for b in msg.blocks)
        if has_tool:
            return False
        total_chars = sum(
            len(b.text if isinstance(b, TextBlock) else
                b.input if isinstance(b, ToolUseBlock) else
                b.output if isinstance(b, ToolResultBlock) else
                b.thinking if hasattr(b, 'thinking') else "")
            for b in msg.blocks
        )
        return total_chars < 200

    result: list[Message] = []
    buffer: list[Message] = []
    total_chains = 0
    total_collapsed = 0

    for msg in messages:
        if _is_chatty(msg):
            buffer.append(msg)
        else:
            if len(buffer) >= threshold:
                summary = _collapse_summary(buffer)
                total_chains += 1
                total_collapsed += len(buffer)
                result.append(Message(
                    role=MessageRole.SYSTEM,
                    blocks=[TextBlock(text=f"[Collapsed Conversation]\n{summary}")],
                ))
            else:
                result.extend(buffer)
            buffer = []
            result.append(msg)

    # Flush remaining buffer
    if len(buffer) >= threshold:
        summary = _collapse_summary(buffer)
        total_chains += 1
        total_collapsed += len(buffer)
        result.append(Message(
            role=MessageRole.SYSTEM,
            blocks=[TextBlock(text=f"[Collapsed Conversation]\n{summary}")],
        ))
    else:
        result.extend(buffer)

    return result, total_chains, total_collapsed


def _collapse_summary(messages: list[Message]) -> str:
    user_count = sum(1 for m in messages if m.role == MessageRole.USER)
    assistant_count = sum(1 for m in messages if m.role == MessageRole.ASSISTANT)
    topics: list[str] = []
    for m in messages:
        for b in m.blocks:
            if isinstance(b, TextBlock) and b.text.strip():
                first_line = b.text.strip().split("\n")[0][:80]
                if first_line not in topics:
                    topics.append(first_line)
                if len(topics) >= 5:
                    break
        if len(topics) >= 5:
            break

    lines = [f"Collapsed {len(messages)} messages ({user_count} user, {assistant_count} assistant)."]
    if topics:
        lines.append("Topics:")
        for t in topics:
            lines.append(f"  - {t}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 3: Cluster
# ---------------------------------------------------------------------------

def stage3_cluster(
    messages: list[Message], min_size: int = 3, threshold: float = 0.6,
) -> tuple[list[Message], int, int]:
    """Group semantically similar messages into clusters."""
    if len(messages) < min_size:
        return messages, 0, 0

    # Build fingerprints: (index, normalized_text)
    fingerprints: list[tuple[int, str]] = []
    for i, msg in enumerate(messages):
        text = msg.text_content().strip().lower() if hasattr(msg, 'text_content') else ""
        if text:
            fingerprints.append((i, text))

    if len(fingerprints) < min_size:
        return messages, 0, 0

    # Simple clustering: compare word sets
    cluster_assignments: dict[int, int] = {}
    cluster_id = 0

    for i, (idx_i, text_i) in enumerate(fingerprints):
        if idx_i in cluster_assignments:
            continue
        members = [idx_i]
        words_i = set(text_i.split())
        if not words_i:
            continue

        for j, (idx_j, text_j) in enumerate(fingerprints):
            if j <= i or idx_j in cluster_assignments:
                continue
            words_j = set(text_j.split())
            if not words_j:
                continue
            # Jaccard similarity
            intersection = len(words_i & words_j)
            union = len(words_i | words_j)
            sim = intersection / union if union > 0 else 0.0
            if sim >= threshold:
                members.append(idx_j)

        if len(members) >= min_size:
            for m in members:
                cluster_assignments[m] = cluster_id
            cluster_id += 1

    if not cluster_assignments:
        return messages, 0, 0

    total_clustered = len(cluster_assignments)
    clusters_found = cluster_id

    # Build cluster summaries
    cluster_buffers: dict[int, list[int]] = {}
    for msg_idx, cid in cluster_assignments.items():
        cluster_buffers.setdefault(cid, []).append(msg_idx)

    result: list[Message] = []
    seen_clusters: set[int] = set()
    for i, msg in enumerate(messages):
        if i in cluster_assignments:
            cid = cluster_assignments[i]
            if cid not in seen_clusters:
                seen_clusters.add(cid)
                members = cluster_buffers[cid]
                texts = []
                for midx in members:
                    t = messages[midx].text_content() if hasattr(messages[midx], 'text_content') else ""
                    if t:
                        texts.append(t[:80])
                summary = f"[Clustered {len(members)} messages]\n" + "\n".join(f"  - {t}" for t in texts[:5])
                result.append(Message(role=MessageRole.SYSTEM, blocks=[TextBlock(text=summary)]))
            # Skip the individual message
        else:
            result.append(msg)

    return result, clusters_found, total_clustered


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def trident_compact_session(
    session: Session,
    compaction_config: CompactionConfig,
    trident_config: TridentConfig,
) -> list[Message]:
    """Run the full Trident compaction pipeline, then apply standard compaction."""
    original_count = len(session.messages)
    original_tokens = estimate_session_tokens(session.messages)

    stats = TridentStats(original_message_count=original_count)
    messages = list(session.messages)

    if trident_config.supersede_enabled:
        messages, count = stage1_supersede(messages)
        stats.superseded_count = count

    if trident_config.collapse_enabled:
        messages, chains, collapsed = stage2_collapse(messages, trident_config.collapse_threshold)
        stats.collapsed_chains = chains
        stats.messages_collapsed = collapsed

    if trident_config.cluster_enabled:
        messages, clusters, clustered = stage3_cluster(
            messages, trident_config.cluster_min_size, trident_config.cluster_similarity_threshold,
        )
        stats.clusters_found = clusters
        stats.messages_clustered = clustered

    stats.final_message_count = len(messages)

    # Apply standard compaction on the trident-processed messages
    return compact_session(messages, compaction_config.input_token_threshold)
