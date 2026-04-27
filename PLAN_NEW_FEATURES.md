# Scholar Assistant — 新功能开发方案与任务清单

> 本文档面向**协同 AI**（Claude / Cursor / Copilot Chat 等）。每个任务自带上下文、验收标准、关键路径与可复制的 Prompt 范例，无需再额外读项目即可独立开干。
> 项目根：`D:\pycharm_study\translator`，详细架构见 `CLAUDE.md`。

## 0. 全局上下文（喂给协同 AI 的开场白）

```
项目：Scholar Assistant（Tauri 2 + Vue3 + Python 3.12 FastAPI 后端，本地 Ollama / 18 家云端 LLM）
后端入口：python/api.py + python/api_factory.py（router 模块化在 python/routers/）
翻译管道：parse → clean → chunk → translate → format（SSE 五步）
关键约定：
  - 后端用 sse-starlette 推 SSE，前端用 src/utils/streamReader.ts 解析
  - 路由注册由 api_factory.register_translate/agent/editor/argument 完成
  - 配置走 python/src/config/default.yaml；Docker 模式用 docker.yaml
  - PyInstaller 双目录：BUNDLED_DIR(只读) vs RUNTIME_DIR(可写)
  - Windows httpx 代理 bug：start_dev.bat 已清理 HTTP_PROXY 才能启动
测试：pytest tests/unit/、pytest tests/integration/、npx vitest
请遵循：不引入新依赖前先看 requirements.txt；不破坏 SSE 事件名；保持 register_*(...) 注册风格
```

---

## 1. 任务总览

| # | 任务 | 优先级 | 工作量 | 依赖 | 关联模块 |
|---|------|--------|--------|------|---------|
| T1 | requirements.txt 版本锁定 | P0 | S | 无 | `python/requirements.txt` |
| T2 | MCP Server 配置/启动/测试补完 | P0 | S | 无 | `python/src/agent/mcp_server.py` |
| T3 | 双语 PDF 叠加导出 | P0 | L | parser bbox | `python/src/formatter/`, `python/src/parser/` |
| T4 | 并行翻译 | P1 | M | T1 | `python/routers/translate.py`, `python/src/translator/` |
| T5 | 翻译记忆库 (TM) | P1 | L | 无 | 新增 `python/src/translator/memory_store.py` |
| T6 | 术语锚点系统 | P1 | M | T5 | 改造 `python/src/translator/_helpers.py` + 新增 `glossary_store.py` |
| T7 | App.vue 拆分（2553 → ~500 行） | P1 | L | 无 | `src/App.vue` → 拆出多个 `src/components/*.vue` |

> 顺序建议：T1 → T2 →（T4 与 T5 并行）→ T6 → T3 → T7
> 每完成一项请：1) 跑 `pytest tests/`；2) 提一次独立 commit；3) 更新本文件对应任务的"完成状态"。

---

## T1 · requirements.txt 版本锁定（P0）

### 现状
`python/requirements.txt` 全部使用 `>=`，无锁版本。生产环境不可复现。

### 目标
- 拆为两个文件：`requirements.txt`（直接依赖、`==` 精确锁定）+ `requirements-lock.txt`（含传递依赖的完整快照，`pip-compile` 生成）。
- 保留三个可选 extras：`requirements-ocr.txt`（pytesseract / pdf2image / paddleocr）、`requirements-dev.txt`（pytest/pytest-cov）、`requirements-docs.txt`（如有）。
- CI / Docker 构建改为 `pip install -r requirements-lock.txt`。

### 验收标准
- [ ] `pip install -r requirements-lock.txt` 在干净 venv 下成功，且 `pytest tests/unit/` 全绿。
- [ ] `python api.py` 能起，`/api/health` 返回 200。
- [ ] `Dockerfile` 已切到 lock 文件。
- [ ] README / CLAUDE.md 记录"如何升级依赖"流程（`pip-compile --upgrade-package xxx`）。

