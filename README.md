# Scholar Translate

本地离线 + 云端大模型双引擎学术文献智能翻译工具。支持 16 种文件格式，自动清洗排版噪声，输出高质量双语对照文档。

## 一键安装桌面端

前往 [Releases 页面](https://github.com/zuowen7/translator/releases) 下载对应平台的安装包：

| 平台 | 文件 |
|------|------|
| Windows | `.exe` 安装包 |
| macOS (Apple Silicon) | `.dmg` |
| macOS (Intel) | `.dmg` |
| Linux | `.AppImage` 或 `.deb` |

安装后启动应用，在「翻译引擎设置」中选择引擎：

- **本地 Ollama**：安装 [Ollama](https://ollama.com) 并拉取模型 → `ollama pull qwen3:8b`
- **云端 API**：填写 API Key 即可使用，无需安装 Ollama（支持 OpenAI、Anthropic、DeepSeek 等）

---

## Docker 一键部署（Web 版）

适合服务器部署或不想安装桌面端的用户。

**前提条件**：安装 [Docker](https://www.docker.com/)

```bash
# 1. 克隆仓库
git clone https://github.com/zuowen7/translator.git
cd translator

# 2. 一键启动
docker compose up -d

# 3. 拉取翻译模型（首次使用）
docker compose exec ollama ollama pull qwen3:8b

# 4. 浏览器打开
# http://localhost:18088
```

### 常用命令

```bash
docker compose up -d          # 启动
docker compose down           # 停止
docker compose logs -f app    # 查看应用日志
```

### GPU 加速

默认 CPU 运行。如需 GPU 加速，编辑 `docker-compose.yml`，取消 ollama 服务的 `deploy` 注释块（需要 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)）。

---

## 功能特性

### 文档解析
- **16 种格式支持** — PDF、Word、Excel、PowerPoint、TXT、Markdown、HTML、EPUB、RTF、LaTeX、CSV、JSON、XML、SRT 等
- **PDF 智能解析** — 自动检测单栏/双栏布局，准确提取文本
- **文本清洗** — 修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区自动跳过** — 识别 REFERENCES 区域并跳过翻译，减少 token 浪费

### 翻译引擎
- **本地 Ollama** — 基于 Qwen3 模型，全程离线，无需 API Key
- **云端 API** — 支持 OpenAI、Anthropic、DeepSeek、Google Gemini 等主流供应商
- **术语一致性** — 自动构建术语表，跨 chunk 保持翻译一致
- **文档级上下文** — 注入标题+摘要作为全局上下文
- **翻译质量校验** — 自动检测未翻译、截断等问题并重试

### 阅读体验
- **三种视图** — 逐句对照 / 段落对照 / 全文 Markdown
- **阅读自定义** — 字号、行高、字体、译文颜色可调节
- **日间/夜间模式** — 一键切换亮暗主题，毛玻璃效果
- **自定义背景** — 支持本地图片/视频作为窗口背景，可调节透明度

### 工程质量
- **实时进度** — SSE 流式推送，解析/清洗/切块/翻译/格式化 5 步进度可视化
- **安全防护** — 路径遍历防护、API Key 脱敏、XSS 注入阻断
- **Docker 一键部署** — `docker compose up -d` 即可使用

---

## 本地开发

```bash
# 安装前端依赖
npm install

# 安装 Python 依赖
pip install -r python/requirements.txt

# 安装 Ollama 并拉取模型（本地模式）
ollama pull qwen3:8b

# 启动桌面应用（开发模式）
npm run tauri dev

# 构建安装包
npm run tauri build
```

### 纯云端模式（无需 Ollama）

适合只使用各家云端大模型 API 的场景：

```bash
cd python
pip install -r requirements.txt
# 在 config/default.yaml 填写 translator.cloud，或用前端「翻译引擎 → 云端 API」保存
python api_cloud.py --host 127.0.0.1 --port 18089
```

- 翻译始终走云端；`GET /api/health` 会包含 `"mode": "cloud_only"`。
- 上传与输出目录为 `python/data_cloud/`，与本地 `api.py` 使用的 `python/data/` 分开。
- 供应商列表见 `GET /api/cloud/providers`；未列出的 OpenAI 兼容网关选「自定义」并填写 Base URL。

---

## 发布新版本

```bash
# 打 tag 触发 GitHub Actions 自动构建并发布
git tag v0.3.0
git push origin v0.3.0
```

构建完成后会在 [Releases 页面](https://github.com/zuowen7/translator/releases) 自动生成草稿，点击发布即可。

---

## 项目结构

```
├── src/                        # Vue 3 前端
│   ├── App.vue                 # 主界面（上传/进度/结果）
│   ├── composables/
│   │   └── useTranslate.ts     # 翻译状态管理 + SSE 客户端
│   └── types/                  # TypeScript 类型定义
├── src-tauri/                  # Tauri 2 桌面端（Rust）
│   └── src/main.rs             # 进程管理（Python + Ollama 子进程）
├── python/
│   ├── api.py                  # FastAPI：Ollama + 可选云端
│   ├── api_cloud.py            # 纯云端模式（无 Ollama），数据在 data_cloud/
│   ├── api_factory.py          # 应用工厂 create_app(cloud_only=…)
│   ├── src/
│   │   ├── parser/             # 多格式文档解析（dispatcher + PDF extractor）
│   │   ├── cleaner/            # 文本清洗管道
│   │   ├── chunker/            # 智能切块（sentence/paragraph/fixed 策略）
│   │   ├── translator/         # 翻译客户端（Ollama + Cloud）
│   │   │   ├── ollama_client.py    # 本地 Ollama 客户端
│   │   │   ├── cloud_client.py     # 云端 API 客户端
│   │   │   └── context.py          # 文档级上下文提取
│   │   ├── formatter/          # 输出格式化（bilingual/parallel/translated_only）
│   │   └── constants.py        # 共享常量（引用区检测模式等）
│   ├── tests/unit/             # 单元测试
│   └── config/                 # 默认 & Docker 配置
├── .github/workflows/          # CI/CD：tag 触发自动构建
├── Dockerfile                  # 多阶段构建（前端 + 后端）
├── docker-compose.yml          # Ollama + Web 一键部署
└── vite.config.ts              # Vite 配置
```

## 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `chunker.max_tokens` | 2048 | 每块最大 token 数 |
| `chunker.overlap_tokens` | 128 | 块间重叠 token 数 |
| `chunker.strategy` | sentence | 切块策略 (sentence/paragraph/fixed) |
| `translator.engine` | ollama | 翻译引擎 (ollama/cloud) |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.num_predict` | 16384 | 最大生成 token 数 |
| `translator.temperature` | 0.3 | 生成温度 |
| `translator.cloud.provider` | openai | 云端供应商 (openai/anthropic/deepseek 等) |
| `translator.cloud.api_key` | | 云端 API Key |
| `translator.cloud.base_url` | https://api.openai.com/v1 | 云端 API 地址 |
| `translator.cloud.model` | gpt-4o | 云端模型名称 |
| `formatter.output_format` | bilingual | 输出格式 (bilingual/parallel/translated_only) |

## 技术栈

- **前端**: Vue 3 + TypeScript + Vite + Tauri 2
- **后端**: Python FastAPI + SSE
- **文档解析**: pdfplumber, python-docx, python-pptx, openpyxl, ebooklib, beautifulsoup4, pylatexenc, striprtf
- **翻译引擎**: Ollama (Qwen3) / OpenAI 兼容 API / Anthropic
- **容器化**: Docker 多阶段构建

## License

[MIT](LICENSE)
