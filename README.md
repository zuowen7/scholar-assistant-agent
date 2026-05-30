# Scholar Assistant

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.2-brightgreen)](https://github.com/zuowen7/scholar-cursor/releases)
[![Test](https://img.shields.io/badge/tests-1815%20passed-success)](https://github.com/zuowen7/scholar-cursor/actions)

**English** | [中文](./README_zh.md)

> Open-source **Claude Code for academic papers** — a privacy-first AI workstation that handles the full lifecycle of scholarly writing.

<!-- TODO: Add demo GIF here -->
<!--
![Scholar Assistant Demo](docs/demo.gif)
-->

## What It Does

Scholar Assistant packs five capabilities into one desktop app:

| | Capability | Highlights |
|---|---|---|
| **Read** | DeepL-quality PDF translation | 5-step SSE pipeline, sentence-level hover alignment, auto-glossary extraction |
| **Think** | Mind map + Argument map | Vue Flow canvas, AI-powered expansion, dagre auto-layout |
| **Write** | AI-powered editor | Monaco + Ghost Text, Agent directly reads/writes your project files |
| **Review** | Adversarial peer review | Reviewer-2 simulation, claim ledger (promises vs. deliveries), rebuttal chat |
| **Publish** | One-click export | IEEE / ACM / NeurIPS / LNCS LaTeX templates + Word, via Pandoc + Tectonic |

**The Agent is the backbone** — it works like Claude Code in a code repo, but for your paper workspace. Open a project folder, and the Agent can `read_file`, `grep_files`, `str_replace`, `write_file`, `run_command`, and `git_op` directly on your PDFs, drafts, bib files, and data. Workspace boundaries are enforced; out-of-scope access requires your approval.

## Download

Pre-built installers are available on the [Releases](https://github.com/zuowen7/scholar-cursor/releases) page.

| Platform | File |
|----------|------|
| Windows | `Scholar Assistant_x64-setup.exe` |
| macOS / Linux | Not yet available (see [Building from Source](#quick-start)) |

> **Prerequisites**: Install [Ollama](https://ollama.com) and pull a model: `ollama pull qwen3:8b`

## Quick Start

### Prerequisites

- [Ollama](https://ollama.com) + `ollama pull qwen3:8b` (local LLM)
- Python 3.12+, Node.js 18+
- Rust 1.80+ (for desktop builds)

### Run as Desktop App (Tauri)

```bash
npm install
npx tauri dev          # Starts Python API + Ollama automatically
```

### Run Python Backend Only

```bash
cd python
pip install -r requirements.txt
python api.py --port 18088
```

### Docker

```bash
docker compose up
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Vue 3 + TypeScript + Monaco Editor + Vue Flow  │
│              (Vite dev server)                   │
├─────────────────────────────────────────────────┤
│  Tauri 2 (Rust) — desktop shell, process mgmt   │
├─────────────────────────────────────────────────┤
│  Python FastAPI + SSE                            │
│  ┌──────────┬──────────┬──────────┬───────────┐ │
│  │ Translate │  Agent   │ Argument │ Mind Map  │ │
│  │ Pipeline  │  ReAct   │ Companion│  CRUD+AI  │ │
│  └──────────┴──────────┴──────────┴───────────┘ │
│  ┌──────────┬──────────┬───────────────────────┐ │
│  │  Parser   │ Cleaner  │ Chunker │ Formatter  │ │
│  │ (16 fmts) │(17 stages)│(3 strats)│(Pandoc)  │ │
│  └──────────┴──────────┴───────────────────────┘ │
├─────────────────────────────────────────────────┤
│  LLM Backends: Ollama (local) | 21 cloud APIs   │
└─────────────────────────────────────────────────┘
```

### Key Design Decisions

- **No LangChain / LlamaIndex** — hand-written ReAct engine for full control
- **SSE everywhere** — streaming UX for translation, agent chat, argument extraction
- **Local-first** — all data stays on your machine; cloud LLMs are optional
- **Workspace-scoped Agent** — file operations locked to project root, with approval for escapes

## 21 Cloud LLM Providers

OpenAI, Anthropic, DeepSeek, Moonshot, Zhipu (ChatGLM), Qwen (Tongyi), Gemini, SiliconFlow, OpenRouter, Groq, Together, Mistral, xAI, Fireworks, DeepInfra, Perplexity, Novita, Volcengine (Doubao), Baidu Qianfan, Azure OpenAI, and custom endpoints.

## Argument Companion (Reviewer-2)

A unique feature not found in any other academic tool:

- **Claim Ledger** — automatically extracts promises from abstract/intro and tracks whether the body delivers on each one (paid / partial / unpaid), anchored to exact character offsets with fuzzy relocation on edits
- **Reviewer-2 Simulation** — calibrated reviews for 7 conferences (NeurIPS, ICML, ICLR, ACL, CVPR, KDD, CHI), with rebuttal mini-chat where the reviewer can be persuaded
- **Parallel Perspectives** — method / experiment / writing angles reviewed concurrently via `asyncio.gather`
- **Real Review Import** — paste actual reviewer comments, get structured rebuttal items

## Testing

```
Python:  1815 tests passed / 11 skipped  (pytest)
Frontend: 347 tests passed / 27 files    (vitest)
```

```bash
cd python && pytest tests/ -v    # Backend tests
npx vitest                       # Frontend tests
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3, TypeScript, Vite, Monaco Editor, Vue Flow |
| Desktop | Tauri 2 (Rust) |
| Backend | Python 3.12, FastAPI, SSE |
| Local LLM | Ollama + Qwen3:8b |
| Cloud LLM | 21 providers via OpenAI-compatible API |
| PDF | PyMuPDF, pdfplumber |
| Vector DB | ChromaDB + all-MiniLM-L6-v2 |
| Export | Pandoc + 6 LaTeX templates (IEEE/ACM/NeurIPS/LNCS/Generic) + Tectonic |

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repo and create a feature branch
2. Make your changes — add tests for new functionality
3. Run `pytest tests/ -v` and `npx vitest` to verify
4. Submit a pull request

Good first issues are tagged `good-first-issue`. The project structure is documented in [CLAUDE.md](./CLAUDE.md).

## License

[MIT](./LICENSE)

---

Built with Tauri, FastAPI, and too many late nights.
