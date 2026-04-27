# Scholar Assistant — 综合项目报告

## 1. 项目概述

**Scholar Assistant**（又名 Scholar Assistant）是一款面向科研人员的英文学术文献智能翻译与写作辅助工具。用户拖入 PDF 文档即可自动完成解析、清洗、翻译全流程，输出高质量双语对照结果，支持全文离线本地运行。项目在此基础上升级为学术写作辅助平台，新增 Agent 对话、RAG 检索、LaTeX 模板导出与 AI 驱动的论文润色/扩写/连贯性改写/合规检查等功能。

- **版本**：Tauri 0.3.1 / npm 0.2.0
- **核心定位**：隐私优先（全程离线）+ 学术级翻译质量 + 一站式写作辅助

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                     Deployment Layer                          │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐              │
│  │ Tauri 2  │  │    Docker    │  │   CLI    │              │
│  │ Desktop  │  │  Container   │  │  python  │              │
│  └────┬─────┘  └──────┬───────┘  └──┬───────┘              │
├───────┼───────────────┼──────────────┼──────────────────────┤
│       │               │              │                      │
│  ┌────▼───────────────▼──────────────▼──────────────┐      │
│  │               Vue 3 Frontend                      │      │
│  │  ┌─────────────────┐  ┌──────────────────────┐   │      │
│  │  │  Translate Mode  │  │     Editor Mode      │   │      │
│  │  │  (SSE 5-step     │  │  (Monaco + AI Panel  │   │      │
│  │  │   pipeline)      │  │   + File Tree)       │   │      │
│  │  └─────────────────┘  └──────────────────────┘   │      │
│  └────────────────────┬──────────────────────────────┘      │
├───────────────────────┼──────────────────────────────────────┤
│                       │                                      │
│  ┌────────────────────▼──────────────────────────────┐      │
│  │          Python Backend (FastAPI :18088)            │      │
│  │                                                     │      │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │      │
│  │  │ Parser  │ │ Cleaner │ │ Chunker │ │Translator│  │      │
│  │  │(16 fmt) │ │(17-stage)│ │(3 strat)│ │(2 client)│  │      │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │      │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────────┐         │      │
│  │  │Formatter│ │  Agent  │ │  RAG (Chroma)│         │      │
│  │  │(3 modes)│ │(ReAct)  │ │ (local-only) │         │      │
│  │  └─────────┘ └─────────┘ └──────────────┘         │      │
│  └────────────────────────────────────────────────────┘      │
│                       │                                      │
├───────────────────────┼──────────────────────────────────────┤
│                       ▼                                      │
│  ┌─────────────────────────────────────────────┐             │
│  │  Ollama (localhost:11434)                    │             │
│  │  Models: qwen3:8b (default), deepseek-r1,   │             │
│  │          llama3, qwen3:32b                   │             │
│  └─────────────────────────────────────────────┘             │
│                                                              │
│  ┌─────────────────────────────────────────────┐             │
│  │  Cloud API (optional)                       │             │
│  │  OpenAI / Anthropic / DeepSeek / Moonshot   │             │
│  │  Grok / Gemini / together / custom          │             │
│  └─────────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

### 三种部署模式

| 模式 | 入口 | 进程管理 | 适用场景 |
|------|------|----------|----------|
| **Tauri 桌面端** | `npx tauri dev` / `npx tauri build` | Rust 自动启动 Python API + Ollama，窗口关闭自动清理 | 日常使用，零手动操作 |
| **Docker 容器** | `docker compose --build` + `docker run` | 容器化运行，需外部 Ollama | 服务器部署，批量翻译 |
| **Python CLI** | `python main.py paper.pdf -o paper.md` | 纯命令行 | 调试，CI，快速试用 |

---

## 3. 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| **前端框架** | Vue 3 (Composition API + `<script setup>`) | ^3.5.0 |
| **代码编辑器** | Monaco Editor | ^0.55.1 |
| **Markdown 渲染** | marked + DOMPurify + KaTeX + highlight.js | - |
| **构建工具** | Vite | ^6.0.0 |
| **类型检查** | TypeScript + vue-tsc | ^5.6.0 / ^2.2.0 |
| **桌面壳** | Tauri 2 (Rust) | ^2.10.1 |
| **Tauri 插件** | dialog, fs, shell | ^2 |
| **后端** | Python 3.12+, FastAPI + SSE + uvicorn | - |
| **翻译引擎（本地）** | Ollama + Qwen3:8b 等 | - |
| **翻译引擎（云端）** | OpenAI / Anthropic / DeepSeek / Moonshot 等 | - |
| **PDF 解析** | pdfplumber（主）+ PyMuPDF（副） | - |
| **向量数据库** | ChromaDB + all-MiniLM-L6-v2（仅本地使用） | - |
| **LaTeX 导出** | Pandoc + 6 套官方模板（IEEE/ACM/NeurIPS/LNCS/Elsevier/通用） | - |
| **容器化** | Docker 多阶段构建 | - |

---

## 4. 核心翻译管道（5 阶段）

```
PDF ──► Parser ──► Cleaner ──► Chunker ──► Translator ──► Formatter ──► Output
         │           │            │             │               │
         ▼           ▼            ▼             ▼               ▼
    16 格式解析   17 级清洗    3 种切块     2 客户端        3 种输出
    (pdf/txt/md   (水印/CID    策略           + Glossary       (bilingual
     /docx/html    /连字符     sentence      提取 + 3 级      /parallel
     /epub/rtf     /页眉页脚   paragraph     上下文           /translated)
     /tex/csv      /参考文献   fixed
     /pptx/xlsx    跳过)
     /srt/json
     /xml)
```

