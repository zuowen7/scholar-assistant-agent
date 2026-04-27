@echo off
REM Scholar Assistant MCP Server launcher (Windows)
REM Clears HTTP_PROXY to avoid httpx import hang on Windows

setlocal

REM Clear proxy env vars (Windows httpx bug)
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=

REM Set PYTHONPATH to project src
set PYTHONPATH=%~dp0..\src

REM Pass through LLM config
if not defined OLLAMA_BASE_URL set OLLAMA_BASE_URL=http://localhost:11434
if not defined OLLAMA_MODEL set OLLAMA_MODEL=qwen3:8b

echo Starting Scholar Assistant MCP Server...
python -m src.agent.mcp_server

endlocal