### 关键改动
1. 新建 `python/requirements.in`（保留 `>=` 的最低约束）。
2. `pip install pip-tools && pip-compile requirements.in -o requirements-lock.txt --resolver=backtracking`。
3. `requirements.txt` 改为 `==` 精确版本（来自当前能跑通的环境）。
4. `Dockerfile` / `docker-compose.yml`：构建步骤替换。
5. `.github/workflows/*.yml`（如有）同步。

### 给协同 AI 的 Prompt
```
任务：把 python/requirements.txt 从 >= 改为 ==，并产出 requirements-lock.txt。
步骤：
1. 读现有 python/requirements.txt
2. 在 D:\env\anaconda 当前环境下跑 `pip freeze > /tmp/freeze.txt`
3. 对每个直接依赖，用当前已安装版本写为 ==X.Y.Z
4. 用 pip-compile 生成 lock 文件
5. 把 OCR 三件套拆到 requirements-ocr.txt（保持可选）
6. 更新 Dockerfile 安装步骤
约束：不要升级任何包大版本；如果 freeze 里没装某依赖，用 pypi 当前 stable
```

---

## T2 · MCP Server 配置/启动/测试补完（P0）

### 现状
`python/src/agent/mcp_server.py` **已经实现了标准 MCP 协议**：
- 用官方 `mcp` 包的 `Server` + `stdio_server`
- 注册 16 个 Tool（translate_text / parse_document / search_documents / crawl_arxiv / polish_text / summarize_text / generate_outline / expand_section / format_bibliography / 6 个 special_elements 工具）
- `python -m src.agent.mcp_server` 即可拉起

**真正缺失**：客户端接入文档、跨平台启动脚本、stdio 协议级集成测试。

### 目标
让用户开箱即用地从 Claude Desktop / Cursor / Continue 调到本服务器。

### 验收标准
- [ ] 新增 `docs/mcp/README.md`（中英双语片段），含三段配置 JSON：
  - Claude Desktop（macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`；Windows：`%APPDATA%\Claude\claude_desktop_config.json`）
  - Cursor（`~/.cursor/mcp.json`）
  - Continue（`~/.continue/config.json`）
- [ ] 新增 `python/scripts/run_mcp_server.bat` 与 `run_mcp_server.sh`，处理：
  - 设置 `PYTHONPATH=python/src`
  - 清空 `HTTP_PROXY`（Windows httpx bug）
  - 透传 `OLLAMA_BASE_URL` / `CLOUD_API_KEY` 等环境变量
- [ ] 新增 `python/tests/integration/test_mcp_server.py`：用 `mcp` 客户端 SDK 启 stdio 子进程，调用 `list_tools` 与 `translate_text`，断言返回非空。
- [ ] 在 `mcp_server.py` 顶部注释加上"如何接入"指引（指向 `docs/mcp/README.md`）。

### 配置 JSON 模板（直接抄进文档）
```jsonc
// claude_desktop_config.json
{
  "mcpServers": {
    "scholar-assistant": {
      "command": "D:\\env\\anaconda\\python.exe",
      "args": ["-m", "src.agent.mcp_server"],
      "cwd": "D:\\pycharm_study\\translator\\python",
      "env": {
        "PYTHONPATH": "D:\\pycharm_study\\translator\\python",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "qwen3:8b",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": ""
      }
    }
  }
}
```

### 给协同 AI 的 Prompt
```
任务：补完 MCP Server 的接入闭环（协议本身已实现）。
读：python/src/agent/mcp_server.py（看 SERVER_NAME / 16 个 Tool / main()）
做：
1. 创建 docs/mcp/README.md，包含 Claude Desktop / Cursor / Continue 三套配置 JSON
2. 创建 python/scripts/run_mcp_server.{bat,sh}，要清空 HTTP_PROXY
3. 创建 python/tests/integration/test_mcp_server.py
   - 用 stdio_client 启 subprocess
   - 断言 list_tools 返回 >= 16 个工具
   - 断言 translate_text("Hello") 返回非空字符串（mock 或跳过 LLM 调用）
