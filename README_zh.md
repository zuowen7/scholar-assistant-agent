# Scholar Assistant

[English](./README.md) | **中文**

面向论文写作与投稿的开源 AI 工作台。写、审、想、排，一站完成。

- **写** — 编辑器内 AI 伴写 / 润色 / 扩写，Agent 直接读写项目文件（论文版 Claude Code）
- **审** — Reviewer-2 对抗式审稿 + 论证账本，投稿前逼问逻辑漏洞
- **想** — 思维导图 + Toulmin 论证图，理清思路与论证结构
- **排** — 一键导出 IEEE / ACM / NeurIPS 等 LaTeX 模板与 Word

PDF 翻译与精读作为辅助入口，帮你快速把论文沉淀进工作流。语音助手支持唤醒词和全局热键。本地可离线运行，也可接入 21 家云端大模型。支持中/英双语界面切换。

v0.3.6 · 最新：Siri 式语音指令路由（20+ 条命令直达功能）、双语 UI。MIT 协议。

## 功能演示

| 审 — 对抗式审稿 | 审 — 论证账本 |
|--------------|-------------|
| ![Reviewer-2 演示](docs/demo/review.gif) | ![账本演示](docs/demo/precheck.gif) |

| 写 — AI 编辑器 + Agent |
|----------------------|
| ![Agent 演示](docs/demo/demo1.gif) |

| 想 — 思维导图 | 想 — 论证地图 |
|--------------|-------------|
| ![思维导图演示](docs/demo/mindmap.gif) | ![论证地图演示](docs/demo/argument.gif) |

| 语音 — 唤醒词 + 语音输入 |
|-----------------------|
| ![语音助手演示](docs/demo/voice.gif) |

| 更多功能 |
|---------|
| ![更多](docs/demo/demo2.gif) |

> 以上均为 v0.3.6 版本实机录屏。

## 下载安装

