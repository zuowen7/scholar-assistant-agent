"""TDD tests for Trident Compaction — 3-stage context compression.

Reference: claw-code rust/crates/runtime/src/trident.rs

Stages under test:
  1. Stage 1 Supersede — remove obsolete file operations (keep only latest write)
  2. Stage 2 Collapse — summarize chatty exchanges (short non-tool messages)
  3. Stage 3 Cluster — semantic grouping of similar messages
  4. TridentConfig + TridentStats
  5. Full pipeline: trident_compact_session
"""
from __future__ import annotations

import json

import pytest

from src.agent_v2.types import (
    Message,
    MessageRole,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    TokenUsage,
)


def _user_msg(text: str) -> Message:
    return Message(role=MessageRole.USER, blocks=[TextBlock(text=text)])


def _assistant_msg(text: str) -> Message:
    return Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text=text)])


def _system_msg(text: str) -> Message:
    return Message(role=MessageRole.SYSTEM, blocks=[TextBlock(text=text)])


def _tool_use_msg(name: str, tool_id: str, input_json: str) -> Message:
    return Message(role=MessageRole.ASSISTANT, blocks=[
        ToolUseBlock(id=tool_id, name=name, input=input_json),
    ])


def _tool_result_msg(tool_id: str, tool_name: str, output: str) -> Message:
    return Message(role=MessageRole.TOOL, blocks=[
        ToolResultBlock(tool_use_id=tool_id, tool_name=tool_name, output=output),
    ])


# ============================================================================
# 1. Stage 1: Supersede
# ============================================================================

class TestStage1Supersede:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.trident import stage1_supersede
        self.stage1 = stage1_supersede

    def test_no_file_ops_no_change(self):
        messages = [
            _user_msg("hello"),
            _assistant_msg("hi there"),
        ]
        kept, count = self.stage1(messages)
        assert len(kept) == 2
        assert count == 0

    def test_single_file_write_no_supersede(self):
        messages = [
            _tool_use_msg("write_file", "t1", '{"file_path": "a.txt", "content": "v1"}'),
            _tool_result_msg("t1", "write_file", "ok"),
        ]
        kept, count = self.stage1(messages)
        assert len(kept) == 2
        assert count == 0

    def test_earlier_reads_superseded_by_later_write(self):
        """If we read a file, then write to it, the read is obsolete."""
        messages = [
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
            _tool_result_msg("t1", "read_file", "old content"),
            _tool_use_msg("write_file", "t2", '{"file_path": "a.txt", "content": "new"}'),
            _tool_result_msg("t2", "write_file", "ok"),
        ]
        kept, count = self.stage1(messages)
        # The read_file tool_use + tool_result should be superseded (2 messages)
        assert count == 2
        # Only the write messages remain
        assert len(kept) == 2

    def test_earlier_writes_superseded_by_later_write(self):
        """If we write to a file twice, the first write is obsolete."""
        messages = [
            _user_msg("edit the file"),
            _tool_use_msg("write_file", "t1", '{"file_path": "a.txt", "content": "v1"}'),
            _tool_result_msg("t1", "write_file", "ok"),
            _tool_use_msg("write_file", "t2", '{"file_path": "a.txt", "content": "v2"}'),
            _tool_result_msg("t2", "write_file", "ok"),
        ]
        kept, count = self.stage1(messages)
        assert count >= 2  # first write op superseded
        assert len(kept) == 3  # user msg + second write pair

    def test_different_files_not_superseded(self):
        """Reads of file A are not superseded by writes to file B."""
        messages = [
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
            _tool_result_msg("t1", "read_file", "content A"),
            _tool_use_msg("write_file", "t2", '{"file_path": "b.txt", "content": "new"}'),
            _tool_result_msg("t2", "write_file", "ok"),
        ]
        kept, count = self.stage1(messages)
        assert count == 0
        assert len(kept) == 4

    def test_edit_also_supersedes(self):
        """str_replace (Edit) also makes earlier reads/writes obsolete."""
        messages = [
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
            _tool_result_msg("t1", "read_file", "content"),
            _tool_use_msg("str_replace", "t2", '{"file_path": "a.txt", "old_string": "x", "new_string": "y"}'),
            _tool_result_msg("t2", "str_replace", "ok"),
        ]
        kept, count = self.stage1(messages)
        assert count == 2

    def test_mixed_user_messages_preserved(self):
        """User messages between file ops should be preserved."""
        messages = [
            _user_msg("read a.txt"),
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
            _tool_result_msg("t1", "read_file", "content"),
            _user_msg("now change it"),
            _tool_use_msg("write_file", "t2", '{"file_path": "a.txt", "content": "new"}'),
            _tool_result_msg("t2", "write_file", "ok"),
        ]
        kept, count = self.stage1(messages)
        # read op superseded, but user messages preserved
        user_msgs = [m for m in kept if m.role == MessageRole.USER]
        assert len(user_msgs) == 2