### 4.1 Parser — 文档解析
- **文件**: `python/src/parser/dispatcher.py`
- 通过注册抽象 `Extractor` 类支持 16 种文件格式：pdf, txt, md, docx, html, epub, rtf, tex, csv, pptx, xlsx, srt, json, xml 等
- PDF 使用 pdfplumber 引擎，自动检测单栏/双栏布局

### 4.2 Cleaner — 文本清洗（17 阶段管线）
- **文件**: `python/src/cleaner/pipeline.py`
- 按顺序执行：水印移除 → CID 伪影修复 → 断行连接 → 连字符断词处理 → 杂散字符清理 → 多余空白标准化 → 行内多余空白清理 → 段落间距标准化 → 基于缩进的段落合并 → 列表条目清理 → 孤行清理 → 短行合并 → 大写字母短行合并 → 页眉页脚检测移除 → 章节标题修复 → 临时段落合并 → References 识别跳过

### 4.3 Chunker — 文本切块
- **文件**: `python/src/chunker/strategies.py`
- 三种策略：**sentence**（按句号边界，默认 max_tokens=2048）、**paragraph**（按段落）、**fixed**（固定长度）
- `TranslatingChunker` 支持动态调整：当某段超过阈值时拆分，过短时合并

### 4.4 Translator — 翻译引擎（两客户端并行）

#### 本地客户端 (`ollama_client.py`)
- 基于 Ollama API，默认模型 qwen3:8b
- 自动 Glossary 提取：扫描全文提取领域术语 → 构建中英对照术语表 → 注入 prompt
- 三级上下文：摘要（全文概要）+ Glossary + 滑动窗口（前 N 块）
- 翻译自我校验：翻译后调用 LLM 验证是否保留原文关键信息
- 核心 Prompt 设计：角色定义（学术翻译专家）+ 输出约束（禁止添加/遗漏/解释/格式）+ 术语表 + 上下文

#### 云端客户端 (`cloud_client.py`)
- 统一接口，支持 8 个 provider presets
- DeepSeek（默认）、OpenAI、Anthropic、Moonshot、Grok、Gemini、together、custom
- 通过配置文件 `config/default.yaml` 的 `translator.engine` 切换

### 4.5 Formatter — 输出格式化
- **文件**: `python/src/formatter/formatter.py`
- 三种输出模式：**bilingual**（逐段双语对照）、**parallel**（原文/译文左右并列表格）、**translated-only**（仅译文）
- 支持 Pandoc LaTeX 模板导出（IEEE, ACM, NeurIPS, LNCS, Elsevier, Generic）
- Markdown 输出（默认）+ PDF 导出

---

## 5. Agent 子系统

- **文件**: `python/src/agent/agent.py` (~1700 行)
- 基于 **Plan-and-Execute + ReAct** 混合架构的智能对话代理
- **三引擎流式输出**：Ollama（NDJSON）/ OpenAI 兼容（SSE）/ Anthropic（SSE），逐 token 推送到前端
- **双调用策略**：
  1. Ollama / Cloud 原生工具调用（`tool_call` 模式）— 优先级高
  2. 文本格式 ReAct（`Action: ...\nAction Input: ...`）— 降级方案
- **10 个内置工具**（`python/src/agent/tools.py`）：
  - **文档类**：`parse_document`（16 格式解析）、`crawl_arxiv`（arXiv 论文抓取）
  - **文本处理类**：`polish_text`（学术润色）、`summarize_text`（摘要生成）、`generate_outline`（大纲生成）、`expand_section`（受控扩写）
  - **文件类**：`save_file`、`read_file`（沙箱隔离，防路径穿越）
  - 工具注册通过 `@tool` 装饰器，自动生成 JSON schema
  - **LRU 工具结果缓存**：`OrderedDict` + MD5 哈希 key，64 条目上限，避免重复调用
  - **文本处理工具内嵌 LLM 调用**：通过 `_call_llm_sync()` 复用翻译引擎进行文本处理
- **Plan-and-Execute 模式**：ReAct 循环前先用轻量 LLM 调用生成执行计划，复杂任务自动拆解为多步骤
- **并行工具执行**：独立工具调用通过 `asyncio.gather()` 并行执行，减少等待时间
- **RAG 自动注入**（`python/src/agent/rag.py`）：
  - ChromaDB + all-MiniLM-L6-v2 嵌入
  - 每次 LLM 调用前自动检索 top-3 相关文档片段，注入为 system message
  - 复用 Chunker 模块对文档分块索引
- **Token 用量追踪**：从 Ollama / OpenAI / Anthropic 响应元数据中提取并累积 token 统计
- Agent 状态管理：memory（消息历史）、trajectory（执行轨迹）、VRAM 复用（不释放嵌入模型，降低加载开销）
- **Skill 系统**（`python/src/agent/skill_system.py`）：
  - 多信号匹配：Jaccard 相似度 + trigger 短语精确匹配 + description/name 关键词重合
  - 最低匹配阈值 1.0，避免误匹配
  - 催促机制：连续 10 轮对话未创建 Skill 时提醒 Agent 整理经验
  - 从任务轨迹中自动沉淀可复用经验（`generate_from_trajectory`）