约束：不动 mcp_server.py 现有逻辑；测试用 pytest mark "integration"，默认不在 unit 里跑
```

---

## T3 · 双语 PDF 叠加导出（P0）

### 现状
`python/src/formatter/` 只有 `renderer.py`（单语 PDF/LaTeX）和 `word_exporter.py`，无叠加模块；`python/src/parser/` 提取纯文本，**未保留 bbox 坐标**。

### 目标
"沉浸式翻译"风格的 PDF：保留原 PDF 排版，把每段译文以可读字号叠在原文下方/上方（用户可选）。导出后下载一个新 PDF。

### 设计要点

#### 3.1 Parser 改造（保留坐标）
- `python/src/parser/pdf_parser.py`：用 `fitz.Page.get_text("dict")` 取出 `blocks → lines → spans` 的 bbox。
- 数据结构（新增到 `python/src/parser/models.py` 或现有 `Document`）：
  ```python
  @dataclass
  class TextBlock:
      page: int           # 页码（0-indexed）
      bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
      text: str
      font_size: float
      block_id: str       # 稳定 hash，用于翻译完后回填
  ```
- `extract_document_with_layout(path) -> tuple[Document, list[TextBlock]]` 作为新 API（**不破坏**现有 `extract_document`）。

#### 3.2 翻译阶段对齐
- 用 `block_id` 当 chunk key，翻译结果以 `dict[block_id, str]` 形式回收。
- 顺序与原 chunker 兼容：将多个 TextBlock 合并为段落级 chunk 喂 LLM，再按 block_id 把译文切回去（按字符比例分配）。

#### 3.3 PDF 叠加渲染
- 新建 `python/src/formatter/pdf_overlay.py`：
  ```python
  def overlay_translation(
      src_pdf: str | Path,
      blocks: list[TextBlock],
      translations: dict[str, str],
      output: str | Path,
      mode: Literal["below", "above", "replace"] = "below",
      font_path: str | None = None,  # CJK 字体，默认用 assets/NotoSansCJK-Regular.otf
  ) -> Path
  ```
- 实现：用 `fitz.open(src_pdf)` 复制原 PDF；对每个 block 按 mode 处理：
  - `below`：在原 bbox 下方插入 `insert_textbox`，自动调小字号确保不溢出
  - `above`：原 bbox 上方加白底 + 译文
  - `replace`：用 `add_redact_annot` 涂掉原文 + 同位置插入译文
- **CJK 字体**：项目里 bundle 一个开源 CJK 字体（`python/assets/fonts/NotoSansCJK-Regular.otf`，或 SourceHanSans）。`font_path` 默认指向它。

#### 3.4 路由暴露
- `python/routers/editor.py` 或 `translate.py` 新增：
  ```
  POST /api/export/bilingual_pdf
  body: { task_id: str, mode: "below" | "above" | "replace" }
  resp: 二进制 PDF 流（Content-Type: application/pdf）
  ```
- 翻译完成后，前端在导出按钮里加"双语 PDF（叠加）"选项（暂不要求 UI 拆分配合，按钮加在现有导出菜单即可）。

### 验收标准
- [ ] `pytest tests/unit/test_pdf_overlay.py`：用一个 1 页测试 PDF，断言输出 PDF 页数相同、文件大小 > 原文件、能用 PyMuPDF 重新打开。
- [ ] 手测：拿真实 arXiv 论文导出一份"below"模式 PDF，中文字符不出现 ▯ 或裁切。
- [ ] 不影响现有 `extract_document` 调用方（`routers/agent.py`、CLI 等）。

### 给协同 AI 的 Prompt
```
任务：实现"沉浸式翻译"风格的双语 PDF 叠加导出。
读：
- python/src/parser/pdf_parser.py（理解 PyMuPDF 用法）
- python/src/formatter/renderer.py（理解输出风格）
- python/routers/translate.py（理解 SSE chunk_done 事件，里面有 chunks）
做：
1. 新增 extract_document_with_layout()，保留每个 TextBlock 的 bbox + block_id（不破坏老 API）
2. 改造 chunker：保留 block_id ↔ chunk 映射
3. 新建 python/src/formatter/pdf_overlay.py，实现 overlay_translation()
4. 在 python/assets/fonts/ 放 NotoSansCJK-Regular.otf（让用户用 ! curl 下载）
5. routers/translate.py 新增 POST /api/export/bilingual_pdf
6. tests/unit/test_pdf_overlay.py：用 1 页测试 PDF 跑端到端
约束：用 PyMuPDF 已有依赖，不要新增 reportlab；译文塞不下时自动缩字号到最小 6pt
```

---

## T4 · 并行翻译（P1，依赖 T1）

### 现状
`python/routers/translate.py:311` 是 `for i, chunk in enumerate(chunk_result.chunks): ... await translate(chunk)`，**严格串行**。一篇 30 chunk 的论文要等 30 次 LLM 往返。

### 目标
按可配置并发度并行翻译（默认 4），保持 SSE `chunk_done` 事件**按 chunk index 顺序**推送给前端，且术语注入逻辑（`_extract_term_pairs`）仍生效（见 T6）。

### 设计要点

#### 4.1 调度器
- 新建 `python/src/translator/parallel_runner.py`：
  ```python
  async def translate_chunks_parallel(
      chunks: list[Chunk],
      translate_fn: Callable[[Chunk, dict], Awaitable[TranslateResult]],
      *,
      concurrency: int = 4,
      glossary: dict[str, str] | None = None,
      on_done: Callable[[int, TranslateResult], Awaitable[None]] | None = None,
  ) -> list[TranslateResult]
  ```
- 实现：`asyncio.Semaphore(concurrency)` + `asyncio.create_task` + `as_completed`；用 buffer 排序，`on_done(idx, result)` 在 idx 等于"下一个待发送的索引"时立即推 SSE，否则缓存。

#### 4.2 配置
- `python/src/config/default.yaml` 新增：
  ```yaml
  translator:
    parallel:
      enabled: true
      max_concurrency: 4   # 本地 Ollama 建议 1-2，云端 4-8
      preserve_order: true # 保证 SSE 事件顺序
  ```
- 当 `max_concurrency=1` 时退化为现有串行逻辑（保留 fallback 路径）。

#### 4.3 术语注入兼容（与 T6 衔接）
- 串行版逻辑是"前 N 个 chunk 提取的术语对，注入到 N+1 chunk 的 prompt"。并行下这条链断了。**临时方案**：
  - 第一阶段：先并行所有 chunk（不带 glossary），收集所有术语对
  - 第二阶段：发现术语冲突时回译有问题的 chunk
- 完整方案见 T6（先建术语库，再翻译）。

#### 4.4 速率与失败
- 引入 `tenacity` 或自写指数退避（云端 429 / 502 重试 3 次）。
- 单 chunk 失败时：用占位 `[翻译失败: 原文片段]` 落位，不阻塞整体。
- SSE 增加事件 `chunk_failed`（前端可重试单 chunk）。

### 验收标准
- [ ] 单测：mock LLM 客户端（每次延迟 100ms），10 chunk 在 concurrency=4 下耗时 < 350ms（理论 250ms+开销）。
- [ ] SSE 事件 `chunk_done` 顺序严格 0,1,2,3...n（即使内部完成顺序乱）。
- [ ] `max_concurrency=1` 行为与改造前完全一致（回归）。
- [ ] 端到端：10 页论文用云端 API，并发 4 比串行快 ≥ 2.5 倍。

### 给协同 AI 的 Prompt
```
任务：让 routers/translate.py 的 chunk 翻译循环并行化。
读：
- python/routers/translate.py（特别是 register_translate 内 for i, chunk in enumerate(...) 那段）
- python/src/translator/_helpers.py（理解术语对注入）
做：
1. 新建 python/src/translator/parallel_runner.py，实现 translate_chunks_parallel()
2. 改造 routers/translate.py：用 parallel_runner 替换串行循环，但保留 SSE 事件名和顺序
3. config/default.yaml 加 translator.parallel.* 段
4. 加单测 tests/unit/test_parallel_runner.py（mock LLM 验证并发数和顺序）
约束：
- 不改 SSE 事件名（progress / parsed / cleaned / chunked / chunk_done / complete）
- chunk_done 必须按 index 顺序推（即使乱序完成）
- max_concurrency=1 必须等价旧逻辑
- 暂不接 T6 术语锚点，先用现有 _extract_term_pairs（接受第一遍质量略降）
```

---

## T5 · 翻译记忆库 TM（P1）

### 现状
完全没有跨任务复用机制。同一句话翻译两次、改一个字重译，都要重新调 LLM。`agent/memory.py` 是 Agent 对话记忆，**与 TM 无关**。

### 目标
SQLite + 句向量索引的本地翻译记忆库。命中精确匹配 / 高相似度（≥0.92）时直接复用译文，否则把"相似度 0.7~0.92"的历史译文作为 few-shot 注入 prompt。

### 设计要点

#### 5.1 存储
- 新建 `python/src/translator/memory_store.py`：
  ```python
  class TranslationMemory:
      def __init__(self, db_path: Path, embedder: Embedder | None = None): ...
      def add(self, source: str, target: str, *, lang_pair: str = "en-zh", meta: dict | None = None): ...
      def lookup_exact(self, source: str, lang_pair: str = "en-zh") -> str | None: ...
      def lookup_fuzzy(self, source: str, *, top_k: int = 3, min_score: float = 0.7) -> list[TMHit]: ...
      def stats(self) -> dict: ...
  ```
- SQLite schema：
  ```sql
  CREATE TABLE tm_entries (
    id INTEGER PRIMARY KEY,
    source_hash TEXT UNIQUE,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    lang_pair TEXT NOT NULL,
    embedding BLOB,            -- numpy float32, 384 维
    meta_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_count INTEGER DEFAULT 0
  );
  CREATE INDEX idx_tm_lang ON tm_entries(lang_pair);
  ```
- Embedding 复用项目已用的 `all-MiniLM-L6-v2`（chromadb 体内已有，但 TM 不要直接进 chroma，避免和 RAG 混用 collection）。
- 文件位置：`python/data/translator/tm.db`（运行时目录，PyInstaller 友好）。

#### 5.2 接入翻译流
- `routers/translate.py` 在每个 chunk 翻译前：
  1. `lookup_exact` 命中 → 直接发 SSE，不调 LLM
  2. `lookup_fuzzy` 命中 → 把 top 3 拼成 few-shot 加进 prompt
  3. 翻译完成后 `tm.add(source, target)`
- 加 SSE 事件 `chunk_tm_hit`（前端可显示"♻️ 来自记忆库"标记）。

#### 5.3 管理 API
- `GET /api/tm/stats`、`POST /api/tm/import`（TMX 1.4b 标准格式）、`POST /api/tm/export`、`DELETE /api/tm/entry/{id}`。
- 用户能在前端看到："本次翻译命中 X 条 / 节省 ~Y 秒"。

### 验收标准
- [ ] 单测：相同句子第二次翻译，调用 LLM 次数为 0。
- [ ] 单测：编辑距离 1 的句子能模糊命中（fuzzy）。
- [ ] TMX 导入/导出可与 OmegaT 互通（用现成 TMX 文件验证）。
- [ ] PyInstaller 打包后 `tm.db` 位于 RUNTIME_DIR 而非 BUNDLED_DIR。

### 给协同 AI 的 Prompt
```
任务：实现翻译记忆库（TM），与翻译管道集成。
读：
- python/routers/translate.py（理解 chunk 循环位置）
- python/src/agent/rag.py（参考 ChromaDB / embedding 使用方式，但 TM 不复用 chroma）
- CLAUDE.md 里 BUNDLED_DIR vs RUNTIME_DIR 的约定
做：
1. python/src/translator/memory_store.py — TranslationMemory 类（SQLite + numpy embeddings）
2. python/routers/translate.py — chunk 翻译前查 TM，翻译后写 TM；加 SSE chunk_tm_hit 事件
3. python/routers/translate.py — 新增 /api/tm/stats、/api/tm/import、/api/tm/export 路由
4. tests/unit/test_translation_memory.py — 精确/模糊匹配、TMX 导入导出
约束：
- embedding 用现有 sentence-transformers all-MiniLM-L6-v2，不新增大模型
- DB 路径必须用 RUNTIME_DIR（看 api_factory.py 怎么拿）
- TMX 导出要 standard-compliant，能被 OmegaT 读取
```

---

## T6 · 术语锚点系统（P1，依赖 T5）

### 现状
`python/src/translator/_helpers.py:38` 的 `_extract_term_pairs` 是**事后**从已翻译文本里正则提取 `中文(English)` 模式的术语对，再注入下个 chunk 的 prompt。问题：
- 不保证一致性：同一个 "transformer" 第 3 chunk 译"变换器"、第 7 chunk 译"转换器"，提取不出冲突
- 不可干预：用户无法预设"BERT 不要翻译"或"attention 必须译为'注意力机制'"
- 与并行翻译（T4）天然冲突

### 目标
带"锚点"的术语库：
1. 用户可预定义术语表（YAML / 前端 UI）
2. 翻译前：扫原文 → 命中锚点术语 → 在 prompt 加硬约束 "必须把 X 译为 Y / 保留 X 不翻译"
3. 翻译后：自动校验（术语未按约定出现就标黄并自动修正）
4. 自动学习：高频未登录术语在翻译完后弹"是否加入术语库"

### 设计要点

#### 6.1 术语库
- 新建 `python/src/translator/glossary_store.py`：
  ```python
  @dataclass
  class GlossaryEntry:
      source: str           # 原文术语（不区分大小写匹配，但保留原 case）
      target: str           # 译文（"" 表示保留不翻译）
      case_sensitive: bool = False
      whole_word: bool = True
      domain: str = "default"
      locked: bool = False  # locked=true 时强制校验+修正

  class Glossary:
      def load(self, path: Path | str) -> None: ...
      def save(self, path: Path | str) -> None: ...
      def match(self, source_text: str) -> list[GlossaryEntry]: ...
      def enforce(self, source: str, translated: str) -> tuple[str, list[Violation]]: ...
  ```
- 文件格式（YAML 简单优先）：
  ```yaml
  domain: ml
  entries:
    - {source: BERT, target: ""}             # 保留
    - {source: attention, target: 注意力机制, locked: true}
    - {source: transformer, target: Transformer, case_sensitive: true}
  ```
- 默认词表：`python/data/translator/glossaries/ml.yaml`、`bio.yaml`、`law.yaml`（每个先放 30~50 条种子）。

#### 6.2 翻译前 prompt 注入
- 改 `python/src/translator/_helpers.py`，新增 `build_glossary_prompt(matched_entries) -> str`：
  ```
  ## 术语约束（必须严格遵守）
  - "attention" 必须译为「注意力机制」
  - "BERT" 保留原文不翻译
  - "Transformer" 保留原文（注意大小写）
  ```
- 注入到 user prompt 顶部。

#### 6.3 翻译后校验 + 自动修正
- `Glossary.enforce(source, translated)` 检查每条 locked 术语：原文出现 N 次 → 译文应有对应术语 N 次。
- 不匹配时尝试简单替换；替换失败则发 SSE 事件 `glossary_violation` 让前端高亮。

#### 6.4 与 TM (T5) 协作
- TM 命中后也走一遍 `enforce`（避免老 TM 不符合新术语表）。

#### 6.5 路由 / 前端
- `GET /api/glossary`、`PUT /api/glossary`、`POST /api/glossary/import`（CSV / TBX）
- 前端：T7 拆分后在设置面板加"术语管理"标签（先做后端 + 简陋 UI 即可）

### 验收标准
- [ ] 单测：同一原文连续 5 chunk 都含 "attention"，全部译成"注意力机制"，0 次"注意"或"关注"。
- [ ] 单测：标了 `target=""` 的 "BERT" 在译文里原样出现。
- [ ] 单测：CSV / TBX 导入导出可用。
- [ ] 与 T4 并行翻译协作：4 并发下术语一致性仍 100%。

### 给协同 AI 的 Prompt
```
任务：实现术语锚点系统，覆盖现有 _extract_term_pairs 的临时方案。
读：
- python/src/translator/_helpers.py（看现有 _extract_term_pairs）
- python/routers/translate.py（看 prompt 怎么拼的，glossary 注入点在哪）
- 如果 T5 已完成：python/src/translator/memory_store.py
做：
1. python/src/translator/glossary_store.py — Glossary + GlossaryEntry
2. python/data/translator/glossaries/ml.yaml — 种子词表（30-50 条 ML 术语）
3. python/src/translator/_helpers.py — 加 build_glossary_prompt()，并保留旧 _extract_term_pairs 作为兜底学习
4. python/routers/translate.py — 翻译前注入约束，翻译后调 enforce()，违反时发 SSE glossary_violation
5. 路由 GET/PUT /api/glossary、POST /api/glossary/import（CSV+TBX）
6. tests/unit/test_glossary.py — 一致性、保留不翻译、locked 强制
约束：
- 不删 _extract_term_pairs（它现在仍在用），但其结果只作为"建议"而非强制
- locked 术语必须 100% 一致；非 locked 仅作建议
- 与 T4 并行翻译兼容：所有 chunk 共享同一份 Glossary 引用
```

---

## T7 · App.vue 拆分（P1）

### 现状
`src/App.vue` 已经 **2553 行**（比上次记录的 2342 还多 211 行）。模板里至少包含：
- 顶栏 / 模式切换 / 引擎设置面板 / 全局设置面板
- 拖拽遮罩 / 翻译模式主区 / 编辑器模式入口
- 视频背景 / 内容遮罩

### 目标
App.vue 降到 ≤ 500 行，**只负责布局组合 + 全局状态注入**。所有面板/区块抽成独立 SFC。

### 拆分方案

| 抽出组件 | 职责 | 大致行数 |
|---------|------|---------|
| `components/AppTopbar.vue` | 顶栏（含 brand + 模式切换 + 设置按钮组） | ~250 |
| `components/EngineSettingsPanel.vue` | 翻译引擎选择 + 云端配置（Ollama / 18 家云端） | ~400 |
| `components/AppSettingsPanel.vue` | 主题 / 背景 / 通用设置 | ~300 |
| `components/BackgroundLayer.vue` | 视频/图片背景层 + 遮罩 | ~120 |
| `components/DragOverlay.vue` | 全局拖拽遮罩 | ~60 |
| `components/TranslateView.vue` | 翻译模式主区（提取自原 App.vue 中段） | ~600 |
| `composables/useEngineConfig.ts` | 引擎/云端配置的状态 + 持久化 | ~200 |
| `composables/useBackground.ts` | 背景图/视频选择 + 持久化 | ~150 |
| `composables/useAppSettings.ts` | 通用设置（主题等） | ~100 |
| **App.vue（保留）** | 布局骨架、模式切换、组件组合 | **≤ 500** |

### 拆分纪律（一定要给协同 AI 强调）
- **一次只拆一块、一次只提交一个 commit**：先 Topbar，再 EngineSettings，每拆一个跑一次 `npx vitest`。
- **状态用 composable 集中管理**：避免子组件大量 props/emits。Engine / Background / AppSettings 三个 composable 都做成"模块级单例"（参照 `useTranslate.ts` 风格）。
- **样式同步迁移**：每个组件带自己的 `<style scoped>`，从 App.vue 的 `<style>` 段精确剪走相关选择器。
- **不引入新功能**：纯重构，不改任何用户可见行为。
- **保留全局拖拽**：`@drop` 必须仍挂在 App.vue 根 div（否则失效）。

### 验收标准
- [ ] App.vue ≤ 500 行
- [ ] `npm run dev` 启动后所有现有功能（翻译/编辑器切换/引擎设置/背景设置/拖拽上传）行为一致
- [ ] `npx vitest` 全绿
- [ ] 拆出的每个 SFC < 500 行
- [ ] Lighthouse / Vue DevTools 看不到额外重渲染回归

### 给协同 AI 的 Prompt（建议拆 7 次、每次发一个）
```
任务：从 src/App.vue 抽出 AppTopbar.vue（其它部分不动）。
读：src/App.vue 第 1-300 行（template 顶栏部分）+ 对应 <script setup> 中的引擎/设置按钮状态
做：
1. 创建 src/components/AppTopbar.vue
2. 移走顶栏 template + 相关 <style>
3. 用 props/emits 暴露：appMode, isDark, 各 panel 的 open 状态切换事件
4. App.vue 用 <AppTopbar v-model:app-mode="appMode" ... />
约束：
- 纯重构，0 行为变化
- 拆完跑 `npx vitest` 必须全绿
- 不要顺手"优化"任何逻辑（保留醒目代码异味，下次再处理）
- 完成后报告：App.vue 减少了多少行，新文件多少行
```
（其余 6 块同模板替换组件名即可）

---

## 9. 协同流程建议

1. **每个任务一个分支**：`feat/req-lock`、`feat/mcp-docs`、`feat/pdf-overlay` ...
2. **协同 AI 必须先读 CLAUDE.md 与本文件 § 0**（喂进它的 system prompt）
3. **每个 PR 必带**：
   - 改动文件清单
   - `pytest tests/unit/` 输出
   - 影响的 SSE 事件 / API 路由列表
   - 是否变更 `requirements.txt`
4. **冲突高风险点**：
   - T4 (并行翻译) 与 T6 (术语锚点) 都改 `routers/translate.py`，**不要并行做**，T4 先合并
   - T5 / T6 都加新 SSE 事件，要在 `src/utils/streamReader.ts` 类型定义里同步
5. **回归测试金标准**：备好一篇 5 页 arXiv PDF（建议 `attention-is-all-you-need.pdf`），每个任务完成后跑一遍端到端翻译，确认**译文质量未退化**（眼测）。

---

## 10. 进度追踪

请在每个任务完成后更新这一节（PR 合并日期 + commit hash）：

- [x] T1 requirements 锁定 — `a668b02` + `d34096b` + `f962066`；`requirements-dev.txt` 已分离测试依赖
- [x] T2 MCP 文档/脚本/测试 — `3f4835f`；`docs/mcp/README.md` + 两套启动脚本 + 集成测试
- [x] T3 双语 PDF 叠加 — 见当前 commit；`pdf_overlay.py` + `extract_document_with_layout` + `/api/export/bilingual_pdf`；测试改为动态生成 PDF（10 passed）
- [x] T4 并行翻译 — `9f6de99`；`parallel_runner.py` Semaphore + 顺序 yield；SSE 事件名为 `chunk_error`（前端已对齐）
- [x] T5 翻译记忆库 — `56a619e`；`memory_store.py` SQLite + embedding（sentence-transformers 可选，缺失时降级为精确匹配）；TMX 导入导出；`/api/tm/*` 路由
- [x] T6 术语锚点系统 — `9e70ba5`；`glossary_store.py` + `ml.yaml` 种子词表；CSV/TBX 导入导出；`glossary_violation` SSE 事件；`/api/glossary` 路由
- [ ] T7 App.vue 拆分 — _暂不做_
