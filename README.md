# Scholar Translate

本地离线英文学术文献智能翻译工具。输入 PDF，自动清洗排版噪声，输出高质量双语对照文档。

## 功能特性

- **PDF 智能解析** — 自动检测单栏/双栏布局，准确提取文本
- **文本清洗** — 修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区跳过** — 自动识别 REFERENCES 区域，原样保留不翻译
- **本地翻译** — 基于 Ollama + Qwen3，全程离线，无需 API Key
- **双语对照输出** — 支持 bilingual / parallel / translated-only 三种格式

## 项目结构

```
├── main.py                  # CLI 入口
├── config/
│   ├── default.yaml         # 默认配置
│   └── docker.yaml          # Docker 环境配置
├── src/
│   ├── parser/              # PDF 解析 (pdfplumber)
│   ├── cleaner/             # 文本清洗管线
│   ├── chunker/             # 文本切块
│   ├── translator/          # Ollama 翻译客户端
│   └── formatter/           # 输出格式化
├── tests/                   # 单元测试 (49个)
├── Dockerfile               # Docker 镜像
├── docker-compose.yml       # 服务编排
└── data/
    ├── input/               # PDF 输入目录
    └── output/              # 翻译输出目录
```

## 快速开始

### 前置条件

- Python 3.12+
- [Ollama](https://ollama.ai) + Qwen3 模型 (`ollama pull qwen3:8b`)
- (可选) Docker + Docker Desktop

### 本地运行

```bash
pip install -r requirements.txt
ollama serve                                    # 启动 Ollama
python main.py paper.pdf -o paper.md           # 翻译
```

### Docker 运行

```bash
# 构建镜像
docker compose --project-name scholar-translate build

# 翻译 (确保 Ollama 监听 0.0.0.0)
OLLAMA_HOST=0.0.0.0:11434 ollama serve

# Windows (Git Bash)
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd)/data/input:/data/input:ro" \
  -v "$(pwd)/data/output:/data/output" \
  --add-host=host.docker.internal:host-gateway \
  scholar-translate-app:latest \
  /data/input/paper.pdf -o /data/output/paper.md -c config/docker.yaml

# Linux / macOS
docker run --rm \
  -v $(pwd)/data/input:/data/input:ro \
  -v $(pwd)/data/output:/data/output \
  --add-host=host.docker.internal:host-gateway \
  scholar-translate-app:latest \
  /data/input/paper.pdf -o /data/output/paper.md -c config/docker.yaml
```

## 配置

编辑 `config/default.yaml` 自定义行为：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `parser.engine` | pdfplumber | PDF 解析引擎 |
| `chunker.max_tokens` | 2048 | 每块最大 token 数 |
| `chunker.strategy` | sentence | 切块策略: sentence / paragraph / fixed |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.temperature` | 0.3 | 生成温度 |
| `translator.timeout` | 300 | 翻译超时 (秒) |
| `formatter.output_format` | bilingual | 输出格式: bilingual / translated_only / parallel |

## 测试

```bash
pytest tests/ -v
```

## 技术栈

- **PDF 解析**: PyMuPDF, pdfplumber
- **翻译引擎**: Ollama (Qwen3:8b)
- **HTTP 客户端**: httpx
- **容器化**: Docker (多阶段构建, Python 3.12-slim)

## License

[MIT](LICENSE)