---

## 6. 学术写作辅助功能（Prompts 系统）

```
python/prompts/
├── system/
│   └── academic_writer_system.md   # 全局系统 Prompt（角色 + 核心原则）
├── tasks_polish/
│   └── academic_polish.md          # 一键学术润色
├── tasks_expand/
│   └── grounded_expand.md          # 受控扩写（不虚构）
├── tasks_coherence/
│   └── coherence_rewrite.md        # 上下文感知连贯性改写
├── tasks_compliance/
│   └── compliance_check.md         # 论文合规检查（JSON 结构化输出）
└── schemas/
    └── structured_output.md        # 结构化输出约束（下游解析）
```

每个 Prompt 文件严格遵循：功能名称 → System Prompt → User Prompt 模板 → Few-Shot 示例 的四段式结构。AGENTS.md 将其注册为文件映射，由 `prompts/loader.py` 动态加载。

### 前端 Editor 模式中这些功能的集成
- `src/composables/useAgentChat.ts` — SSE Agent 对话状态管理
- AI Panel 提供：润色 / 扩写 / 连贯性改写 / 合规检查 四个按钮
- 选中文本后调用 Agent SSE API，流式返回修改结果
- Monaco Editor 集成支持差异高亮

---

## 7. 论文资产与模板 (Paper Assets)

```
python/data/paper_assets/
├── templates/
│   ├── ieee_journal/          # IEEE 期刊官方模板（源文件 + PDF + 资产）
│   ├── ieee_conference/       # IEEE 会议官方模板
│   ├── acm/                   # ACM 官方模板
│   ├── neurips/               # NeurIPS 官方模板
│   ├── lncs/                  # LNCS 官方模板
│   └── generic_article/       # 通用文章模板（已编译通过）
├── materials/
│   ├── text/                  # 论文各章节示例文本（title/abstract/intro/method/experiment/conclusion）
│   └── markdown/              # 对应 Markdown 版本的素材
├── components/
│   ├── equations/             # 公式组件
│   ├── figures/               # 图组件
│   ├── tables/                # 表组件
│   ├── citations/             # 引用格式组件
│   └── appendix/              # 附录组件
└── docs/
    ├── template_matrix.md     # 模板覆盖矩阵
    ├── compile_notes.md       # 编译记录
    ├── collection_checklist.md # 收集检查清单
    └── asset_inventory.md     # 资产清单
```

---

## 8. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/ollama/status` | Ollama 运行状态和模型列表 |
| `POST` | `/api/translate` | 上传文档，返回 task_id |
| `GET` | `/api/translate/{id}/stream` | SSE 翻译进度流（5 阶段事件） |
| `GET` | `/api/download/{id}` | 下载翻译结果 |
| `GET` | `/api/config` | 读取配置 |
| `PUT` | `/api/config` | 写入配置 |
| `POST` | `/api/chat` | Agent SSE 对话（ReAct 循环） |
| `POST` | `/api/agent/task` | 执行特定 Agent 任务 |

SSE 事件序列：`progress` → `parsed` → `cleaned` → `chunked` → `chunk_done` (×N) → `complete`

---

## 9. 主要配置项

**文件**: `python/config/default.yaml`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `parser.engine` | `pdfplumber` | PDF 解析引擎 |
| `chunker.max_tokens` | `2048` | 每块最大 token 数 |
| `chunker.strategy` | `sentence` | 切块策略 |
| `translator.engine` | `cloud` | 翻译引擎：`ollama` / `cloud` |
| `translator.model` | `qwen3:8b` | Ollama 模型名 |
| `translator.temperature` | `0.3` | 生成温度 |
| `translator.timeout` | `300` | 翻译超时（秒） |
| `formatter.output_format` | `bilingual` | 输出格式 |
| `agent.enabled` | `true` | 是否启用 Agent |
| `rag.enabled` | `true` | 是否启用 RAG（仅本地） |

---

## 10. 前端组件架构

### 主要 SFC 文件

| 文件 | 职责 |
|------|------|
| `src/App.vue` | 主组件（~1500 行）：Translate Mode + Editor Mode 双模式切换 |
| `src/composables/useTranslate.ts` | SSE 翻译管线状态机（idle → uploading → parsing → cleaning → chunking → translating → complete） |
| `src/composables/useAgentChat.ts` | SSE Agent 对话状态管理（流式 token 渲染 + 工具调用展示） |
| `src/composables/useEditor.ts` | Monaco Editor 集成（文件树 + 多标签 + AI 面板 + 差异高亮 + 模板导出） |
| `src/types/index.ts` | TypeScript 类型定义 |

### 关键流程

**Translate Mode 用户流程**：
1. 拖放 PDF（或点击选择）
2. 后端解析 → SSE 推送 `parsed` 事件
3. 清洗 → `cleaned`
4. 切块 → `chunked`
5. 逐块翻译 → `chunk_done` (×N) + 实时文本流
6. 完成 → `complete`，展示双语对照视图

**Editor Mode 用户流程**：
1. 加载 Markdown 文件（通过 Tauri dialog 或文件树）
2. Monaco Editor 编辑
3. AI Panel：选中文本 → 润色 / 扩写 / 连贯性改写 / 合规检查
4. Agent 对话：自由提问，ReAct 循环响应
5. 模板导出：选择 LaTeX 模板 → Pandoc 编译

---

## 11. 测试

```bash
cd python && pytest tests/ -v
```

