"""翻译管道性能基准测试

测量各阶段的耗时和资源消耗，帮助识别性能瓶颈。
使用方法: python -m tests.unit.test_benchmark
"""

from __future__ import annotations

import asyncio
import time
import statistics
from pathlib import Path
from dataclasses import dataclass, field

from src.parser import extract_document
from src.cleaner import clean_text_full
from src.chunker import chunk_text_full
from src.translator.ollama_client import OllamaClient
from src.translator.cloud_client import CloudClient


@dataclass
class BenchmarkResult:
    """单次测试结果"""
    stage: str
    duration_ms: float
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineBenchmark:
    """翻译管道基准测试"""
    doc_path: str = ""
    engine: str = "ollama"
    results: list[BenchmarkResult] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return sum(r.duration_ms for r in self.results)

    def summary(self) -> dict:
        """汇总统计"""
        by_stage = {}
        for r in self.results:
            if r.stage not in by_stage:
                by_stage[r.stage] = []
            by_stage[r.stage].append(r.duration_ms)

        stage_stats = {}
        for stage, durations in by_stage.items():
            stage_stats[stage] = {
                "count": len(durations),
                "total_ms": sum(durations),
                "avg_ms": statistics.mean(durations),
                "min_ms": min(durations),
                "max_ms": max(durations),
                "stdev_ms": statistics.stdev(durations) if len(durations) > 1 else 0,
            }

        return {
            "doc_path": self.doc_path,
            "engine": self.engine,
            "total_ms": round(self.total_ms, 1),
            "total_s": round(self.total_ms / 1000, 2),
            "stage_count": len(self.results),
            "stage_stats": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in stage_stats.items()},
        }


async def benchmark_parsing(file_path: str) -> BenchmarkResult:
    """解析阶段基准测试"""
    start = time.perf_counter()
    doc = await asyncio.to_thread(extract_document, file_path)
    dur = (time.perf_counter() - start) * 1000

    return BenchmarkResult(
        stage="parse",
        duration_ms=round(dur, 1),
        metadata={
            "pages": doc.page_count,
            "chars": len(doc.full_text),
        },
    )


async def benchmark_cleaning(text: str) -> BenchmarkResult:
    """清洗阶段基准测试"""
    start = time.perf_counter()
    result = await asyncio.to_thread(clean_text_full, text)
    dur = (time.perf_counter() - start) * 1000

    return BenchmarkResult(
        stage="clean",
        duration_ms=round(dur, 1),
        metadata={
            "chars_before": len(text),
            "chars_after": len(result.text),
        },
    )


async def benchmark_chunking(text: str, max_tokens: int = 2048) -> BenchmarkResult:
    """切块阶段基准测试"""
    start = time.perf_counter()
    result = await asyncio.to_thread(chunk_text_full, text, max_tokens, 128, "sentence", True)
    dur = (time.perf_counter() - start) * 1000

    return BenchmarkResult(
        stage="chunk",
        duration_ms=round(dur, 1),
        metadata={
            "chunks": len(result.chunks),
            "refs_chars": len(result.references_text),
        },
    )


async def benchmark_translation(
    texts: list[str],
    engine: str = "ollama",
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    cloud_base_url: str = "",
    cloud_api_key: str = "",
    cloud_model: str = "",
) -> list[BenchmarkResult]:
    """翻译阶段基准测试（逐块计时）"""
    results = []
    prev_trans = ""

    if engine == "cloud":
        client = CloudClient(
            base_url=cloud_base_url,
            api_key=cloud_api_key,
            model=cloud_model or model,
        )
    else:
        client = OllamaClient(
            base_url=ollama_url,
            model=model,
        )

    try:
        for i, text in enumerate(texts):
            start = time.perf_counter()
            result = await asyncio.to_thread(client.translate, text, prev_trans)
            dur = (time.perf_counter() - start) * 1000

            results.append(BenchmarkResult(
                stage=f"translate_{i}",
                duration_ms=round(dur, 1),
                metadata={
                    "chars_in": len(text),
                    "chars_out": len(result.translated),
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                },
            ))
            prev_trans = result.translated
    finally:
        if hasattr(client, "close"):
            client.close()

    return results


def run_full_benchmark(
    file_path: str,
    engine: str = "ollama",
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    cloud_base_url: str = "",
    cloud_api_key: str = "",
    cloud_model: str = "",
    max_tokens: int = 2048,
) -> dict:
    """运行完整翻译管道基准测试

    Args:
        file_path: 文档路径
        engine: 引擎类型 "ollama" | "cloud"
        其余参数对应各引擎的配置

    Returns:
        基准测试汇总结果
    """
    bench = PipelineBenchmark(doc_path=file_path, engine=engine)

    # 解析
    bench.results.append(asyncio.run(benchmark_parsing(file_path)))
    doc = asyncio.run(benchmark_parsing(file_path))  # 重新获取文本用于后续阶段
    raw_text = extract_document(file_path).full_text

    # 清洗
    bench.results.append(asyncio.run(benchmark_cleaning(raw_text)))
    clean = asyncio.run(benchmark_cleaning(raw_text))
    clean_text = clean_text_full(raw_text).text

    # 切块
    bench.results.append(asyncio.run(benchmark_chunking(clean_text, max_tokens)))
    chunked = asyncio.run(benchmark_chunking(clean_text, max_tokens))
    chunks = chunk_text_full(clean_text, max_tokens, 128, "sentence", True).chunks
    chunk_texts = [c.text for c in chunks]

    # 翻译（只测第一块，避免耗时过长）
    if chunk_texts:
        translate_results = asyncio.run(benchmark_translation(
            chunk_texts[:1],  # 只测第一块
            engine=engine,
            ollama_url=ollama_url,
            model=model,
            cloud_base_url=cloud_base_url,
            cloud_api_key=cloud_api_key,
            cloud_model=cloud_model,
        ))
        bench.results.extend(translate_results)

    return bench.summary()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python -m tests.unit.test_benchmark <文档路径>")
        print("示例: python -m tests.unit.test_benchmark ./data/input/paper.pdf")
        sys.exit(1)

    file_path = sys.argv[1]
    if not Path(file_path).exists():
        print(f"文件不存在: {file_path}")
        sys.exit(1)

    print(f"基准测试: {file_path}")
    print("=" * 50)

    result = run_full_benchmark(file_path, engine="ollama")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))