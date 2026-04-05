# Scholar Translate

本地离线英文学术文献智能翻译工具。输入 PDF，自动清洗排版噪声，输出高质量双语对照文档。

## 一键安装桌面端

前往 [Releases 页面](https://github.com/zuowen7/translator/releases) 下载对应平台的安装包：

| 平台 | 文件 |
|------|------|
| Windows | `.msi` 或 `.exe` |
| macOS (Apple Silicon) | `.dmg` |
| macOS (Intel) | `.dmg` |
| Linux | `.AppImage` 或 `.deb` |

安装后还需要安装 [Ollama](https://ollama.com) 并拉取模型：

```bash
ollama pull qwen3:8b
```

然后打开 Scholar Translate 即可使用。

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

- **PDF 智能解析** — 自动检测单栏/双栏布局，准确提取文本
- **文本清洗** — 修复断行、移除水印/页眉页脚、处理连字符断词
- **引用区跳过** — 自动识别 REFERENCES 区域，原样保留不翻译
- **本地翻译** — 基于 Ollama + Qwen3，全程离线，无需 API Key
- **双语逐句对照** — 翻译结果按句配对，支持逐句/段落/全文三种视图
- **日间/夜间模式** — 一键切换亮暗主题，液态玻璃毛玻璃效果
- **自定义背景** — 支持本地图片/视频作为窗口背景，可调节透明度
- **Docker 一键部署** — `docker compose up -d` 即可使用

## 本地开发

```bash
# 安装前端依赖
npm install

# 安装 Ollama 并拉取模型
ollama pull qwen3:8b

# 启动桌面应用（开发模式）
npm run tauri dev

# 构建安装包
npm run tauri build
```

## 发布新版本

```bash
# 打 tag 触发 GitHub Actions 自动构建并发布
git tag v0.3.0
git push origin v0.3.0
```

构建完成后会在 [Releases 页面](https://github.com/zuowen7/translator/releases) 自动生成草稿，点击发布即可。

## 项目结构

```
├── src/                        # Vue 3 前端
├── src-tauri/                  # Tauri 2 桌面端
├── python/
│   ├── api.py                  # FastAPI 服务器
│   ├── src/translator/         # 翻译管道（解析/清洗/切块/翻译/格式化）
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
| `chunker.strategy` | sentence | 切块策略 |
| `translator.model` | qwen3:8b | Ollama 模型 |
| `translator.num_predict` | 16384 | 最大生成 token 数 |
| `translator.temperature` | 0.3 | 生成温度 |
| `formatter.output_format` | bilingual | 输出格式 |

## 技术栈

- **前端**: Vue 3 + TypeScript + Vite + Tauri 2
- **后端**: Python FastAPI + SSE
- **PDF 解析**: pdfplumber
- **翻译引擎**: Ollama (Qwen3)
- **容器化**: Docker 多阶段构建

## License

[MIT](LICENSE)
