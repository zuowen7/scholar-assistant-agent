# Scholar Assistant

隐私优先的学术 AI 写作辅助平台。从翻译切入，覆盖阅读、写作、排版全流程。拖入 PDF，自动完成解析、清洗、翻译；切换到 Editor 模式，用 AI 润色、扩写、生成大纲；导出 LaTeX 模板直接投稿。

- **版本**：Tauri 0.3.1 / npm 0.2.0
- **许可**：不开源，私有项目

## 核心功能

### 翻译管道
- **PDF 智能解析** — 16 种格式支持，自动检测单栏/双栏布局
- **文本清洗** — 17 阶段管线，修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区跳过** — 自动识别 REFERENCES/BIBLIOGRAPHY 区域，原样保留不翻译
- **双语对照输出** — Markdown blockquote 格式，原文/译文逐段对照
- **实时进度** — SSE 流式推送 5 步管道进度

### 翻译引擎
- **本地** — Ollama + Qwen3，全程离线，无需 API Key
- **云端** — OpenAI / Anthropic / DeepSeek / Moonshot / Grok / Gemini / together / custom
- **Glossary 自动提取** — 翻译结果中提取 `中文(English)` 术语对，注入后续块翻译
- **滑动上下文窗口** — 每块翻译携带前 N 块的摘要和术语表

### 学术写作 AI
- **Agent 对话** — 基于 ReAct 循环的智能助手，可调用工具、检索知识库
- **RAG 知识库** — ChromaDB + 本地嵌入，文档自动分块索引；翻译后自动入库；支持手动上传/删除文件
- **Skill 系统** — 从任务轨迹中沉淀可复用经验，支持多信号匹配
- **AI 润色 / 扩写 / 连贯性改写 / 合规检查** — 通过 AI Panel 对选中文本操作
- **Inline Ghost Text** — Monaco Editor 打字后 1.5s 自动请求补全建议，Tab 接受 ghost 文本

### 编辑器
- **Monaco Editor** — 全功能代码编辑器，支持 Markdown 语法高亮
- **AI Panel** — 聊天风格 UI，支持消息历史；润色/扩写结果用 diff 视图对比原文，一键应用/撤销
- **文件树** — 多文件管理，左侧导航
- **模板导出** — Pandoc 编译，支持 IEEE/ACM/NeurIPS/LNCS/Elsevier/通用 LaTeX 模板

### 部署
- **桌面端** — Tauri 2 打包，自动管理 Python 后端和 Ollama 进程
- **Docker** — 多阶段构建，一键容器化运行
- **Python CLI** — `python main.py paper.pdf -o paper.md`

## 项目结构

```
├── src-tauri/                    # Rust + Tauri 桌面端
│   ├── src/main.rs               #   进程管理 (Python API + Ollama)
│   └── capabilities/             #   Tauri v2 权限配置
├── src/                          # Vue 3 前端
│   ├── App.vue                   #   主界面 (Translate Mode + Editor Mode)
│   ├── composables/
│   │   ├── useTranslate.ts       #   SSE 翻译管线状态管理
│   │   ├── useAgentChat.ts       #   Agent SSE 对话状态管理
│   │   └── useEditor.ts          #   Monaco Editor + AI Panel
│   └── components/               #   AI Panel, FileTree, ComplianceModal 等
├── python/                       # Python 后端 (~10337 行)
│   ├── api_factory.py            #   FastAPI app 工厂
│   ├── main.py                   #   CLI 入口
│   ├── config/default.yaml       #   默认配置
│   ├── src/
│   │   ├── parser/               #   16 格式解析器
│   │   ├── cleaner/             #   17 阶段清洗管线
│   │   ├── chunker/              #   3 策略切块 (sentence/paragraph/fixed)
│   │   ├── translator/           #   Ollama + Cloud 双客户端
│   │   ├── formatter/            #   3 输出模式 + Pandoc 导出
│   │   └── agent/                #   ReAct Agent + RAG + Tools + Skills
│   ├── prompts/                  #   学术写作 Prompt 体系
│   ├── data/paper_assets/       #   论文模板 + 组件库
│   └── tests/                    #   170 个单元测试
├── Dockerfile
├── docker-compose.yml
└── package.json
```

## 下载安装

### 桌面端安装包（Windows / macOS / Linux）

GitHub Releases 页面：https://github.com/zuowen7/scholar-cursor/releases

