"""Scholar Translate - 学术文献翻译工具主入口"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

from src.chunker import chunk_text_full
from src.cleaner import clean_text_full
from src.formatter import format_output
from src.formatter.renderer import save_output
from src.parser import extract_pages
from src.translator.ollama_client import OllamaClient

logger = logging.getLogger("scholar-translate")


def load_config(config_path: str | Path) -> dict:
    """加载配置文件"""
    config_path = Path(config_path)
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def setup_logging(verbose: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> None:
    """主流程"""
    parser = argparse.ArgumentParser(
        prog="scholar-translate",
        description="学术文献智能翻译工具",
    )
    parser.add_argument("pdf", help="输入 PDF 文件路径")
    parser.add_argument("-o", "--output", help="输出文件路径（默认: 同目录下 .md 文件）")
    parser.add_argument("-c", "--config", default="config/default.yaml", help="配置文件路径")
    parser.add_argument("-f", "--format", choices=["bilingual", "translated_only", "parallel"],
                        help="输出格式（覆盖配置文件）")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    config = load_config(args.config)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error("文件不存在: %s", pdf_path)
        sys.exit(1)

    # 输出路径
    output_path = args.output or str(pdf_path.with_suffix(".md"))

    logger.info(" Scholar Translate v0.1.0")
    logger.info("输入: %s", pdf_path)

    # Step 1: PDF 解析
    logger.info("[1/5] 解析 PDF...")
    t0 = time.time()
    doc = extract_pages(pdf_path)
    raw_text = doc.full_text
    dual_pages = sum(1 for p in doc.pages if p.is_dual_column)
    logger.info("  → %d 页, %d 字符", doc.page_count, len(raw_text))
    if dual_pages:
        logger.info("  → 检测到 %d 页双栏布局", dual_pages)

    # Step 2: 文本清洗
    logger.info("[2/5] 清洗文本...")
    clean_result = clean_text_full(raw_text)
    cleaned = clean_result.text
    logger.info("  → 清洗后 %d 字符", len(cleaned))
    if clean_result.has_references:
        logger.info(
            "  → 检测到引用区 (位置 %d, %d 字符)",
            clean_result.references_start,
            len(clean_result.references_text),
        )

    # Step 3: 文本切块
    logger.info("[3/5] 切块...")
    chunker_cfg = config.get("chunker", {})
    chunk_result = chunk_text_full(
        cleaned,
        max_tokens=chunker_cfg.get("max_tokens", 2048),
        overlap_tokens=chunker_cfg.get("overlap_tokens", 128),
        strategy=chunker_cfg.get("strategy", "sentence"),
        skip_references=True,
    )
    chunks = chunk_result.chunks
    references_text = chunk_result.references_text
    logger.info("  → %d 个文本块", len(chunks))
    if references_text:
        logger.info("  → 引用区 %d 字符已跳过", len(references_text))

    # Step 4: 翻译
    logger.info("[4/5] 翻译中...")
    trans_cfg = config.get("translator", {})
    client = OllamaClient(
        base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
        model=trans_cfg.get("model", "qwen3"),
        temperature=trans_cfg.get("temperature", 0.3),
        num_predict=trans_cfg.get("num_predict", 4096),
        system_prompt=trans_cfg.get("system_prompt", ""),
        timeout=trans_cfg.get("timeout", 300.0),
    )

    # 健康检查
    if not client.health_check():
        logger.error("Ollama 服务不可达，请确认已启动: ollama serve")
        sys.exit(1)

    results = []
    for i, chunk in enumerate(chunks):
        logger.info("  翻译块 %d/%d (%d tokens)...", i + 1, len(chunks), chunk.estimated_tokens)
        try:
            result = client.translate(chunk.text)
            results.append(result)
            logger.debug("  → %d tokens 生成", result.completion_tokens)
        except (ConnectionError, ValueError) as e:
            logger.error("  翻译块 %d 失败: %s", i + 1, e)
            sys.exit(1)

    # Step 5: 格式化输出
    logger.info("[5/5] 生成输出...")
    fmt_cfg = config.get("formatter", {})
    output_format = args.format or fmt_cfg.get("output_format", "bilingual")
    content = format_output(results, output_format=output_format)

    # 追加未翻译的引用区
    if references_text:
        content += "\n\n---\n\n## References\n\n" + references_text

    saved = save_output(content, output_path)

    elapsed = time.time() - t0
    logger.info("完成! 输出: %s (%.1fs)", saved, elapsed)


if __name__ == "__main__":
    main()
