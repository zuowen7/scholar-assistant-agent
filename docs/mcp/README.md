# Scholar Assistant MCP Server

Scholar Assistant 暴露了 16 个学术工具（翻译、解析、检索、润色、大纲、arXiv 搜索等）作为 [Model Context Protocol](https://modelcontextprotocol.io) 端点，可通过 stdio 接入任何 MCP 兼容客户端。

Scholar Assistant exposes 16 academic tools (translate, parse, search, polish, outline, arXiv search, etc.) as Model Context Protocol endpoints over stdio, compatible with any MCP client.

## 运行方式 / Running

```bash
# 从项目根目录 / From project root
cd python
set PYTHONPATH=python/src        # Windows
export PYTHONPATH=python/src      # Linux/macOS
set HTTP_PROXY=                   # Windows: clear proxy (httpx bug)
unset HTTP_PROXY                  # Linux/macOS
python -m src.agent.mcp_server
```

或使用启动脚本 / Or use the launcher scripts:
- Windows: `python\scripts\run_mcp_server.bat`
- Linux/macOS: `python/scripts/run_mcp_server.sh`

## 环境变量 / Environment Variables

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OLLAMA_BASE_URL` | Ollama 服务地址 | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama 模型名称 | `qwen3:8b` |
| `CLOUD_BASE_URL` | 云端 LLM API 地址 | _(空，使用 Ollama)_ |
| `CLOUD_API_KEY` | 云端 LLM API Key | _(空)_ |
| `CLOUD_MODEL` | 云端模型名称 | _(空)_ |

---

## Claude Desktop

### macOS

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "scholar-assistant": {
      "command": "python",
      "args": ["-m", "src.agent.mcp_server"],
      "cwd": "/path/to/scholar-assistant/python",
      "env": {
        "PYTHONPATH": "python/src",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "qwen3:8b"
      }
    }
  }
}
```

### Windows

编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "scholar-assistant": {
      "command": "python",
      "args": ["-m", "src.agent.mcp_server"],
      "cwd": "C:\\path\\to\\scholar-assistant\\python",
      "env": {
        "PYTHONPATH": "python/src",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "qwen3:8b"
      }
    }
  }
}
```

> **Windows 注意**：必须清空 `HTTP_PROXY` / `HTTPS_PROXY`，否则 httpx 会在 import 时挂起。

## Cursor

编辑 `~/.cursor/mcp.json`（macOS/Linux）或 `%USERPROFILE%\.cursor\mcp.json`（Windows）：

```json
{
  "mcpServers": {
    "scholar-assistant": {
      "command": "python",
      "args": ["-m", "src.agent.mcp_server"],
      "cwd": "/path/to/scholar-assistant/python",
      "env": {
        "PYTHONPATH": "python/src",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "qwen3:8b"
      }
    }
  }
}
```

Windows 用户同样需要设置 `"HTTP_PROXY": ""` 和 `"HTTPS_PROXY": ""`。

## Continue

编辑 `~/.continue/config.json`（macOS/Linux）或 `%USERPROFILE%\.continue\config.json`（Windows）：

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "name": "scholar-assistant",
        "transport": {
          "type": "stdio",
          "command": "python",
          "args": ["-m", "src.agent.mcp_server"],
          "cwd": "/path/to/scholar-assistant/python",
          "env": {
            "PYTHONPATH": "python/src",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "qwen3:8b"
          }
        }
      }
    ]
  }
}
```

## 可用工具 / Available Tools (12)

| 工具 | 说明 |
|------|------|
| `translate_text` | 翻译学术文本（英→中） |
| `parse_document` | 解析 PDF/Word/PPT 等 16 种格式 |
| `search_documents` | RAG 语义检索已入库文档 |
| `crawl_arxiv` | 搜索 arXiv 学术论文 |
| `format_bibliography` | BibTeX → IEEE/APA/GB/T 7714/MLA |
| `analyze_markdown_elements` | 分析 Markdown 特殊元素 |
| `parse_table_structure` | 解析 Markdown 表格 |
| `generate_table_markdown` | 从数据生成 Markdown 表格 |
| `format_latex_formula` | 格式化 LaTeX 公式 |
| `get_citation_context` | 获取引用上下文 |
| `analyze_image_with_vision` | Vision API 分析图片 |
| `analyze_chart_image` | Vision API 分析图表 |