| 平台 | 下载文件 |
|------|---------|
| Windows | `Scholar Assistant_{版本}_x64-setup.exe` |
| macOS (Apple Silicon) | `Scholar Assistant_{版本}_aarch64.dmg` |
| macOS (Intel) | `Scholar Assistant_{版本}_x64.dmg` |
| Linux | `Scholar Assistant_{版本}_amd64.deb` 或 `.AppImage` |

> **前提条件**：安装 [Ollama](https://ollama.com) 并拉取模型：
> ```bash
> ollama pull qwen3:8b
> ```

### Docker 镜像

```bash
# 拉取最新镜像
docker pull zuowen7/scholar-cursor:latest

# 启动 Ollama + 应用服务
docker compose up

# 翻译文档
docker compose run app /data/input/paper.pdf -o /data/output/paper.md
```

---

## 快速开始

### 前置条件

- Python 3.12+
- [Ollama](https://ollama.ai) + Qwen3 模型 (`ollama pull qwen3:8b`)
- Node.js 18+, Rust 1.80+ (桌面端开发)
- (可选) Docker + Docker Desktop

### 方式一：桌面端 (Tauri)

```bash
npm install

# 开发模式
npx tauri dev

# 生产构建
npx tauri build
```

应用会自动启动 Python API 服务，关闭窗口时自动清理所有子进程。

### 方式二：仅 Python 后端

```bash
cd python
pip install -r requirements.txt
ollama serve                                    # 启动 Ollama
python api.py --port 18088                      # 启动 API 服务
# 或使用 CLI
python main.py paper.pdf -o paper.md
```

### 方式三：Docker

```bash
docker compose --project-name scholar-assistant build

OLLAMA_HOST=0.0.0.0:11434 ollama serve

# Windows (Git Bash)
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd)/python/data/input:/data/input:ro" \
  -v "$(pwd)/python/data/output:/data/output" \
  --add-host=host.docker.internal:host-gateway \
  scholar-assistant-app:latest \
  /data/input/paper.pdf -o /data/output/paper.md
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/ollama/status` | Ollama 状态 |
| `POST` | `/api/translate` | 上传文档，返回 task_id |
| `GET` | `/api/translate/{id}/stream` | SSE 翻译进度流 |
| `GET` | `/api/download/{id}` | 下载翻译结果 |
| `GET/PUT` | `/api/config` | 读写配置 |
| `POST` | `/api/chat` | Agent SSE 对话（ReAct 循环） |
| `POST` | `/api/agent/task` | 执行特定 Agent 任务 |
| `POST` | `/api/edit` | AI 驱动的 SSE 流式编辑（ollama/cloud 双引擎） |
| `POST` | `/api/complete` | 非流式 inline 补全 |
| `GET` | `/api/rag/documents` | 列出 RAG 知识库文档 |
| `POST` | `/api/rag/upload` | 上传文件入库 RAG（不经翻译） |
| `DELETE` | `/api/rag/documents/{doc_id}` | 删除 RAG 知识库文档 |
| `POST` | `/api/rag/ingest` | 向 RAG 知识库存入文本 |

翻译 SSE 事件顺序：`progress` → `parsed` → `cleaned` → `chunked` → `chunk_done`(×N) → `complete`

## 配置

编辑 `python/config/default.yaml`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `parser.engine` | pdfplumber | PDF 解析引擎 |
| `chunker.max_tokens` | 2048 | 每块最大 token 数 |
| `chunker.strategy` | sentence | 切块策略 |
| `translator.engine` | cloud | 翻译引擎: ollama / cloud |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.temperature` | 0.3 | 生成温度 |
| `translator.timeout` | 300 | 翻译超时 (秒) |
| `formatter.output_format` | bilingual | 输出格式 |
| `agent.enabled` | true | 是否启用 Agent |
| `rag.enabled` | true | 是否启用 RAG（仅本地） |

## 测试

```bash
cd python && pytest tests/ -v
```

当前：463 个测试（24 unit + 3 integration），覆盖 Parser / Cleaner / Chunker / Translator / Formatter / Agent 全模块 / RAG / MCP / Zotero / WordExporter / Benchmark

## 技术栈

| 层 | 技术 |
|----|------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor |
| 桌面端 | Tauri 2 (Rust) |
| 后端 | Python 3.12, FastAPI, SSE |
| 翻译（本地） | Ollama + Qwen3:8b |
| 翻译（云端） | OpenAI / Anthropic / DeepSeek / Moonshot 等 |
| PDF | PyMuPDF, pdfplumber |
| 向量数据库 | ChromaDB + all-MiniLM-L6-v2（仅本地） |
| LaTeX 导出 | Pandoc + 6 套官方模板 |
| 容器化 | Docker 多阶段构建 |