- 49 个单元测试（位于 `python/tests/`）
- 覆盖 Parser / Cleaner / Chunker / Translator / Formatter 各模块

---

## 12. 项目结构完整一览

```
translator/
├── src-tauri/                      # Tauri 2 Rust 桌面壳
│   ├── src/main.rs                 #   进程管理 (Python API + Ollama 生命周期)
│   ├── Cargo.toml
│   └── capabilities/               #   Tauri v2 权限
├── src/                            # Vue 3 前端
│   ├── App.vue                     #   主界面
│   ├── composables/
│   │   ├── useTranslate.ts         #   SSE 翻译状态机
│   │   ├── useAgentChat.ts         #   Agent SSE 对话
│   │   └── useEditor.ts            #   Monaco Editor + AI Panel
│   └── types/
│       └── index.ts                #   TS 类型
├── python/                         # Python 后端
│   ├── api.py                      #   FastAPI 入口 (SSE)
│   ├── api_cloud.py                #   纯云端 API 入口
│   ├── api_factory.py              #   FastAPI app 工厂 (~900 行)
│   ├── main.py                     #   CLI 入口
│   ├── config/default.yaml         #   默认配置
│   ├── prompts/                    #   学术写作 Prompt 体系
│   ├── src/
│   │   ├── parser/                 #   16 格式解析器
│   │   ├── cleaner/                #   17 级清洗管线
│   │   ├── chunker/                #   3 策略切块
│   │   ├── translator/             #   Ollama + Cloud 双客户端
│   │   ├── formatter/              #   3 输出模式 + Pandoc 导出
│   │   └── agent/                  #   ReAct Agent + RAG + Tools
│   ├── data/paper_assets/          #   论文模板 + 组件库
│   ├── tests/                      #   49 个测试
│   └── requirements.txt
├── Dockerfile                      # Docker 多阶段构建
├── docker-compose.yml
├── package.json                    # npm 0.2.0
├── vite.config.ts
└── tsconfig.json
```

---

## 13. 开发路线图

| 阶段 | 状态 | 内容 |
|------|------|------|
| **P0 — 核心翻译管道** | ✅ 完成 | Parser / Cleaner / Chunker / Translator / Formatter |
| **P0 — Tauri 桌面集成** | ✅ 完成 | 子进程管理，自动启动/关闭 |
| **P0 — Docker 部署** | ✅ 完成 | 多阶段构建，容器化运行 |
| **P1 — SSE 流式翻译** | ✅ 完成 | 5 阶段进度推送 |
| **P1 — 双翻译引擎** | ✅ 完成 | Ollama 本地 + 多 provider 云端 |
| **P1 — 49 个单元测试** | ✅ 完成 | 覆盖核心模块 |
| **P2 — Agent 子系统** | ✅ 完成 | ReAct 循环 + 工具调用 + SSE |
| **P2 — RAG 检索** | ✅ 完成 | ChromaDB + 本地嵌入 |
| **P2 — Editor 模式** | ✅ 完成 | Monaco + AI Panel + 文件树 |
| **P3 — 学术写作 AI 功能** | ✅ 完成 | 润色 / 扩写 / 连贯性改写 / 合规检查 |
| **P3 — LaTeX 模板导出** | ✅ 完成 | 6 套官方模板 + Pandoc 编译 |
| **P3 — 论文资产库** | ✅ 完成 | templates / materials / components |
| **P4 — Cloud API 独立入口** | ✅ 完成 | `api_cloud.py` 纯云端部署 |
| **P4 — PyInstaller 打包** | ⚠️ 初步 | `.spec` 文件存在，待完善 |

---

## 14. 关键设计决策

1. **三合一部署**：同一套代码库支持 Tauri 桌面应用、Docker 容器、Python CLI 三种运行方式，最大化灵活度
2. **引擎可切换**：翻译引擎通过配置项 `translator.engine` 在 ollama/cloud 间切换，无需修改代码
3. **本地优先 + 云端扩展**：默认使用 DeepSeek 云端，但全套离线方案（Ollama + ChromaDB）随时可用
4. **Agent 双调用策略**：优先使用 Ollama 原生 tool calling；如果模型不支持，自动降级为文本格式 ReAct
5. **VRAM 复用**：Agent 初始化时加载的嵌入模型在 session 结束后保留在显存中，避免反复加卸载
6. **安全**：Tauri 2 能力白名单（capabilities），用户需授权文件系统/对话框操作

---

## 15. 性能基准（预期值，基于代码分析）

| 阶段 | 10 页 PDF（~5000 词） | 30 页 PDF（~15000 词） | 瓶颈 |
|------|----------------------|------------------------|------|
| Parse (pdfplumber) | 1-3s | 3-8s | I/O（磁盘读取） |
| Clean (17 阶段正则) | 0.5-1s | 1-3s | CPU（纯计算） |
| Chunk (sentence 策略) | 0.1s | 0.3s | CPU |
| **Translate (串行, Ollama qwen3:8b)** | **3-10 min** | **10-30 min** | **GPU 推理（主要瓶颈）** |
| Translate (串行, DeepSeek cloud) | 1-3 min | 3-10 min | 网络延迟 + API 限速 |
| **Translate (并行 4x, Ollama)** | **~1-3 min** | **~3-8 min** | GPU 显存（并发受限） |
| Format (Markdown) | 0.1s | 0.3s | CPU |
| **总计（串行 Ollama）** | **~5-12 min** | **~15-40 min** | — |
| **总计（4x 并行 Ollama）** | **~2-4 min** | **~5-12 min** | — |

