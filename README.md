# Scholar Translate

本地离线英文学术文献智能翻译工具。拖入 PDF，自动清洗排版噪声，输出高质量双语对照文档。

## 功能特性

- **PDF 智能解析** — 自动检测单栏/双栏布局，准确提取文本
- **文本清洗** — 修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区跳过** — 自动识别 REFERENCES 区域，原样保留不翻译
- **本地翻译** — 基于 Ollama + Qwen3，全程离线，无需 API Key
- **双语逐句对照** — 原文与译文左右并排，逐段对照
- **实时进度** — SSE 流式推送 5 步管道进度，翻译块级粒度
- **桌面端** — Tauri 2 打包，自动管理 Python 后端和 Ollama 进程
- **Docker 部署** — 多阶段构建，一键容器化运行

## 项目结构

```
├── src-tauri/               # Rust + Tauri 桌面端
│   ├── src/main.rs          #   进程管理 (Python API + Ollama)
│   ├── Cargo.toml
│   └── capabilities/        #   Tauri v2 权限配置
├── src/                     # Vue 3 前端
│   ├── App.vue              #   主界面 (上传/进度/双语对照)
│   ├── composables/
│   │   └── useTranslate.ts  #   SSE 翻译管线状态管理
│   └── types/index.ts       #   TypeScript 类型定义
├── python/                  # Python 翻译引擎
│   ├── api.py               #   FastAPI HTTP + SSE 服务
│   ├── main.py              #   CLI 入口
│   ├── config/default.yaml  #   默认配置
│   ├── src/
│   │   ├── parser/          #   PDF 解析 (pdfplumber)
│   │   ├── cleaner/         #   文本清洗管线
│   │   ├── chunker/         #   文本切块
│   │   ├── translator/      #   Ollama 翻译客户端
│   │   └── formatter/       #   输出格式化
│   └── tests/               #   49 个单元测试
├── Dockerfile               # Docker 多阶段构建
├── docker-compose.yml
├── index.html
├── vite.config.ts
└── package.json
```

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
docker compose --project-name scholar-translate build

OLLAMA_HOST=0.0.0.0:11434 ollama serve

# Windows (Git Bash)
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd)/python/data/input:/data/input:ro" \
  -v "$(pwd)/python/data/output:/data/output" \
  --add-host=host.docker.internal:host-gateway \
  scholar-translate-app:latest \
  /data/input/paper.pdf -o /data/output/paper.md -c config/docker.yaml
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/ollama/status` | Ollama 状态 |
| `POST` | `/api/translate` | 上传 PDF，返回 task_id |
| `GET` | `/api/translate/{id}/stream` | SSE 翻译进度流 |
| `GET` | `/api/download/{id}` | 下载翻译结果 |
| `GET/PUT` | `/api/config` | 读写配置 |

SSE 事件顺序：`progress` → `parsed` → `cleaned` → `chunked` → `chunk_done`(×N) → `complete`

## 配置

编辑 `python/config/default.yaml`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `parser.engine` | pdfplumber | PDF 解析引擎 |
| `chunker.max_tokens` | 2048 | 每块最大 token 数 |
| `chunker.strategy` | sentence | 切块策略: sentence / paragraph / fixed |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.temperature` | 0.3 | 生成温度 |
| `translator.timeout` | 300 | 翻译超时 (秒) |
| `formatter.output_format` | bilingual | 输出格式 |

## 测试

```bash
cd python && pytest tests/ -v
```

## 技术栈

| 层 | 技术 |
|----|------|
| UI | Vue 3, TypeScript, Vite |
| 桌面端 | Tauri 2 (Rust) |
| 后端 | Python 3.12, FastAPI, SSE |
| 翻译 | Ollama, Qwen3:8b |
| PDF | PyMuPDF, pdfplumber |
| 容器化 | Docker 多阶段构建 |

## License

[MIT](LICENSE)
