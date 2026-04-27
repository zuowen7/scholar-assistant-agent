#!/usr/bin/env bash
# Scholar Assistant MCP Server launcher (Linux/macOS)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Clear proxy env vars (Windows httpx bug; harmless on other OSes)
unset HTTP_PROXY
unset HTTPS_PROXY
unset NO_PROXY

# Set PYTHONPATH to project src
export PYTHONPATH="${SCRIPT_DIR}/../src"

# Default LLM config
: "${OLLAMA_BASE_URL:=http://localhost:11434}"
: "${OLLAMA_MODEL:=qwen3:8b}"
export OLLAMA_BASE_URL OLLAMA_MODEL

echo "Starting Scholar Assistant MCP Server..." >&2
python -m src.agent.mcp_server