> 估算基于：qwen3:8b ~40 tok/s（RTX 3060）、Ollama 模型加载预热（首块延迟 ~5s）、Chunk 大小 ~512 tokens。Cloud API 取决于 provider 速率（DeepSeek 约 50-100 tok/s，有 rate limit）。

### 影响建议
- **并行翻译**是性价比最高的优化——改造 1-2 天，速度提升 3-4x
- **翻译记忆库**在重复段落多的论文（如实验对比部分）可再节省 10-30%
- **多模型路由**（标题用小模型）节省约 5-10% token 消耗

---

## 16. 架构决策记录 (ADRs)

### ADR-001：选用 SSE 而非 WebSocket 做翻译进度推送

**状态**：已实施  
**决策**：翻译进度使用 Server-Sent Events，而非 WebSocket  
**理由**：
- SSE 单向推送足够（后端→前端），不需要双向通信
- FastAPI 原生支持 SSE（sse-starlette），无需额外库
- 比 WebSocket 简单：无连接状态管理、自动重连、HTTP 兼容
- Agent 对话场景确实需要双向，但目前也走了 SSE（前端无法中断，是个已知缺陷）  
**后果**：
- ✅ 翻译流实现简洁，5 行代码即可注册一个 SSE 端点
- ❌ Agent 对话无法支持用户中途打断/澄清，后续应考虑改 WebSocket（ADR-007）

### ADR-002：双翻译引擎（Ollama + Cloud）用配置切换

**状态**：已实施  
**决策**：不采用统一抽象层包装多引擎，而是两个独立 Client 类，由 `translator.engine` 配置路由  
**理由**：
- Ollama 和 Cloud 的 API 差异大（参数、认证、速率限制、格式），统一抽象层会泄漏太多细节
- 共用 `Glossary`、后处理函数、`TranslationResult` 类型，复用已经够多
- 配置驱动切换，用户不需要改代码  
**后果**：
- ✅ 两客户端可独立演进而互不影响
- ❌ 切换引擎需重启服务（配置热加载只重读，不重建 Client）

### ADR-003：Chunker 可配置策略，默认 sentence

**状态**：已实施  
**决策**：不采用单一智能切分算法，而是提供三种可选策略  
**理由**：
- 不同文档类型适合不同策略：论文适合 sentence，代码文档适合 fixed，纯散文适合 paragraph
- 避免过度工程化：ML 驱动的智能切分（如 spaCy 句法分析）的收益与复杂度不成正比
- 用户可以通过配置实验找到最适合自己文档的策略  
**后果**：
- ✅ 灵活，适配多场景
- ✅ 策略之间可以组合（TranslatingChunker 已实现阈值自适应调整）
- ❌ 句法感知切分被推迟到 P1（见 STRATEGY.md 句法感知 Chunker）

### ADR-004：Glossary 自动提取而非手动输入

**状态**：已实施  
**决策**：术语表通过解析翻译结果中的 `中文(English)` 模式自动构建，不要求用户预设  
**理由**：
- 减少用户操作步骤，拖入 PDF 即可开始翻译
- 提取准确率足够高（模型按要求标注了术语格式）
- 后续通过「术语锚点系统」（P0 计划）补充用户确认环节  
**后果**：
- ✅ 零配置体验
- ❌ 模型不按格式输出时 Glossary 为空（需增加 fallback 提取策略）
- ❌ 无法区分「故意保留的英文」和「需要翻译的术语」

### ADR-005：Tauri 2 capability 权限白名单

**状态**：已实施  
**决策**：使用 Tauri 2 的 capability 系统声明权限，不采用 Tauri 1 的 allowlist  
**理由**：
- Tauri 2 的 capability 系统更细粒度（按命令、按窗口、按作用域）
- 安全：默认拒绝，只授予 dialog、fs、shell 三个插件的最小权限集合
- migrations/ 目录保留升级路径  
**后果**：
- ✅ 安全风险降低（恶意页面无法调用任意 Rust 命令）
- ✅ 符合 Tauri 2 推荐实践
- ❌ 调试时需手动检查 capability 配置（漏配会导致静默失败）

### ADR-006：Agent 双调用策略（tool_call → text ReAct fallback）

**状态**：已实施  
**决策**：Agent 优先尝试 Ollama 原生 tool calling，失败时降级为文本格式 ReAct  
**理由**：
- 不同模型对 tool calling 的支持不一致：qwen3 原生支持，llama3 部分支持
- 原生 tool calling 输出更稳定、解析更容易
- 文本 ReAct 是通用后备，确保任何模型都能运行 Agent  
**后果**：
- ✅ 兼容所有 Ollama 模型
- ✅ 模型升级后可自动享受 tool calling 的改进
- ❌ 两套解析逻辑增加维护成本

### ADR-007（未来）：Agent 通信切换为 WebSocket

**状态**：计划（P2）  
**决策理由**：SSE 单向推送无法支持用户「中途打断 Agent 思考」「澄清意图」「确认工具调用」。WebSocket 允许双向实时通信，Agent 流程可在任意轮次插入用户输入。  
**代价**：需要重写前端 `useAgentChat.ts` 和后端 `/api/chat` 端点；需要处理连接断开/重连。

---

## 17. 安全与隐私分析

