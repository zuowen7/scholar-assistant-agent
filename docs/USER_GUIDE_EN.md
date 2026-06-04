# Scholar Assistant — User Guide

> For version v0.3.6+ | [中文指南](./USER_GUIDE.md)

## Table of Contents

- [Installation & Startup](#installation--startup)
- [Translation Mode](#translation-mode)
- [Editor Mode](#editor-mode)
- [Voice Assistant](#voice-assistant)
- [AI Agent Chat](#ai-agent-chat)
- [Argument Companion](#argument-companion)
- [Mind Map](#mind-map)
- [Settings & Engine Configuration](#settings--engine-configuration)
- [Export](#export)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [FAQ](#faq)

---

## Installation & Startup

### Prerequisites

Install [Ollama](https://ollama.com) and pull a model (optional for local translation):

```bash
ollama pull qwen3:8b
```

> Ollama is optional — the default engine is cloud-based. Just fill in an API Key in Settings.

### Option 1: Desktop App (Recommended)

1. Download the installer from [GitHub Releases](https://github.com/zuowen7/scholar-assistant-agent/releases)
2. Install and launch — the app manages all backend services automatically
3. On startup, the app checks for new versions and shows a toast notification if an update is available

**Windows developers**: Use `start_dev.bat` to launch (automatically clears proxy environment variables that can cause httpx to hang)

### Option 2: Development Mode

```bash
# Terminal 1 — Start Python backend
cd python
pip install -r requirements.txt
python api.py

# Terminal 2 — Start frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. The frontend proxies `/api` requests to `localhost:18088`.

### Option 3: Docker

```bash
docker compose up
```

---

## Translation Mode

Switch to "Translate" in the top bar. Drag in a PDF and wait for completion.

### Translating a Paper

1. **Upload**: Click the upload area to select a PDF, or drag a file anywhere onto the window
2. **Processing**: The 5-step pipeline runs automatically with a live progress bar
   - Parse → Clean → Chunk → Translate → Format
3. **Results**: View the translation when complete

### Result Views

| View | Description |
|------|-------------|
| **Bilingual** | Source on left, translation on right; hover a sentence to highlight its counterpart |
| **Translation Only** | Just the translated text |
| **Markdown** | Rendered formatted Markdown page |

### Retry Failed Blocks

If a paragraph fails (shown in red), you don't need to re-translate the entire document:
- Click the failed block → select "Retry" → only that block is re-translated

### Export Translation

Use the dropdown menu in the top-right corner, 4 formats:

| Format | Content |
|--------|---------|
| Bilingual Markdown | Alternating Chinese/English, paragraph-aligned |
| Translation-only Markdown | Chinese translation only |
| Bilingual Word (.docx) | Side-by-side, print-friendly |
| Translation-only Word (.docx) | Chinese text only |

### Auto-Ingest into Library

After translation, the bilingual full text is automatically stored in the local vector database (ChromaDB). The Agent can later retrieve previously translated papers using the "Search Documents" tool.

---

## Editor Mode

Switch to "Editor" in the top bar. The core is a Monaco editor + left file tree + right panel.

### Create / Open a Project

The welcome page offers 4 entry points:

| Entry | Purpose |
|-------|---------|
| **New Project** | Start from a mind map, generate a paper draft step by step |
| **New from Template** | Choose IEEE / ACM / NeurIPS template, AI generates outline |
| **Open Folder** | Open an existing paper project (Agent workspace) |
| **New Document** | Create a blank Markdown file |

### File Management

- **File Tree** (left sidebar): Browse, create, and delete files and folders
- **Tab Bar** (top): Switch between files, drag to reorder, `Ctrl+W` to close

### Ghost Text (Auto-Completion)

After typing, **pause for 1.5 seconds** — AI generates a grayed-out continuation at the cursor:
- **Tab** — Accept suggestion
- **Esc** — Dismiss

### Preview

Switch the right panel to "Preview" for a live rendered view of your Markdown.

### Voice Input

The editor toolbar has a microphone button for voice dictation:

- Click 🎤 → start speaking; your speech is transcribed in real time at the cursor
- Click again → stop recording
- While speaking, press `Tab` to accept Ghost Text; subsequent voice input continues seamlessly

---

## Voice Assistant

The voice assistant lets you control Scholar Assistant hands-free — say the wake word or press a hotkey, speak a command, and the Agent executes it.

### Activation

| Method | How |
|--------|-----|
| **Wake Word** | Say "**小研**" (default), the voice UI appears |
| **Global Hotkey** | Press `Alt+Shift+V`, works even when the window is minimized |

> Wake word only works when the app window is in the foreground. Global hotkey works system-wide (desktop app only).

### Voice UI

Activation opens a Siri-style fullscreen overlay:

- **Pulsing orb** — breathing animation to indicate listening
- **Ripple rings** — 3 concentric expanding rings when the mic is active
- **Live transcript** — your speech appears word-by-word in the center
- **Silence auto-submit** — after a 2-second pause, the command is sent to the Agent
- **10-second timeout** — auto-cancels if no speech is detected

> Press `Escape` or click the backdrop to cancel.

### Usage Flow

1. Say "**小研**" or press `Alt+Shift+V` → voice UI opens
2. Speak your command, for example:
   - "Translate the current paragraph"
   - "Make the experiment section more detailed"
   - "Search the library for papers about transformers"
3. Pause for 2 seconds → auto-submits to the Agent
4. The Agent executes in the side panel; voice UI closes automatically

### Wake Word Support

Default wake word is "**小研**". Speech recognition supports homophone variants:

- 小研 / 小严 / 小言 / 小岩 / 小颜 and similar-sounding characters all work
- 5-second cooldown: after activation, the wake word is ignored for 5 seconds to prevent accidental re-triggering

### Voice Dictation

Mic buttons are available in the editor toolbar, Agent panel, and AI edit panel:

- Click → start voice input; speech is transcribed to text in real time
- Click again → stop recording
- No conflict with wake word: wake word detection auto-pauses during dictation
- Chrome's automatic re-recognition is handled by three layers of deduplication

### Voice Settings

Settings panel → "Voice" tab:

| Setting | Description | Default |
|---------|-------------|---------|
| Enable Voice Assistant | Turn wake word + hotkey on/off | On |
| Wake Word | Custom wake word (2–4 characters) | 小研 |
| Global Hotkey | Press a key combination to reassign | Alt+Shift+V |
| Language | Recognition language | zh-CN |
| Sensitivity | Wake word detection sensitivity | Medium |

---
## AI Agent Chat

Switch the right panel to "Agent" — this is the core of the app. It operates on your workspace files directly, like Claude Code.

### Basic Usage

1. First, open a project folder via "Open Folder"
2. Type instructions in the Agent chat, e.g.:
   - "Read introduction.md and summarize the key points"
   - "Rewrite paragraph 3's experiment description more rigorously"
   - "Search the library for papers about transformers"
3. The Agent reads and modifies your files; the editor auto-refreshes after each change

### Quick Actions (Bottom Preset Buttons)

| Button | Effect |
|--------|--------|
| Polish | Improve writing quality of selected text |
| Expand | Expand selected paragraph into detailed discussion |
| Review | Check for logical gaps and weak arguments |
| EN→ZH | Translate selected English to Chinese |
| ZH→EN | Translate selected Chinese to academic English |

> These presets use one-shot LLM streaming — no Agent ReAct loop, faster response.

**How to use**:
1. **Select text** in the editor
2. Click a preset button (or type a custom instruction)
3. AI returns a result — click "Insert" to replace the selection, or "Copy" to clipboard
4. Not satisfied? Click "Undo" to restore original text

### Advanced Features

- Type `/` to open the slash command menu
- Type `@` to reference other workspace files as context
- Click 📎 to attach files
- The Agent auto-parses PDFs — no manual conversion needed

### Workspace Boundary Approval

The Agent's file operations are restricted to the project folder. If it needs to access files outside the project, an approval popup appears:

| Option | Meaning |
|--------|---------|
| Allow Once | Approve this single operation |
| Allow for Session | Don't ask again this session |
| Deny | Reject the operation |

### Library (RAG)

The "Library" tab in the Agent panel:
- Translated papers are auto-ingested
- Manually upload files or delete existing entries
- The Agent uses `search_documents` on demand (not auto-injected every turn)

---

## Argument Companion

Switch the right panel to "Argument Companion" — a pre-submission self-check tool with two sub-tabs.

### Claim Ledger

**Purpose**: AI automatically checks whether every promise made in your abstract/intro is actually delivered in the body.

**How to use**:

1. Open your paper file
2. Click "**Analyze Claim Ledger**"
3. After AI scanning, each promise is shown as a row:

| Status | Meaning |
|--------|---------|
| ✅ Paid | Body has supporting experiments/arguments |
| ⚠️ Partial | Some support but insufficient |
| ❌ Unpaid | No corresponding experiments/arguments found |
| ⚠️ Mismatch | Delivered but doesn't match the promise |

4. **Click a promise** → editor jumps to the source text
5. Click "**→ Discharge**" → jump to the supporting section in the body
6. For unpaid promises, click "**How to fill**" → AI suggests specific experiment designs
7. **After editing**, the top bar shows "Draft changed, may be stale" — click "Re-analyze" to refresh

### Reviewer-2 Adversary

**Purpose**: Simulate a harsh reviewer to stress-test your paper. You can rebut each critique point by point (rebuttal practice).

**How to use**:

1. Switch to the "**Reviewer 2**" sub-tab
2. Select a **conference** (NeurIPS / ICML / ICLR / ACL / CVPR / KDD / CHI or Generic)
3. Select a **review style**:
   - Reviewer 2 (Harsh) — most critical
   - AC (Balanced) — objective and fair
   - Domain Expert — focuses on technical depth
   - Friendly Reviewer — constructive suggestions
4. Click "**Red-team this paper**"
5. AI outputs critique points one by one. Each can be expanded:
   - Click "**Rebuttal**" to open the input box
   - Write your rebuttal, click "**Send**"
   - The AI reviewer responds — it may be persuaded, or may push back
   - After a few rounds, the status changes to "Rebutted"
6. When done, click "**↓ Export Rebuttal**" to download a Markdown file with all critiques and your rebuttals

### 3-Angle Parallel Review

When enabled, AI reviews from three angles simultaneously with automatic deduplication:
- **Method** — experimental design, statistical methods
- **Experiment** — datasets, baselines, ablation studies
- **Writing** — clarity, logical coherence

> Enable via `features.parallel_review` in settings, or select parallel mode in the review panel.

### Import Real Review Comments

If you received real reviewer comments, you can import them:

1. Find "**Import Real Reviews**" at the bottom of the Reviewer 2 sub-tab
2. Paste the reviewer comments into the text box
3. Click "**Import**"
4. AI structures the raw comments into itemized, rebuttal-ready entries
5. The rebuttal flow is the same as for simulated reviews

---

## Mind Map

Enter from the editor welcome page "**New Project** → **Start from Mind Map**", or click the mind map icon in the editor toolbar.

### Basic Operations

| Action | How |
|--------|-----|
| Add child node | Select node → **Tab** |
| Add sibling node | Select node → **Enter** |
| Edit node text | Select node → **F2** |
| Delete node | Select node → **Delete** |
| Move node | Drag the node card |
| Delete edge | Hover edge (turns red) → click to delete |
| Zoom / Pan | Mouse wheel / drag canvas background |
| Auto layout | Click the "Tidy" button in toolbar |

### Node Body

Each node has a collapsible **body text area** in addition to its title:
- Click the **▸** button on the right side of a node to expand the editor (button is highlighted when body has content)
- When collapsed, a first-line preview is shown (≤40 characters)
- When exporting to a paper outline, titles become headings and bodies become paragraphs

### AI Assistance

- **AI Expand**: Select a node → click "AI Expand" → auto-generate subtopics
- **AI Analysis**: Check the entire map for logical gaps

### Editor Sync

Mind map and editor support bidirectional switching:
- **Editor → Mind Map**: Outline auto-parses into a node tree (headings + body)
- **Mind Map → Editor**: All headings and body content preserved, exported as Markdown

---

## Settings & Engine Configuration

Click the status indicator in the top-right corner (shows Ollama / Cloud) to expand the service status panel.

### Translation Engine

| Engine | Description |
|--------|-------------|
| **Ollama (Local)** | Runs offline, no network needed, best privacy. Requires Ollama installation and model pull |
| **Cloud API** | 21 providers, higher translation quality. Requires an API Key |

Supported cloud providers: OpenAI, Anthropic, DeepSeek, Moonshot, Zhipu (ChatGLM), Qwen (Tongyi), Gemini, SiliconFlow, OpenRouter, Groq, Together, Mistral, xAI, Fireworks, DeepInfra, Perplexity, Novita, Volcengine (Doubao), Baidu Qianfan, Azure OpenAI, Custom.

### Interface Language

The settings panel includes a language dropdown:
- 简体中文 (zh-CN)
- English (en-US)

Changes take effect immediately, no restart needed.

### Service Status

The status panel shows:
- 🟢 Backend: Whether the API service is online
- 🟢 Ollama: Whether the local model is ready (when using Ollama engine)

If offline, click "Restart Backend".

---

## Export

### LaTeX / PDF Export

Editor toolbar → select template → export:

| Template | Use Case |
|----------|----------|
| IEEE Conference | IEEE conference papers |
| IEEE Journal | IEEE journal articles |
| ACM | ACM conferences/journals |
| NeurIPS | NeurIPS conference |
| LNCS | Springer LNCS |
| Generic Article | General academic papers |

### Word Export

Editor toolbar → Export Word → download .docx file.

### Mind Map Export

Mind maps can be converted to paper outlines with one click, then opened in the editor for continued writing.

---

## Keyboard Shortcuts

### Editor

| Shortcut | Function |
|----------|----------|
| `Ctrl+S` | Save file |
| `Ctrl+W` | Close current tab |
| `Ctrl+K` | AI Edit (select text, then type a natural language instruction) |
| `Tab` | Accept Ghost Text suggestion |
| `Esc` | Dismiss Ghost Text |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |

### Mind Map

| Shortcut | Function |
|----------|----------|
| `Tab` | Add child node |
| `Enter` | Add sibling node |
| `F2` | Edit selected node |
| `Delete` | Delete selected node |
| `Arrow keys` | Navigate between nodes |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |

### AI Chat Panel

| Shortcut | Function |
|----------|----------|
| `Enter` | Send message |
| `Tab` | Accept input suggestion |

### Voice Assistant

| Shortcut | Function |
|----------|----------|
| `Alt+Shift+V` | Activate voice assistant (default, customizable) |
| `Escape` | Cancel voice input |

---

## FAQ

### Q: Backend shows offline after startup

**A**: The backend service takes a few seconds to start. If still offline after 30 seconds:
1. Check if port 18088 is occupied
2. Click "Restart Backend"
3. If using the Tauri desktop app, close and relaunch

### Q: Ollama shows offline

**A**:
1. Confirm Ollama is installed: run `ollama list` in a terminal
2. Confirm model is pulled: `ollama pull qwen3:8b`
3. Ollama defaults to port 11434 — make sure it hasn't been changed

### Q: Can I use it without Ollama?

**A**: Yes. Select "Cloud API" in settings and fill in an API Key (DeepSeek recommended — cheap and good). Ollama is entirely optional.

### Q: Windows startup hangs / httpx error

**A**: This is caused by Windows proxy environment variables making httpx hang on import. Use `start_dev.bat` to launch — it automatically clears `HTTP_PROXY` and related variables.

### Q: Translation quality is poor

**A**:
1. Switch to a cloud engine (e.g., DeepSeek / GPT-4) — significantly better than local Ollama
2. Lower `temperature` in settings (e.g., 0.2) for more stable output
3. Use "Retry Failed Block" to re-translate specific poor-quality paragraphs

### Q: Ghost Text doesn't appear

**A**: Ghost Text requires the `/api/complete` endpoint. Confirm:
1. Backend service is online
2. Wait 1.5 seconds after stopping typing
3. Cursor is at end of line (not in a selection)

### Q: Agent doesn't execute tools / always refuses

**A**:
1. Confirm you've opened a project folder via "Open Folder"
2. Confirm a translation engine is available (the Agent reuses the translation engine's LLM)
3. Try more explicit instructions, e.g., "Read the file introduction.md" instead of "Look at the intro"

### Q: Claim Ledger analysis produces no results

**A**:
1. Make sure the paper has an abstract or introduction section (AI extracts promises from these)
2. Make sure a translation engine is available (local Ollama or cloud API)
3. If LLM is unavailable, analysis fails silently — check the service status panel

### Q: LaTeX export fails

**A**:
1. Check if Tectonic is installed (one-click install available in Settings)
2. Confirm Markdown content is well-formatted (heading levels, formula syntax, etc.)
3. If Tectonic is unavailable, export as .tex and compile manually with another LaTeX compiler

### Q: Some text didn't change after switching language

**A**: Language switching takes effect immediately, but content in open dialogues won't be translated. Refresh the page to fully switch.

### Q: Voice assistant won't activate

**A**:
1. Make sure the voice assistant is enabled in Settings → Voice
2. Wake word only works when the app is in the foreground — bring Scholar Assistant to focus
3. Global hotkey (`Alt+Shift+V`) not working? Confirm you're using the desktop app (hotkey requires Tauri, not available in browser)
4. Re-record the hotkey in settings: click the hotkey input box, then press a new key combination

### Q: Voice dictation doesn't work / no response

**A**:
1. Confirm microphone permission is granted in your browser/WebView
2. Make sure the voice assistant is not currently active (dictation auto-pauses wake word)
3. Check if another app is using the microphone
4. Restart the app and try again

### Q: Voice recognition produces duplicate text

**A**: Chrome's continuous speech recognition occasionally re-recognizes earlier audio. Scholar Assistant has three layers of deduplication (prefix overlap detection + utterance tracking + internal duplication cleaning) that handle most cases automatically. If duplication still occurs, stop the mic and restart recording.