安装包在 [Releases](https://github.com/zuowen7/scholar-assistant/releases) 页面。

| 平台 | 文件 |
|------|------|
| Windows | `Scholar Assistant_x64-setup.exe` |
| macOS / Linux | 暂未提供（见[从源码构建](#快速开始)） |

> **注意**：[Ollama](https://ollama.com) 为可选项——仅本地离线翻译需要。云端翻译填 API Key 即可直接使用。

## 核心功能

### 学术写作 AI（Agent 为核心）

> **定位：论文版 Claude Code。** 把科研项目当 workspace，Agent 像 Claude Code 修代码一样直接读/写 PDF、草稿、bib、数据文件。

- **Agent 工作区文件操作** — 打开项目文件夹后，Agent 可直接调用 `read_file / grep_files / str_replace / write_file / git_op` 等工具读写项目内文件，Agent 完成后编辑器实时刷新；`read_file` 对 PDF/Word/EPUB 自动走解析器提取纯文本
- **文档问答一次性短路** — 打开文档问"写得怎么样/总结/有什么问题"时，内容已在手，直接单次 LLM 流式回答，不进多步工具循环；仅当明确要改文件/跑命令才走完整 ReAct Agent
- **workspace 边界 & 越界审批** — 所有文件操作严格锁定在项目根目录内；访问项目外路径触发审批弹窗（Allow once / Allow session / Deny），行为与 Claude Code 一致
- **Copilot 风格 inline diff** — Agent 修改文件后，编辑器内以红色波浪线标记删除、绿色预览部件 + [Accept][Reject] 按钮审阅改动
- **ReAct 智能推理** — 多步工具调用循环，支持任务拆解、断点续跑、Skill 三层注入（SOUL/AGENTS/IDENTITY）、上下文压缩
- **文献库（RAG）** — 翻译完成后自动将双语全文收录进本地向量库；Agent 按需调用 `search_documents` 跨文献检索，不自动注入每轮上下文；支持手动上传/删除文件
- **AI 润色 / 扩写 / 连贯性改写 / 合规检查** — 通过 AI Panel 对选中文本操作
- **Inline Ghost Text** — Monaco Editor 打字后 1.5s 自动请求补全建议，Tab 接受 ghost 文本

### 论证陪练（Argument Companion v3）+ 论证地图（v2）

> **投稿前的压力测试。** AI 主动发现逻辑问题，你只需回应。

- **论证账本（Claim Ledger）** — 自动提取 abstract/intro 中每条承诺，追踪正文是否兑付（paid / partial / unpaid / mismatch），每条锚定到精确字符偏移；改稿后用模糊重定位（anchored → drifted → lost 三态）保持锚点存活，类似 `git blame` 之于论证
- **Reviewer‑2 对抗** — 7 种会议校准的模拟评审（NeurIPS / ICML / ICLR / ACL / CVPR / KDD / CHI），每条批评锚到具体句子；作者逐条起草 rebuttal，reviewer 会被说服；三角度并行评审（方法/实验/写作）自动去重聚合
- **真实评审导入** — 粘贴真实 reviewer 意见，AI 结构化拆解为可逐条 rebuttal 的条目
- **实验缺口建议** — 对每条 unpaid / partial 承诺，AI 给出具体实验设计方案
- **Rebuttal 包导出** — 一键下载含所有批评点 + rebuttal 草稿的 Markdown 文件
- **Toulmin 论证图** — 节点（主张/依据/保证/支撑/限定/反驳）+ 关系，Vue Flow 画布可视化；AI 自动提取、批判审查、建议下一个元素；降维展开为结构化 Markdown/LaTeX 论文草稿

**状态**：Phase 0–5 全部完成，`features.argument_companion=true` 已发布，pytest 2025 passed / 11 skipped + vitest 482 passed。

### 思维导图
- **Vue Flow 画布** — 自定义节点卡片 + 连线（树边/关联线），支持拖拽、缩放、小地图
- **节点正文编辑** — 每个节点可展开正文编辑区（▸ 按钮），收起时显示首行预览
- **编辑器双向同步** — 编辑器 → 导图自动解析 heading + body，导图 → 编辑器完整保留内容
- **AI 智能展开** — 基于选中节点内容自动生成子主题
- **AI 逻辑检查** — 检测思维链中的逻辑问题
- **撤销/重做** — 100 步历史栈，支持 Ctrl+Z / Ctrl+Shift+Z
- **自动布局** — dagre 算法一键整理
- **快捷键** — Tab 添加子节点、Enter 添加兄弟、F2 编辑、Delete 删除悬停连线、方向键导航

### 翻译管道

> DeepL 级 PDF 翻译作为辅助入口，帮你快速把论文沉淀进工作流。

- **PDF 智能解析** — 16 种格式支持，自动检测单栏/双栏布局
- **文本清洗** — 17 阶段管线，修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区跳过** — 自动识别 REFERENCES/BIBLIOGRAPHY 区域，原样保留不翻译
- **DeepL-like 体验** — 左右双栏对照 + 句子悬停高亮，逐句精准对齐
- **实时进度** — SSE 流式推送 5 步管道进度，完整段落实时预览
- **失败块重试** — 翻译失败的块可单独重译，无需重新翻译全文
- **多格式导出** — 双语 Markdown/Word、纯译文 Markdown/Word 四种格式

### 翻译引擎
- **本地** — Ollama + Qwen3，全程离线，无需 API Key
- **云端** — OpenAI / Anthropic / DeepSeek / Moonshot / 智谱 / 通义千问 / Gemini / SiliconFlow / OpenRouter / Groq / Together / Mistral / xAI / Fireworks / DeepInfra / Perplexity / Novita / 火山方舟 / 百度千帆 / Azure / 自定义 (共 21 家供应商)
- **增强 Prompt** — 严格段落结构保持指令，显著降低对齐失败率
- **Glossary 自动提取** — 翻译结果中提取 `中文(English)` 术语对，注入后续块翻译
- **滑动上下文窗口** — 每块翻译携带前 N 块的摘要和术语表

### 语音助手

> **论文写作版的 Siri** — 喊"小研"或按 Alt+Shift+V 激活，Siri 浮层弹出，说指令直达功能。

- **语音指令路由** — 关键词分类 20+ 条命令，5 个层级直达功能：导航（翻译/编辑/论证/思维导图/主题）、文件（保存/新建/打开）、编辑器（导出/润色/扩写/审阅/中英互译/合规/引用）、翻译管道（新翻译/重试/导出 Word/PPTX）、思维导图（增删节点/AI 扩展/布局/缩放）；未命中自动走 Agent 聊天
- **唤醒词** — Web Speech API 连续模式，同音字变体匹配（小研/小严/小言/小岩 等均能识别）；5 秒冷却防误触发；设置中可自定义
- **全局热键** — `Alt+Shift+V` 系统级生效（Tauri 插件），窗口最小化也能唤醒
- **Siri 风格语音界面** — 全屏毛玻璃遮罩 + 脉冲球体 + 波纹扩散动画 + 实时转写；2 秒静默自动提交；命中命令后显示反馈（命令名 + 成功/失败）
- **语音打字** — 编辑器工具栏、Agent 面板、AI 编辑面板均有麦克风；说话即转录；按 Tab 接受 Ghost Text 后语音自动续接
- **免冲突设计** — 语音打字时唤醒词自动暂停，无麦克风争抢

### 编辑器
- **Monaco Editor** — 全功能代码编辑器，支持 Markdown 语法高亮
- **AI Panel** — 聊天风格 UI，支持消息历史；润色/扩写结果用 diff 视图对比原文，一键应用/撤销
- **文件树** — 多文件管理，左侧导航
- **模板导出** — Pandoc 编译，支持 IEEE/ACM/NeurIPS/LNCS/Elsevier/通用 LaTeX 模板

### 调试 & 可观测性
- **日志落文件** — 后端日志写入 `RUNTIME_DIR/logs/app.log`（10 MB × 5 备份轮转，每行携带 trace_id）
- **访问日志** — 每个 HTTP 请求记录 method/path/status/耗时
- **调试面板** — 顶栏 Terminal 图标按钮，显示前端错误历史（时间戳 + 级别）和后端日志；有未读错误时红色数字徽标提示

### 部署
- **桌面端** — Tauri 2 打包，自动管理 Python 后端和 Ollama 进程
- **离线开箱即用** — 发行版安装包内置 Pandoc / Tectonic（含预热 LaTeX 缓存）/ all-MiniLM-L6-v2 嵌入模型，首启播种到用户缓存，PDF 导出与文献库无需联网；翻译默认引擎为云端（用户自填 API Key）
- **Docker** — 多阶段构建，一键容器化运行
- **Python CLI** — `python main.py paper.pdf -o paper.md`

## 项目结构

```
├── src-tauri/                    # Rust + Tauri 桌面端
│   ├── src/main.rs               #   进程管理 (Python API + Ollama，自动清除代理环境变量)
│   └── capabilities/             #   Tauri v2 权限配置
├── src/                          # Vue 3 前端
│   ├── App.vue                   #   主界面薄壳（~684 行，管理全局状态）
│   ├── styles/tokens.css         #   Design Tokens（暗色/亮色主题）
│   ├── composables/
│   │   ├── useTranslate.ts       #   SSE 翻译管线状态管理（单例）
│   │   ├── useAgentChat.ts       #   Agent SSE 对话状态管理（单例）
│   │   ├── useEditor.ts          #   Monaco Editor + AI Panel（单例）
│   │   ├── useAiPanelState.ts    #   AI Panel 独立状态管理
│   │   ├── useFileTree.ts        #   文件树导航（单例）
│   │   ├── useMindMap.ts         #   思维导图数据 + undo/redo（单例）
│   │   ├── useMindMapKeyboard.ts #   思维导图键盘快捷键
│   │   ├── useMindMapLayout.ts   #   dagre 自动布局
│   │   ├── useMindMapAnalysis.ts #   AI 分析集成
│   │   ├── useArgumentMap.ts     #   Toulmin v2 论证图状态（单例，SSE 提取/审查/建议）
│   │   ├── useArgumentCompanion.ts # 论证陪练账本状态（单例，SSE 构建/重建）
│   │   ├── useArgumentLayout.ts  #   Toulmin dagre 布局（动态节点+关系分层）
│   │   ├── useSpeechRecognition.ts # Web Speech API（累积/去重/标点合并）
│   │   ├── useSpeechBusy.ts      #   全局忙标志（唤醒词 ↔ 语音打字冲突预防）
│   │   ├── useWakeWord.ts        #   唤醒词检测（连续 SR，同音字匹配，冷却）
│   │   ├── useGlobalHotkey.ts    #   系统热键注册（Tauri 插件，Alt+Shift+V）
│   │   ├── useVoiceCommand.ts    #   语音指令状态机 + 自动提交
│   │   ├── useVoiceRouter.ts     #   Siri 式意图路由（关键词分类 + 命令分发）
│   │   ├── useAppMode.ts         #   全局模式/面板状态（单例）
│   │   └── voiceCommands/        #   声明的命令注册表（5 tier，20+ 条命令）
│   ├── components/
│   │   ├── AppTopBar.vue         #   顶栏（品牌/模式切换/引擎设置/语音设置/窗口控制）
│   │   ├── TranslateView.vue     #   翻译模式（上传/进度/结果三视图）
│   │   ├── AgentPanel.vue        #   Agent 侧面板（对话/知识库/模板/会话）
│   │   ├── EditorLayout.vue      #   编辑器布局（~657 行，Monaco + AiPanel + FileTree）
│   │   ├── VoiceAssistantView.vue #   Siri 风格全屏语音界面（毛玻璃 + 脉冲/波纹动画）
│   │   ├── mindmap/              #   思维导图（Vue Flow 画布 + 自定义节点/边）
│   │   ├── ui/                   #   UI 原语（Button/Input/Panel/Tooltip…）
│   │   └── …                     #   MonacoEditor, AiPanel, ArgumentMap 等
│   ├── utils/
│   │   ├── api.ts                #   API base URL（自动检测 Tauri/Web）
│   │   └── streamReader.ts       #   统一 SSE 流解析工具（6 个调用点共用）
│   └── types/index.ts            #   共享 TypeScript 类型
├── python/                       # Python 后端
│   ├── api_factory.py            #   FastAPI app 工厂（仅保留核心逻辑）
│   ├── routers/                  #   路由模块（按功能拆分）
│   │   ├── translate.py          #   翻译/配置/健康检查路由
│   │   ├── agent.py              #   Agent 对话/RAG/工具路由
│   │   ├── editor.py             #   编辑/导出/Vision/Citation路由
│   │   ├── argument.py           #   动态逻辑引擎路由
│   │   └── mindmap.py            #   思维导图持久化 + AI 分析/扩展
│   ├── main.py                   #   CLI 入口
│   ├── config/default.yaml       #   默认配置
│   ├── src/
│   │   ├── parser/               #   16 格式解析器
│   │   ├── cleaner/              #   17 阶段清洗管线
│   │   ├── chunker/              #   3 策略切块 (sentence/paragraph/fixed)
│   │   ├── translator/           #   Ollama + Cloud 双客户端 (21 家供应商)
│   │   ├── formatter/            #   3 输出模式 + Pandoc 导出
│   │   ├── agent/                #   ReAct Agent + RAG + Tools + Skills
│   │   │   ├── agent.py          #     AgentLoop ReAct 引擎
│   │   │   ├── session.py        #     会话管理 (断点续传/审批)
│   │   │   ├── session_store.py  #     会话持久化 (JSON)
│   │   │   ├── memory.py         #     短/长期记忆
│   │   │   ├── skill_system.py   #     Skill 沉淀 (调度 → 匹配/持久化/自动提取子模块)
│   │   │   ├── prompt_builder.py #     Prompt 组装 (Skill SOUL/AGENTS 注入)
│   │   │   ├── context_compressor.py # 上下文压缩
│   │   │   ├── llm_client.py     #     统一 LLM 客户端 (按后端拆分为 _llm_*.py)
│   │   │   ├── security_gate.py  #     工具执行安全门控
│   │   │   ├── hooks.py          #     错误/重试 Hook
│   │   │   ├── tools/            #     工具集 (core/atomic/builtin/workspace/registry)
│   │   │   └── ...               #     mcp_server, rag, review_agent, trajectory, etc.
│   │   ├── argument/             #   论证地图 v2 + 论证陪练 v3 (llm_client, ai_ops, ledger, reviewer, _reviewer_perspectives, anchor, companion_store, graph_store)
│   │   ├── plugin/               #   MCP 风格插件注册
│   │   ├── citation/             #   引用索引器
│   │   ├── zotero/               #   Zotero API 集成
│   │   └── mcp/                  #   Vision 客户端 (多模态图像理解)
│   ├── prompts/                  #   学术写作 Prompt 体系 (6层骨架 + YAML frontmatter + eval runner)
│   ├── data/paper_assets/        #   论文模板 (IEEE/ACM/NeurIPS/LNCS/通用)
│   └── tests/                    #   单元测试 + 集成测试（含 E2E companion + adversarial），pytest 2025 passed / 11 skipped
├── Dockerfile
├── docker-compose.yml
└── package.json
```

## 下载安装

### 桌面端安装包（Windows / macOS / Linux）

GitHub Releases 页面：https://github.com/zuowen7/scholar-assistant/releases

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
docker pull zuowen7/scholar-assistant:latest

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

# 开发模式（自动清除代理环境变量，避免 httpx import 卡住）
start_dev.bat
# 或手动清除代理后运行
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

翻译 SSE 事件顺序：`progress` → `parsed` → `cleaned` → `chunked` → `chunk_done`(×N) → `complete`

### 翻译
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/translate` | 上传文档，返回 task_id |
| `POST` | `/api/translate/path` | 从文件路径翻译 |
| `GET` | `/api/translate/{id}/stream` | SSE 翻译进度流 |
| `GET` | `/api/download/{id}` | 下载翻译结果 |

### 引擎状态
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/ollama/status` | Ollama 状态 |
| `GET` | `/api/cloud/status` | 云端 API 状态 |
| `GET` | `/api/cloud/providers` | 列出可用供应商 |

### 配置
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/config` | 读取配置 |
| `PUT` | `/api/config` | 写入配置 |

### Agent & 编辑
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | Agent SSE 对话 (ReAct 循环) |
| `POST` | `/api/agent/v2/chat` | Agent V2 SSE 对话 (会话管理) |
| `GET` | `/api/agent/v2/sessions` | 列出会话历史 |
| `POST` | `/api/agent/v2/resume/{session_id}` | 恢复会话 |
| `POST` | `/api/agent/v2/approve/{session_id}/{event_id}` | 审批工具调用 |
| `POST` | `/api/agent/v2/abort/{session_id}` | 中止会话 |
| `POST` | `/api/agent/v2/undo/{session_id}` | 撤销上一步 |
| `POST` | `/api/agent/v2/tool` | 直接调用工具 |
| `POST` | `/api/edit` | AI 驱动的 SSE 流式编辑 |
| `POST` | `/api/complete` | 非流式 inline 补全 |
| `GET` | `/api/agent/stats` | Agent 统计信息 |

### RAG 知识库
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/rag/documents` | 列出 RAG 文档 |
| `POST` | `/api/rag/upload` | 上传文件到 RAG |
| `POST` | `/api/rag/ingest` | 向 RAG 存入文本 |
| `DELETE` | `/api/rag/documents/{doc_id}` | 删除 RAG 文档 |

### 动态逻辑引擎 (v2)
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/argument/graph` | 创建论证图 |
| `GET` | `/api/argument/graph/{gid}` | 获取论证图 |
| `GET` | `/api/argument/graphs` | 列出所有论证图 |
| `DELETE` | `/api/argument/graph/{gid}` | 删除论证图 |
| `PUT` | `/api/argument/graph/{gid}/node` | 创建/更新节点 |
| `DELETE` | `/api/argument/graph/{gid}/node/{nid}` | 删除节点 |
| `PUT` | `/api/argument/graph/{gid}/edge` | 创建/更新关系 |
| `DELETE` | `/api/argument/graph/{gid}/edge/{eid}` | 删除关系 |
| `PUT` | `/api/argument/graph/{gid}/span` | 创建原文绑定 |
| `DELETE` | `/api/argument/graph/{gid}/span/{sid}` | 删除原文绑定 |
| `POST` | `/api/argument/graph/{gid}/extract` | SSE 提取 Toulmin 论证图 |
| `POST` | `/api/argument/graph/{gid}/critique` | AI 批判审查 |
| `POST` | `/api/argument/graph/{gid}/suggest` | AI 建议下一个元素 |
| `POST` | `/api/argument/graph/{gid}/flatten` | SSE 降维展开为论文草稿 |

### 论文写作
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/paper-assets/templates` | 列出论文模板 |
| `POST` | `/api/paper-assets/ingest` | 索引模板素材 |
| `POST` | `/api/paper-scaffold` | 生成论文大纲 |
| `POST` | `/api/paper-style-transfer` | 风格迁移 |
| `POST` | `/api/compliance` | 合规检查 |

### 导出
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/export/templates` | 列出导出模板 |
| `POST` | `/api/export` | 导出文档 (LaTeX/PDF) |
| `POST` | `/api/export/pdf` | 导出为 PDF |
| `POST` | `/api/export/word` | 导出为 Word (.docx) |
| `GET` | `/api/export/word/{filename}` | 下载 Word 导出 |

### Vision
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/vision/analyze` | 通用图像分析 |
| `POST` | `/api/vision/ocr` | OCR 文字提取 |
| `POST` | `/api/vision/chart` | 图表分析 |
| `POST` | `/api/vision/table` | 表格结构提取 |

### 论证陪练（Argument Companion v3）
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/companion/ledger/build` | SSE 构建论证账本（anchor* → promise* → complete） |
| `GET` | `/api/companion/ledger?doc_id=` | 获取账本 |
| `PUT` | `/api/companion/ledger/promise?doc_id=` | 新增/更新承诺条目 |
| `DELETE` | `/api/companion/ledger/promise/{pid}?doc_id=` | 删除承诺 |
| `POST` | `/api/companion/ledger/relocate?doc_id=` | 改稿后重定位所有锚点 |
| `POST` | `/api/companion/ledger/promise/{pid}/suggest-experiment?doc_id=` | 实验缺口建议 |
| `POST` | `/api/companion/review` | SSE 模拟评审（review_point* → complete）；`mode: "parallel"` 启用三角度并行 |
| `GET` | `/api/companion/review/{session_id}` | 获取评审会话 |
| `GET` | `/api/companion/reviews` | 列出文档评审历史 |
| `PUT` | `/api/companion/review/{sid}/point/{pid}` | 更新批评点状态 |
| `POST` | `/api/companion/review/{sid}/point/{pid}/rebut` | SSE rebuttal（reviewer 会被说服） |
| `POST` | `/api/companion/review/import` | SSE 导入真实审稿意见 |
| `GET` | `/api/companion/download/review/{session_id}` | 下载 rebuttal Markdown 包 |
| `DELETE` | `/api/companion/review/{session_id}` | 删除评审会话 |

### 思维导图
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/mindmap/save` | 保存思维导图 |
| `GET` | `/api/mindmap/load` | 加载思维导图 |
| `DELETE` | `/api/mindmap` | 删除思维导图 |
| `POST` | `/api/mindmap/analyze` | AI 分析思维导图 |
| `POST` | `/api/mindmap/expand` | AI 扩展节点 |

### Zotero
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/zotero/status` | 连接状态 |
| `POST` | `/api/zotero/search` | 搜索 Zotero 库 |
| `GET` | `/api/zotero/item/{key}` | 获取条目元数据 |
| `GET` | `/api/zotero/item/{key}/bibtex` | 获取 BibTeX |
| `POST` | `/api/zotero/export` | 导出条目到文件 |
| `POST` | `/api/zotero/citations` | 提取引用 |

### 调试
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/logs` | 返回最近 N 行后端日志 + 日志文件路径 |

### 其他
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/plugins` | 列出已注册插件工具 |
| `GET` | `/api/tectonic/status` | LaTeX 引擎状态 |
| `POST` | `/api/tectonic/install` | 安装 Tectonic |
| `PUT` | `/api/citation/index` | 索引引用 |
| `GET` | `/api/citation/extract` | 提取引用 |
| `POST` | `/api/upload/image` | 上传图片 |
| `GET` | `/api/assets/{filename}` | 获取资源文件 |

## 配置

编辑 `python/config/default.yaml`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `parser.engine` | pdfplumber | PDF 解析引擎 |
| `chunker.max_tokens` | 800 | 每块最大 token 数（曾为 2048，过大导致对齐回退） |
| `chunker.strategy` | sentence | 切块策略 |
| `translator.engine` | cloud | 翻译引擎: ollama / cloud |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.temperature` | 0.3 | 生成温度 |
| `translator.timeout` | 300 | 翻译超时 (秒) |
| `formatter.output_format` | bilingual | 输出格式 |
| `agent.enabled` | true | 是否启用 Agent |
| `rag.enabled` | true | 是否启用 RAG（仅本地） |
| `features.parallel_review` | false | 三角度并行评审（需在 `default.local.yaml` 启用） |

## 测试

```bash
# Python 后端测试
cd python && pytest tests/ -v

# 前端单元测试
npx vitest
```

## 技术栈

| 层 | 技术 |
|----|------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor, Vue Flow |
| 桌面端 | Tauri 2 (Rust) |
| 后端 | Python 3.12, FastAPI, SSE |
| 翻译（本地） | Ollama + Qwen3:8b |
| 翻译（云端） | OpenAI / Anthropic / DeepSeek 等 21 家供应商 |
| PDF | PyMuPDF, pdfplumber |
| 向量数据库 | ChromaDB + all-MiniLM-L6-v2（仅本地） |
| LaTeX 导出 | Pandoc + 6 套模板 (IEEE Conf/Journal, ACM, NeurIPS, LNCS, 通用) |
| 思维导图 | Vue Flow + dagre 自动布局 |
| 容器化 | Docker 多阶段构建 |

---

如果这个项目能帮到你的论文工作流，欢迎点个 star。PR 和 Issue 都欢迎。