### 数据流
```
PDF → [Tauri 窗口] → [FastAPI localhost] → [Ollama localhost]
     ↕ (Tauri IPC)      ↕ (127.0.0.1)        ↕ (127.0.0.1)
```
- **任何数据不离开本机**（使用云端引擎时，数据经 HTTPS 到对应 provider 服务器）
- Tauri 2 的 capability 系统限制前端只能调用声明的 Rust 命令，不能执行任意 shell
- API 服务仅绑定 `127.0.0.1`，不被局域网访问

### 风险点
1. **Cloud 引擎的数据外泄**：使用 DeepSeek/OpenAI 等云端时，文档内容会发送到第三方服务器。应在 UI 清晰标注「当前使用云端模式，数据会离开本机」
2. **日志可能包含原文**：`logging` 配置可能在 debug 级别输出原文片段。生产构建应设为 WARNING 级别
3. **Tauri dialog 插件可读任意文件**：用户授权后对话框可选中任意文件。属于用户有意行为，风险可接受

### 建议
1. 云端翻译前弹出隐私提醒：「文档将发送到 xxx 服务器，是否继续？」
2. 生产日志级别固定为 WARNING，不泄漏原文内容
3. Ollama 和 Python API 均无身份认证（仅限 localhost），应确保不在公网暴露端口

---

## 18. 技术债与风险分析

### 架构层面的问题

| 问题 | 位置 | 风险 | 建议 |
|------|------|------|------|
| `api_factory.py` ~900 行，承担路由+业务逻辑+进程管理 | `python/api_factory.py` | 高，单文件故障点 | 拆分为 routers/ + services/ + background/ |
| Cleaner 17 阶段全用正则，对罕见排版变体脆弱 | `cleaner/pipeline.py` | 中，特定 PDF 会漏处理 | 维护 PDF 样本库做回归测试 |
| Glossary 提取仅依赖 `中文(English)` 模式 | `ollama_client.py:363-386` | 高，模型不按格式输出则术语表为空 | 增加备选策略：对齐原文/译文的共现短语 |
| 翻译失败无差异化降级 | `ollama_client.py:156-185` | 中，坏块直接抛异常中断全文 | 跳过错块+标记，后续人工修补 |
| Tauri 进程管理硬编码 Windows 命令 | `src-tauri/src/main.rs` | 中，跨平台不兼容 | 抽象为 PlatformAdapter trait |
| Agent 与翻译管线独立无交集 | `agent/agent.py` vs `translator/` | 低，错失协同机会 | Agent 可调用翻译结果做润色，翻译可调用 Agent 做术语确认 |
| 配置文件运行时热加载不校验 | `api_factory.py:64` | 低，配置写坏无报错 | 加 pydantic schema 校验 |

### 测试覆盖的缺口

| 模块 | 行数 | 测试数 | 评估 |
|------|------|--------|------|
| Cleaner | 789 | ~10 | ⚠️ 不足，17 阶段应每阶段有独立测试用例 |
| Cloud Client | 535 | ~0 | ❌ 几乎无测试（需要 mock API） |
| Agent | ~1700 | ~0 | ❌ 无测试（ReAct 循环难测但可测工具函数） |
| Chunker | ~300 | ~5 | ⚠️ 边界情况（超长句、空块、LaTeX 公式块）缺覆盖 |

### 工程风险

1. **Ollama 服务可用性**：用户机器可能没装 Ollama、GPU 显存不足、模型未拉取 → 应有安装引导 + 自动检测 + 降级提示
2. **PyInstaller 打包**：`.spec` 文件存在但未验证可运行 → 打包后路径处理（`sys._MEIPASS`）需完整测试
3. **前端组件膨胀**：`App.vue` 1500 行，`useEditor.ts` 增长快 → 应拆分为更小的 composable
4. **依赖锁定**：`requirements.txt` 未锁版本号 → CI 可能突然失败

---

## 20. 当前问题清单（2026-04-24 审计）

### 🔴 阻断级：8 个测试失败

```
FAILED python/tests/unit/test_cleaner.py::TestDetectReferences::test_references_section
FAILED python/tests/unit/test_cleaner.py::TestDetectReferences::test_references_and_notes
FAILED python/tests/unit/test_cleaner.py::TestDetectReferences::test_bibliography
FAILED python/tests/unit/test_cleaner.py::TestDetectReferences::test_case_insensitive
FAILED python/tests/unit/test_cleaner.py::TestDetectReferences::test_supplementary_materials
FAILED python/tests/unit/test_cleaner.py::TestCleanTextFull::test_clean_result_with_references
FAILED python/tests/unit/test_phase2.py::TestSkillRegistry::test_match
FAILED python/tests/unit/test_formatter.py::TestFormatMarkdown::test_bilingual_format
```

**根因分析**：

| 失败项 | 根因 | 修复方案 |
|--------|------|----------|
| Cleaner 5 项引用区检测 | `constants.py` 中的 `REFERENCE_SECTION_PATTERNS` 缺少 `r"^" + p + r"\s*$"` 锚定，引用区标题模式与 `pipeline.py` 中生成的 `_REFERENCE_PATTERNS` 不一致（多行模式下 `^` 锚定导致 `REFERENCES\n1. Smith` 无法匹配） | 修改 `constants.py` 中 pattern 定义，去掉行首锚定，或改用非贪婪匹配 |
| Skill matching | 匹配阈值 1.0 过高，测试 query "帮我翻译这篇学术论文" 无法达到阈值（新算法基于 Jaccard + trigger phrase + description overlap，query 中"翻译"token 在 trigger "翻译论文, 学术翻译" 中是子串但贡献分数不足） | 降低阈值至 0.5-0.8，或在 trigger 匹配中增加子串匹配的权重 |
| Formatter 中文编码 | `format_output()` 返回字节串编码错误，中文字符在测试比较时损坏 | 检查 `renderer.py` 输出编码路径，确保返回 str 而非 bytes |

