# Scholar Translate

本地离线 + 云端大模型双引擎学术文献智能翻译工具。支持 16 种文件格式，自动清洗排版噪声，输出高质量双语对照文档。内置 Agent 助手，支持文档检索、arXiv 搜索和智能问答。

> **v0.3.1** — PDF 双栏提取优化、翻译循环重复检测、纯 Python / Pandoc 双通道 PDF 导出、NSIS 一键安装
>
> **Agent v2** — 上下文工程 + 持久记忆 + 动态 Skill + 错误恢复 + 生命周期 Hook（Phase 1/2/3 已完成）

## 一键安装桌面端

前往 [Releases 页面](https://github.com/zuowen7/translator/releases) 下载 `Scholar Translate_0.3.1_x64-setup.exe`，安装即可：

- **内置 Pandoc 3.6.2** — 无需手动安装，NSIS 安装包已打包
- **内置 Python 后端** — PyInstaller 单文件打包，开箱即用
- 支持本地 Ollama 或云端 API 翻译引擎

### 翻译引擎配置

安装后启动应用，在「翻译引擎设置」中选择引擎：

| 引擎 | 配置方式 |
|------|----------|
| **本地 Ollama** | 安装 [Ollama](https://ollama.com) → `ollama pull qwen3:8b` |
| **云端 API** | 填写 API Key，支持 OpenAI / Anthropic / DeepSeek / 智谱 等 |

---

## 功能特性

### 文档解析
- **16 种格式** — PDF、Word、Excel、PowerPoint、TXT、Markdown、HTML、EPUB、RTF、LaTeX、CSV、JSON、XML、SRT
- **PDF 智能解析** — 自动检测单栏/双栏布局，词间距丢失时自动回退字符级坐标推断
- **文本清洗** — 修复断行、移除水印/页眉页脚、处理连字符断词、修复跨页截断词
- **引用区自动跳过** — 识别 REFERENCES 区域并跳过翻译，减少 token 浪费

### 翻译引擎
- **本地 Ollama** — 基于 Qwen3 模型，全程离线，无需 API Key
- **云端 API** — 支持 OpenAI、Anthropic、DeepSeek、智谱 GLM 等主流供应商
- **术语一致性** — 自动构建术语表，跨 chunk 保持翻译一致
- **翻译质量校验** — 自动检测未翻译、截断、循环重复等问题并重试

### 阅读体验
- **三种视图** — 逐句对照 / 段落对照 / 全文 Markdown
- **阅读自定义** — 字号、行高、字体、译文颜色可调节
- **日间/夜间模式** — 一键切换亮暗主题

### Agent 智能助手
- **ReAct 推理循环** — 手写 Agent 框架，不依赖 LangChain/LlamaIndex
- **上下文工程** — 比例阈值压缩（头尾保护 + 中间 LLM 摘要），动态 System Prompt 拼装
- **持久记忆** — MEMORY.md + SQLite 双层存储，自动召回相关记忆注入上下文
- **动态 Skill** — 从任务轨迹沉淀可复用经验，字符级智能匹配，催促机制
- **错误恢复** — 14 类错误分类 + 指数退避重试，自动降级策略
- **生命周期 Hook** — 12 个扩展点，支持同步/异步 Hook 注入
- **后台审查** — 异步三维度审查（记忆 + Skill + 综合），不阻塞前台
- **RAG 文档检索** — 基于 ChromaDB 的本地向量存储，CPU 嵌入零配置
- **工具调用** — 文档翻译、文本检索、arXiv 论文搜索
- **对话管理** — 流式 SSE 输出，事件卡片可视化推理过程

### PDF 导出
- **Pandoc 双通道** — Pandoc 可用时走 Pandoc → LaTeX → PDF；不可用时自动降级纯 Python `markdown_to_latex()` 引擎
- **期刊模板** — 支持 generic、IEEE、ACM、CVPR、Springer、Elsevier 等模板
- **Tectonic 编译** — 自动检测系统 Tectonic 安装，优先用于 PDF 编译

---

## 项目结构

```
├── src/                          # Vue 3 前端
│   ├── App.vue                   # 主界面（上传/进度/结果 + Agent 面板）
│   ├── components/              # UI 组件（FileTree、EditorLayout、AgentPanel 等）
│   ├── composables/
│   │   ├── useTranslate.ts       # 翻译状态管理 + SSE 客户端
│   │   ├── useAgentChat.ts       # Agent 对话状态管理 + SSE 客户端
│   │   ├── useEditor.ts          # Monaco Editor 封装
│   │   └── useFileTree.ts        # 文件树管理
│   └── types/                   # TypeScript 类型定义
├── src-tauri/                    # Tauri 2 桌面端（Rust）
│   ├── src/main.rs              # 进程管理（启动 Python/Ollama 子进程）
│   ├── capabilities/            # Tauri capability 权限配置
│   ├── resources/pandoc/        # 内置 Pandoc 3.6.2（NSIS 打包）
│   └── python-dist/             # PyInstaller 打包的 Python 后端
├── python/
│   ├── api_factory.py           # FastAPI 应用工厂（翻译 + Agent 双模式）
│   ├── pandoc_templates/        # Pandoc 输出模板（generic.tex 等）
│   ├── prompts/                 # Agent / AI Edit prompt 模板
│   ├── paper_assets.py          # 期刊模板资产工具
│   ├── src/
│   │   ├── parser/              # 多格式文档解析
│   │   ├── cleaner/             # 文本清洗管道
│   │   ├── chunker/             # 智能切块（sentence/paragraph/fixed）
│   │   ├── translator/          # 翻译客户端（Ollama + Cloud）
│   │   ├── agent/               # Agent 子系统（ReAct + RAG + 记忆 + Skill）
│   │   │   ├── agent.py         # ReAct 推理循环（双策略工具调用 + 上下文压缩）
│   │   │   ├── context_compressor.py  # 比例阈值上下文压缩器
│   │   │   ├── prompt_builder.py     # 动态 System Prompt 拼装
│   │   │   ├── memory.py        # 持久化记忆（MEMORY.md + SQLite）
│   │   │   ├── skill_system.py  # 动态 Skill 系统
│   │   │   ├── trajectory.py    # ReAct 轨迹记录器
│   │   │   ├── review_agent.py  # 后台审查 Agent
│   │   │   ├── error_classifier.py  # 14 类错误分类 + 恢复策略
│   │   │   ├── hooks.py         # 生命周期 Hook 系统
│   │   │   ├── tools.py         # 工具注册表
│   │   │   ├── rag.py           # ChromaDB 向量存储
│   │   │   └── vram_manager.py  # VRAM 时分复用调度
│   │   └── formatter/           # 输出格式化
│   └── config/                  # 默认配置
├── scripts/
│   └── api.spec                 # PyInstaller spec 文件
├── .github/workflows/            # CI/CD：tag 触发自动构建 + 发布
├── Dockerfile                   # 多阶段构建
├── docker-compose.yml           # Ollama + Web 一键部署
├── vite.config.ts               # Vite 配置
└── README.md
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 桌面端 | Tauri 2 + Rust | 窗口管理 + 子进程生命周期绑定 |
| 前端 | Vue 3 + TypeScript + Vite | 单页应用 |
| 编辑器 | Monaco Editor | Markdown 语法高亮 + AI 辅助编辑 |
| 后端 | Python FastAPI + SSE | 翻译流式输出 + Agent 对话 |
| 文档解析 | pdfplumber, python-docx, ebooklib 等 | 16 种格式支持 |
| 翻译 | Ollama (Qwen3) / 云端 OpenAI 兼容 API | 本地 + 云端双模式 |
| Agent | 手写 ReAct + ChromaDB + 记忆 + Skill | 不依赖 LangChain/LlamaIndex，自进化架构 |
| PDF 导出 | Pandoc + Tectonic + 纯 Python 降级 | 双通道保障 |

## 本地开发

```bash
# 前端依赖
npm install

# Python 依赖
cd python
pip install -r requirements.txt

# 启动桌面应用（开发模式）
npm run tauri dev

# 构建安装包（需先安装 Rust）
npm run tauri build
```

### 纯云端模式（无需 Ollama）

```bash
cd python
pip install -r requirements.txt
python api_cloud.py --host 127.0.0.1 --port 18089
```

---

## 发布新版本

```bash
# 修改版本号后，打 tag 触发 GitHub Actions 自动构建
git tag v0.3.2
git push origin v0.3.2
```

GitHub Actions 完成构建后，在 [Releases 页面](https://github.com/zuowen7/translator/releases) 自动生成草稿，点击发布即可。