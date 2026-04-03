# Scholar Translate

本地离线英文学术文献智能翻译工具。输入 PDF，自动清洗排版噪声，输出高质量双语对照文档。

## 功能特性

- **PDF 智能解析** — 自动检测单栏/双栏布局，准确提取文本
- **文本清洗** — 修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区跳过** — 自动识别 REFERENCES 区域，原样保留不翻译
- **本地翻译** — 基于 Ollama + Qwen3，全程离线，无需 API Key
- **双语逐句对照** — 翻译结果按句配对，支持逐句/段落/全文三种视图
- **桌面端 UI** — Tauri + Vue 3 桌面应用，拖拽 PDF 即可翻译
- **Web UI** — Docker 一键部署，浏览器即可使用

## 项目结构

```
├── src/                        # Vue 3 前端
│   ├── App.vue                 # 主界面 (上传、进度、结果展示)
│   ├── composables/            # Vue composables
│   └── types/                  # TypeScript 类型
├── src-tauri/                  # Tauri 2 桌面端 (Rust)
├── python/
│   ├── api.py                  # FastAPI 服务端 (Web API + SSE)
│   ├── main.py                 # CLI 入口
│   ├── config/
│   │   ├── default.yaml        # 默认配置
│   │   └── docker.yaml         # Docker 环境配置
│   ├── src/                    # Python 核心模块
│   │   ├── parser/             # PDF 解析 (pdfplumber)
│   │   ├── cleaner/            # 文本清洗管线
│   │   ├── chunker/            # 文本切块
│   │   ├── translator/         # Ollama 翻译客户端
│   │   └── formatter/          # 输出格式化
│   └── tests/                  # 单元测试
├── Dockerfile                  # 多阶段 Docker 构建
├── docker-compose.yml          # Ollama + Web UI 一键部署
└── scripts/docker.sh           # Docker 便捷脚本
```

## 快速开始

### 方式一: Docker 一键部署 (推荐)

```bash
# 克隆仓库
git clone https://github.com/zuowen7/translator.git
cd translator

# 启动所有服务 (Ollama + Web UI)
docker compose -p scholar-translate up -d

# 首次使用需要拉取模型
docker compose -p scholar-translate exec ollama ollama pull qwen3:8b

# 浏览器打开 http://localhost:18088
```

### 方式二: 桌面端 (Tauri)

需要: Node.js 20+, Python 3.12+, Ollama, Rust + MSYS2

```bash
npm install
ollama pull qwen3:8b
npx tauri dev
```

### 方式三: CLI

```bash
cd python
pip install -r requirements.txt
python main.py paper.pdf -o paper.md
```

## 配置

编辑 `python/config/default.yaml` 自定义行为：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `chunker.max_tokens` | 1024 | 每块最大 token 数 |
| `chunker.strategy` | sentence | 切块策略 |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.num_predict` | 16384 | 最大生成 token 数 |
| `translator.temperature` | 0.3 | 生成温度 |
| `formatter.output_format` | bilingual | 输出格式 |

## 技术栈

- **前端**: Vue 3 + TypeScript + Vite + Tauri 2
- **后端**: Python FastAPI + SSE
- **PDF 解析**: PyMuPDF, pdfplumber
- **翻译引擎**: Ollama (Qwen3:8b)
- **容器化**: Docker 多阶段构建

## License

[MIT](LICENSE)