**影响**：影响翻译管线完整性验证，必须立即修复后才能推进后续开发。

---

### 🟡 高优先级：架构问题

| 问题 | 位置 | 行数 | 说明 |
|------|------|------|------|
| 单文件过大 | `api_factory.py` | 778 行 | 承担路由 + 业务逻辑 + 进程管理，拆分为 `routers/` + `services/` + `background/` 后可解除单点故障风险 |
| 前端组件膨胀 | `src/App.vue` | 2342 行 | 单文件包含 3 个主模式（Translate/Editor/对比阅读）、完整导航、翻译状态机、AI 面板；建议按模式拆为 `TranslatePage.vue`、`EditorPage.vue`，共享基础组件 |
| Agent 过长 | `python/src/agent/agent.py` | 1736 行 | 最大的 Python 文件，含有 5 个 100+ 行函数（`__init__` 114行、`run` 268行、`_build_messages` 89行、`_call_llm_cloud` 115行、`_stream_anthropic` 153行），建议按职责拆分为 `_llm_engine.py`、`_tool_executor.py`、`_plan_engine.py` |
| Cloud Client 无测试 | `cloud_client.py` | 535 行 | 零测试覆盖，所有调用路径未验证 |
| Agent 无测试 | `agent.py` | 1736 行 | 零测试覆盖，ReAct 循环难以测试但工具函数可独立测试 |

### 🟡 中优先级：代码质量

| 问题 | 位置 | 说明 |
|------|------|------|
| 前端 `any` 类型滥用 | `App.vue:600`, `ComplianceModal.vue:170,177,185`, `useEditor.ts:196,308` 等 | 9 处 `any` 使用，应定义明确类型或使用 `unknown` |
| 过长函数 | `agent.py:run` 268行、`_run_pipeline` 186行、`_stream_anthropic` 153行、`_is_frozen` 58行等 | 违反单一职责原则，影响可读性和测试性 |
| 依赖未锁版本 | `requirements.txt` 全部使用 `>=` 范围版本 | CI 可能因上游 breaking change 突然失败 |
| 文本处理工具内嵌 LLM | `tools.py:_call_llm_sync` 67行 | 文本处理（润色/摘要/扩写）直接调 LLM，绕过 Agent 的 ReAct 循环和 RAG 注入上下文，质量和 Agent 调用不一致 |
| 平台硬编码 | `src-tauri/src/main.rs` | Windows 命令硬编码，跨平台需抽象为 PlatformAdapter trait |

### 🟢 低优先级：工程改进

- `cleaner/pipeline.py` 17 阶段正则管线缺少 PDF 样本回归测试集
- Glossary 提取仅依赖 `中文(English)` 模式，模型不按格式输出则术语表为空
- 翻译失败无差异化降级（坏块直接抛异常中断全文）
- `src/__tests__/` 仅 1 个前端测试（dompurify），覆盖率极低
- PyInstaller `.spec` 文件存在但未验证可运行

### 测试覆盖总览

| 模块 | 源码行数 | 测试数 | 测试文件 | 覆盖评估 |
|------|----------|--------|----------|----------|
| Cleaner | 789 | ~10 | test_cleaner.py (20 tests) | ⚠️ 引用区检测缺回归 |
| Chunker | 347 | 9 | test_chunker.py | ✅ 基本覆盖 |
| Translator (Ollama) | 839 | 4 | test_translator.py | ⚠️ 不足 |
| Translator (Cloud) | 535 | 0 | — | ❌ 无覆盖 |
| Formatter | 469 | 5 | test_formatter.py | ⚠️ 中文编码缺测 |
| Agent | 1736 | 6 | test_agent_dual_engine.py | ❌ 工具函数未测 |
| ContextCompressor | 412 | 23 | test_context_compressor.py | ✅ 较好 |
| PromptBuilder | 261 | 25 | test_prompt_builder.py | ✅ 较好 |
| SkillSystem | 517 | 31 | test_phase2.py | ⚠️ 匹配算法缺边界测 |
| Parser | 825 | 11 | test_parser.py | ⚠️ 仅基础格式 |
| **总计** | **~10337** | **~170** | — | 约 **1.6%/行**，远低于目标 |

---

## 21. 下阶段目标（v0.4.0 — 2026-04-24 修订）

### P0 必须修复
- **8 个测试失败**（见第 20 章）：引用区检测 regression、Skill 匹配阈值、Formatter 编码问题
- **依赖版本锁定**：`requirements.txt` 所有 `>=` 改为 `==` 精确版本，生成 `requirements.lock`

### P0 新增功能（来自竞品分析）
- **MCP Server 支持**（1-2 天）：将翻译管道 + Agent 工具暴露为 MCP 协议，Claude/Cursor 等客户端可直接调用
- **双语 PDF 叠加**（3-5 天）：Parser 保留坐标 + Formatter `pdf_overlay` 模式（格式保留是用户第一痛点）

