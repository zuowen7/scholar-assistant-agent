"""手动测试翻译管道"""
import logging, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
from src.parser import extract_document
from src.cleaner import clean_text_full
from src.chunker import chunk_text_full
from src.formatter import format_output
from src.translator.ollama_client import OllamaClient
from src.translator.context import extract_document_context

def run(pdf_path, output_path):
    print(f"=== {pdf_path} ===")
    doc = extract_document(pdf_path)
    raw = doc.full_text
    print(f"[1] {doc.page_count} pages, {len(raw)} chars")
    clean_result = clean_text_full(raw)
    print(f"[2] {len(clean_result.text)} chars, refs={clean_result.has_references}")
    chunks = chunk_text_full(clean_result.text, max_tokens=2048, overlap_tokens=128)
    print(f"[3] {len(chunks.chunks)} chunks")
    for i, c in enumerate(chunks.chunks):
        print(f"  chunk {i}: {len(c.text)} chars")

    client = OllamaClient(base_url="http://127.0.0.1:11434", model="qwen3:8b",
        temperature=0.3, num_predict=16384,
        system_prompt="你是一位资深学术文献翻译专家。逐句完整翻译，不跳过不省略。数学公式和引用标记保持原样。只输出中文翻译，不要前言或总结。",
        timeout=300.0)
    doc_ctx = extract_document_context(raw)
    if doc_ctx: client.set_document_context(doc_ctx)
    results = []
    t0 = time.time()
    for i, chunk in enumerate(chunks.chunks):
        prev = results[-1].translated if results else ""
        print(f"[4] {i+1}/{len(chunks.chunks)} ({len(chunk.text)}c)...", end=" ", flush=True)
        t1 = time.time()
        result = client.translate(chunk.text, prev)
        print(f"done ({time.time()-t1:.0f}s, {result.completion_tokens}t)")
        results.append(result)
    client.close()
    print(f"[4] total {time.time()-t0:.0f}s")
    content = format_output(results, output_format="bilingual", file_format="markdown")
    with open(output_path, "w", encoding="utf-8") as f: f.write(content)
    print(f"[5] {output_path} ({len(content)} chars)")

if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "../attention.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "../test_attention_v2.md"
    run(pdf, out)