# ============================================================================
# 2. Stage 2: Collapse
# ============================================================================

class TestStage2Collapse:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.trident import stage2_collapse
        self.stage2 = stage2_collapse

    def test_short_messages_no_collapse(self):
        messages = [_user_msg("hi"), _assistant_msg("hello")]
        result, chains, collapsed = self.stage2(messages, threshold=4)
        assert len(result) == 2
        assert chains == 0
        assert collapsed == 0

    def test_many_chatty_messages_collapse(self):
        """4+ short non-tool messages in a row get collapsed to 1 summary."""
        messages = [
            _user_msg("ok"),
            _assistant_msg("sure"),
            _user_msg("yes"),
            _assistant_msg("fine"),
            _user_msg("go ahead"),
        ]
        result, chains, collapsed = self.stage2(messages, threshold=4)
        assert chains == 1
        assert collapsed == 5
        assert len(result) == 1
        assert "[Collapsed Conversation]" in result[0].text_content()

    def test_tool_messages_not_collapsed(self):
        """Tool-use messages are not 'chatty' and should not be collapsed."""
        messages = [
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
            _tool_result_msg("t1", "read_file", "content"),
        ]
        result, chains, collapsed = self.stage2(messages, threshold=2)
        assert chains == 0

    def test_chatty_then_tool_preserves_tool(self):
        """Chatty messages collapse, but tool messages after them are preserved."""
        messages = [
            _user_msg("ok"), _assistant_msg("sure"), _user_msg("go"),
            _assistant_msg("fine"), _user_msg("yes"),
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
        ]
        result, chains, collapsed = self.stage2(messages, threshold=4)
        # Chatty messages collapse, tool message preserved
        tool_msgs = [m for m in result if any(
            isinstance(b, ToolUseBlock) for b in m.blocks)]
        assert len(tool_msgs) == 1

    def test_below_threshold_no_collapse(self):
        messages = [
            _user_msg("ok"),
            _assistant_msg("sure"),
            _user_msg("yes"),
        ]
        result, chains, collapsed = self.stage2(messages, threshold=4)
        assert chains == 0
        assert len(result) == 3


# ============================================================================
# 3. Stage 3: Cluster
# ============================================================================

class TestStage3Cluster:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.trident import stage3_cluster
        self.stage3 = stage3_cluster

    def test_too_few_messages_no_cluster(self):
        messages = [_user_msg("hi"), _assistant_msg("hello")]
        result, clusters, clustered = self.stage3(messages, min_size=3, threshold=0.6)
        assert clusters == 0
        assert clustered == 0

    def test_identical_messages_cluster(self):
        """Messages with identical content should cluster together."""
        messages = [
            _user_msg("check status"),
            _assistant_msg("ok"),
            _user_msg("check status"),
            _assistant_msg("ok"),
            _user_msg("check status"),
            _assistant_msg("ok"),
        ]
        result, clusters, clustered = self.stage3(messages, min_size=3, threshold=0.6)
        assert clusters >= 1
        assert clustered >= 3

    def test_different_messages_no_cluster(self):
        """Completely different messages should not cluster."""
        messages = [
            _user_msg("read file A from disk"),
            _assistant_msg("the file contains configuration data"),
            _user_msg("translate document to Chinese language"),
            _assistant_msg("translation is complete now"),
            _user_msg("export the result to PDF format"),
            _assistant_msg("PDF has been generated successfully"),
        ]
        result, clusters, clustered = self.stage3(messages, min_size=3, threshold=0.9)
        assert clusters == 0


