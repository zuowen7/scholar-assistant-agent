"""Phase 0 tests: Answer quality verification.

TDD Red phase — tests exercise interfaces that do NOT exist yet.
"""
from __future__ import annotations

import pytest


class TestAnswerVerification:
    """Post-execution answer quality check."""

    def test_empty_answer_rejected(self, mock_verifier):
        """Empty answer should be flagged for retry."""
        result = mock_verifier.verify(
            query="解释一下什么是梯度下降",
            answer="",
        )
        assert result.should_retry is True
        assert result.confidence == 0.0

    def test_short_answer_for_complex_query(self, mock_verifier):
        """Complex query getting a 2-word answer → low confidence."""
        result = mock_verifier.verify(
            query="请详细分析这篇论文的方法论，包括实验设计、统计方法和局限性",
            answer="方法论不错。",
        )
        assert result.confidence < 0.5

    def test_answer_confidence_scoring(self, mock_verifier):
        """Well-structured answer gets high confidence."""
        long_answer = (
            "梯度下降是一种优化算法，用于最小化损失函数。"
            "其核心思想是沿着梯度的反方向迭代更新参数。"
            "学习率控制每次更新的步长，太大可能导致震荡，"
            "太小则收敛缓慢。常见的变体包括 SGD、Adam、RMSprop。"
        )
        result = mock_verifier.verify(
            query="什么是梯度下降？",
            answer=long_answer,
        )
        assert result.confidence > 0.5
        assert result.should_retry is False

    def test_verification_max_retries(self, mock_verifier):
        """Verification should not retry more than 2 times."""
        # Simulate a verification that has already retried twice
        result = mock_verifier.verify(
            query="复杂问题",
            answer="",
            retry_count=2,
        )
        assert result.should_retry is False  # Give up after 2 retries

    def test_verification_returns_reason(self, mock_verifier):
        """Verification result includes a human-readable reason."""
        result = mock_verifier.verify(
            query="写一篇论文",
            answer="好",
        )
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_verifier():
    """Create a mock verifier with verify() interface.

    Red phase: verify() logic will be implemented in agent.py during IMPL.
    """
    class _MockVerifier:
        def verify(self, query: str, answer: str, retry_count: int = 0):
            # Simple heuristic — will be replaced by LLM-based verification
            from dataclasses import dataclass

            @dataclass
            class Result:
                confidence: float
                should_retry: bool
                reason: str

            if retry_count >= 2:
                return Result(confidence=0.0, should_retry=False, reason="max retries reached")

            if not answer or not answer.strip():
                return Result(confidence=0.0, should_retry=True, reason="empty answer")

            query_words = len(query)
            answer_words = len(answer)
            ratio = answer_words / max(query_words, 1)

            if ratio < 0.1:
                return Result(
                    confidence=0.2,
                    should_retry=True,
                    reason=f"answer too short ({answer_words} chars for {query_words} char query)",
                )

            confidence = min(1.0, ratio / 0.5)
            return Result(
                confidence=confidence,
                should_retry=confidence < 0.3,
                reason="ok" if confidence >= 0.3 else "low confidence",
            )

    return _MockVerifier()