### P1 核心功能
- **翻译记忆库 TMCache**（1-2 天）：ChromaDB 存储原文→译文映射，命中率 > 0.9 复用
- **并行翻译**（1-2 天）：`asyncio.Semaphore` 控制并发度，翻译速度提升 3-4x
- **术语锚点系统**（2-3 天）：首次术语弹出确认 → 全局锁定译法（后端 API + 前端交互）

### P2 工程改善
- **api_factory.py 拆分为多文件**（0.5 天）：`routers/translate.py`、`routers/config.py`、`routers/agent.py`、`services/translation_pipeline.py`
- **App.vue 拆分**（2-3 天）：按模式拆为 `TranslatePage.vue` + `EditorPage.vue`，共享基础组件
- **前端测试补全**（2 天）：增加组件测试，覆盖 useTranslate、useEditor、useAgentChat
- **Cleaner PDF 回归测试集**（1-2 天）：收集 10 份不同排版 PDF，保证正则修改不破坏兼容性

### P3 打磨
- 多轮翻译精炼、文档级一致性质检、AI Panel diff 视图、Ollama 进程守护

### 版本目标
> **v0.4.0 = MCP 生态兼容 + 翻译速度 3x + 格式保留（PDF叠加）+ 术语可锚点 + 测试全部通过**

### 关键决策
1. **先修测试再推功能**：8 个失败测试阻断所有后续开发信心，必须作为第一优先级
2. **格式保留降级**：不做 DocLayout-YOLO 级排版（不与 PDFMathTranslate 竞争），只做 `pdf_overlay` 文字叠加
3. **依赖先锁再开发**：任何新依赖加入前必须锁版本

### 一、翻译记忆库 (Translation Memory)

**现状**：相同短语在不同文档中反复调用 LLM 翻译，耗时且结果可能不一致。  
**做法**：基于 ChromaDB（已集成）存储 `原文 embedding → 译文` 的映射。翻译前先查 TM 命中率 > 0.9 直接复用。  
**收益**：重复内容秒回，减少 10-30% API 调用，术语一致性自然增强。  
**实现**：1-2 天，翻译管线中加 `TMCache` 类，在 `translate()` 前查、后存。

### 二、文档级一致性质检

**现状**：每块独立翻译，块间可能术语/风格不一致（即使有 Glossary + 滑动窗口）。  
**做法**：全文翻译完成后，用一个轻量 prompt 扫描全文译文，标记「疑似不一致」的术语。  
**收益**：从「每段尽力」到「全文可控」。  
**实现**：`Translator.post_process()` 中加 `_consistency_check()`，返回警告列表，前端展示。

### 三、双语 PDF 叠加输出

**现状**：翻译结果只有 Markdown/文本文档，脱离原 PDF 布局。  
**做法**：记录 pdfplumber 提取时每段文字的坐标（page_no, bbox），翻译后用 PyMuPDF 在原 PDF 上绘制译文字块，输出「双语叠加 PDF」。  
**收益**：这是「格式保留」的最务实方案——不需要复杂排版引擎，保留原图/表/公式。  
**实现**：3-5 天，Parser 输出时保留坐标，Formatter 新增 `pdf_overlay` 模式。

### 四、多轮翻译精炼

**现状**：一次翻译定稿，首轮质量不足时没有改进手段。  
**做法**：两阶段翻译——第一轮「快速直译」（低 temp + 短 context），第二轮「学术润色」（用学术润色 prompt 改写译文，注入 Glossary）。  
**收益**：翻译质量显著提升，尤其对长难句效果明显。  
**实现**：1-2 天，Translator 支持 `refine=True` 参数。

### 五、Chunker 智能预分析

**现状**：Chunker 按标点机械切分，可能切开从句或公式。  
**做法**：切分前用 spaCy 做依存句法分析，识别从句边界、括号配对、公式块，保证每个 chunk 是完整的语法单元。  
**收益**：减少 LLM 处理「断句残片」的上下文负担，翻译流畅度提升。  
**实现**：2-3 天，`SyntaxAwareChunker` 类，只在句子策略下启用。

### 六、Ollama 多模型路由

**现状**：所有翻译用同一个模型。  
**做法**：短文本（标题/图注）用小模型（qwen3:4b）→ 快速响应；长段落用大模型（qwen3:32b）→ 高质量翻译。  
**收益**：综合速度提升 2-3 倍，用户几乎无感知质量下降。  
**实现**：1 天，Translator 加 `model_router(config)`。

### 七、用户纠错闭环

**现状**：翻译错了用户只能手动修改，下次还错。  
**做法**：用户在前端修改译文时，记录 `原文 → 用户修正` 对，存入 Glossary 或 Translation Memory，后续翻译自动生效。  
**收益**：越用越准，形成用户专属翻译模型。  
**实现**：3-4 天，前端修改事件 → API 记录修正对 → Glossary 并入。需要设计 UI（修改时弹出「保存为术语?」）。

### 八、工程建议

- **为 api_factory.py 「拆分为多文件」**：`routers/translate.py`, `routers/config.py`, `routers/agent.py`, `services/translation_pipeline.py`
- **为 Cleaner 加「PDF 回归测试集」**：收集 10 份不同排版 PDF，保证修改清洗逻辑不破坏已有兼容性
- **Agent 改用 WebSocket**：SSE 单向推送不够，Agent 需要用户「中断/澄清/确认」，WebSocket 支持双向