# ============================================================================
# 4. TridentConfig + TridentStats
# ============================================================================

class TestTridentConfigAndStats:

    def test_config_defaults(self):
        from src.agent_v2.runtime.trident import TridentConfig
        config = TridentConfig()
        assert config.supersede_enabled
        assert config.collapse_enabled
        assert config.cluster_enabled
        assert config.collapse_threshold == 4
        assert config.cluster_min_size == 3
        assert config.cluster_similarity_threshold == 0.6

    def test_config_custom(self):
        from src.agent_v2.runtime.trident import TridentConfig
        config = TridentConfig(supersede_enabled=False, collapse_threshold=8)
        assert not config.supersede_enabled
        assert config.collapse_threshold == 8

    def test_stats_default(self):
        from src.agent_v2.runtime.trident import TridentStats
        stats = TridentStats()
        assert stats.superseded_count == 0
        assert stats.collapsed_chains == 0
        assert stats.clusters_found == 0
        assert stats.original_message_count == 0
        assert stats.final_message_count == 0

    def test_stats_format_report(self):
        from src.agent_v2.runtime.trident import TridentStats
        stats = TridentStats(
            superseded_count=5,
            collapsed_chains=2,
            messages_collapsed=8,
            clusters_found=1,
            messages_clustered=3,
            tokens_saved_estimate=10000,
            original_message_count=20,
            final_message_count=10,
        )
        report = stats.format_report()
        assert "Supersede" in report
        assert "5 obsolete" in report
        assert "Collapse" in report
        assert "Cluster" in report


# ============================================================================
# 5. Full pipeline: trident_compact_session
# ============================================================================

class TestTridentCompactSession:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.trident import trident_compact_session, TridentConfig
        self.trident_compact = trident_compact_session
        self.TridentConfig = TridentConfig

    def test_no_compaction_needed(self):
        from src.agent_v2.runtime.compact import CompactionConfig
        from src.agent_v2.runtime.session import Session

        session = Session()
        session.append(_user_msg("hi"))
        session.append(_assistant_msg("hello"))
        config = CompactionConfig(input_token_threshold=1_000_000)
        result = self.trident_compact(session, config, self.TridentConfig())
        assert result is not None

    def test_supersede_then_compact(self):
        from src.agent_v2.runtime.compact import CompactionConfig
        from src.agent_v2.runtime.session import Session

        session = Session()
        for m in [
            _user_msg("read a.txt"),
            _tool_use_msg("read_file", "t1", '{"file_path": "a.txt"}'),
            _tool_result_msg("t1", "read_file", "content v1"),
            _user_msg("write a.txt"),
            _tool_use_msg("write_file", "t2", '{"file_path": "a.txt", "content": "v2"}'),
            _tool_result_msg("t2", "write_file", "ok"),
        ]:
            session.append(m)
        config = CompactionConfig(input_token_threshold=1_000_000)
        result = self.trident_compact(session, config, self.TridentConfig())
        assert result is not None

    def test_stages_can_be_disabled(self):
        from src.agent_v2.runtime.compact import CompactionConfig
        from src.agent_v2.runtime.session import Session

        session = Session()
        session.append(_user_msg("hi"))
        session.append(_assistant_msg("hello"))
        config = CompactionConfig(input_token_threshold=1_000_000)
        no_trident = self.TridentConfig(
            supersede_enabled=False, collapse_enabled=False, cluster_enabled=False,
        )
        result = self.trident_compact(session, config, no_trident)
        assert result is not None
