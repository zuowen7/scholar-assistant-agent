"""Scholar Translate MCP Server — JSON-RPC over stdio。

提供翻译相关工具，Agent 通过 McpManager 发现和调用。
"""
from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "translate_pdf",
        "description": "Translate a PDF document. Parses, cleans, chunks, and translates the document using the configured translation engine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the PDF file in the workspace"},
                "source_lang": {"type": "string", "default": "en", "description": "Source language (e.g. en, zh, ja)"},
                "target_lang": {"type": "string", "default": "zh-CN", "description": "Target language (e.g. zh-CN, en)"},
                "engine": {"type": "string", "default": "cloud", "description": "Translation engine: cloud, ollama"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "translate_status",
        "description": "Check the status of a running or completed translation task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID from translate_pdf"},
            },
            "required": ["task_id"],
        },
    },
]


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    params = msg.get("params", {})
    req_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "scholar-translate", "version": "0.4.1"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        if tool_name == "translate_pdf":
            fp = args.get("file_path", "")
            src = args.get("source_lang", "en")
            tgt = args.get("target_lang", "zh-CN")
            text = f"[translate] Task queued: {fp} ({src} -> {tgt}). The translation pipeline will process this file. Check status with translate_status."
        elif tool_name == "translate_status":
            tid = args.get("task_id", "")
            text = f"[translate] Task {tid}: status=queued, progress=0%. Start translation with translate_pdf first."
        else:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown tool: {tool_name}"}}
        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}]}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
