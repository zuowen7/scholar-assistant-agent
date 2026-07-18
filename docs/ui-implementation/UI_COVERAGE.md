# 研墨生产前端 UI 覆盖矩阵

分支：`refactor/reference-driven-ui`

最后更新：2026-07-18（持续适配中）

状态仅允许：`FULLY_ADAPTED`、`PARTIALLY_ADAPTED`、`SHELL_ONLY`、`UNTOUCHED`、`VISUALLY_BROKEN`、`NOT_REACHABLE`。

`FULLY_ADAPTED` 的门槛：真实生产入口可达、真实数据或真实 API 已验证、主要交互已走通，并完成 1440×900、1200×800、1024×768、200% 缩放、深色和中英文检查。仅复用 AppShell 或 Token 不算完成。

## 1. 全局框架与启动

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 主窗口 AppShell、统一导航、窗口控制 | PARTIALLY_ADAPTED | 四个核心页面已实机检查；浅色无边框窗口已在 1440×900 Tauri 实机确认 | 覆盖全部模式、焦点与多尺寸 |
| 启动加载 InkBrushLoader | UNTOUCHED | 仍为旧视觉 | 适配加载、超时与后端启动失败 |
| 全局拖放 PDF 遮罩 | UNTOUCHED | 仍为旧 drag-card / drag-ring | 改为参考图语言并检查 Tauri 拖放 |
| 翻译恢复 Banner | PARTIALLY_ADAPTED | 功能仍在，未做深色/长文/操作验收 | 真实恢复与丢弃验证 |
| Toast 成功/错误/警告 | SHELL_ONLY | 读取了新 Token，布局和语义未统一验收 | 适配并触发全部状态 |
| 深色模式 | PARTIALLY_ADAPTED | 新 Token 有暗色变量；大量旧组件未检查 | 全入口暗色截图与对比 |
| 中文界面 | PARTIALLY_ADAPTED | 原 i18n 在；新增组件存在硬编码中文 | 新增文案进入 i18n 并全入口检查 |
| 英文界面 | VISUALLY_BROKEN | 新 Shell/Reviewer/任务面板存在硬编码中文 | 补齐 i18n、检查溢出与长文本 |
| 100%–200% WebView 缩放 | PARTIALLY_ADAPTED | 写作页已验证，其他生产入口未验证 | 全入口缩放检查 |
| 键盘焦点、Escape 与 reduced-motion | UNTOUCHED | 未全局审计 | 建立统一焦点/弹窗行为 |

## 2. 首页与项目旅程

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 欢迎页 / 最近项目 | PARTIALLY_ADAPTED | 暖白视觉已出现，未完成深色/英文/错误验收 | 统一 Shell、状态、响应式 |
| 新建工程 | UNTOUCHED | `EditorNewProject.vue` 旧视觉 | 真实创建、校验、失败与成功路径 |
| 从模板新建 | UNTOUCHED | `TemplatePicker.vue` 旧视觉 | 接入统一弹窗并真实生成 |
| 打开文件夹 | PARTIALLY_ADAPTED | 可用，Tauri 选择器已走通 | 取消、权限、长路径、错误状态 |
| 最近项目打开 | PARTIALLY_ADAPTED | 项目 6 已真实打开 | 加载/不存在/删除最近项 |
| 项目关闭与返回欢迎页 | NOT_REACHABLE | 原入口位于不再渲染的 AppTopBar | 在新 Shell 恢复等价入口 |
| 项目类型检测与恢复 | UNTOUCHED | API 在，未做新 UI 验收 | 真实检测/恢复状态 |

## 3. 翻译旅程

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 翻译首页 / 上传区 | SHELL_ONLY | 仅套新侧栏，主体仍为旧版 | 重构为参考图工作台 |
| PDF / DOCX / TXT / Markdown 选择与拖放 | UNTOUCHED | 真实链路在，未检查新 UI | 多格式真实选择与校验 |
| 翻译引擎与模型选择 | UNTOUCHED | 旧控件 | 统一控件、真实 Provider 状态 |
| 翻译进度五阶段 | UNTOUCHED | SSE 功能在，视觉仍旧 | 状态层级、取消、恢复 |
| 块级失败与重试 | UNTOUCHED | `retry_block` 链路在 | 制造真实失败并重试 |
| 术语警告 / QA 警告 | UNTOUCHED | SSE 状态在 | 长列表、无警告、错误状态 |
| 双栏阅读 | UNTOUCHED | 功能在，旧布局 | 重构比例、滚动同步、阅读设置 |
| 翻译结果筛选 / 搜索 | UNTOUCHED | 未验收 | 真实长文检查 |
| 双语 Word 导出 | UNTOUCHED | API 在 | 真实导出和失败状态 |
| 译文 Word 导出 | UNTOUCHED | API 在 | 真实导出和失败状态 |
| PPTX / Data Availability 导出 | UNTOUCHED | API 在 | 真实导出和反馈 |

## 4. 写作、LaTeX 与编辑器

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| Markdown 写作工作区 | PARTIALLY_ADAPTED | 1440/1200/1024/200% 已检查 | 深色、英文、选择工具条和错误路径 |
| LaTeX 编辑器 | PARTIALLY_ADAPTED | 真实 `neurips.tex` 已打开并修复脏状态误报 | 编辑、保存、深色、英文、长路径 |
| 文件树 | PARTIALLY_ADAPTED | 真实目录与文件已打开 | 新建/重命名/删除/复制/错误/确认 |
| 标签页与脏状态 | PARTIALLY_ADAPTED | 打开即脏问题已修复 | 多标签、关闭脏文件、键盘导航 |
| 编辑器工具栏 | SHELL_ONLY | 读取 Token，仍有旧图标密度 | 全动作入口与 Tooltip |
| 正文 / 大纲 / 预览 | PARTIALLY_ADAPTED | 三态入口在，未全交互验收 | Markdown 预览、滚动与长文 |
| 选择文本浮动工具条 | PARTIALLY_ADAPTED | 接真实 Agent，未做实机任务验收 | 真实润色/扩写/审查 |
| AI 编辑 `/api/edit` | PARTIALLY_ADAPTED | 真实入口保留 | 润色/扩写/重写/翻译/停止/失败 |
| 合规检查 | UNTOUCHED | `ComplianceModal.vue` 旧视觉 | 真实检查、结果、关闭与错误 |
| 图片 / Vision / OCR / Chart / Table | UNTOUCHED | API 与旧工具入口在 | 真实图片、权限、失败与插入 |
| 引用索引与提取 | UNTOUCHED | API 在 | 真实文稿、空结果与错误 |
| Zotero 状态、搜索与插入 | UNTOUCHED | API 在 | 未连接、连接、搜索与导出 |
| Ghost Text / 完成建议 | UNTOUCHED | 功能与测试在 | 真实输入、接受、取消、错误 |

## 5. Agent V2

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 写作页任务式 Agent | PARTIALLY_ADAPTED | 接 Agent V2 真状态；未完整任务验收 | 真实任务、步骤、审批与结果 |
| 全局 Agent 主面板 | UNTOUCHED | 仍为旧聊天式视觉 | 重构为任务流，保留会话能力 |
| Agent 独立窗口 | UNTOUCHED | 生产入口在，未适配 Shell/窗口 | 真实打开、关闭、恢复与多尺寸 |
| 会话列表与恢复 | UNTOUCHED | API 与组件在 | 真实会话恢复、空/错状态 |
| 工具调用过程 | UNTOUCHED | SSE 在 | 长参数、结果、错误与折叠 |
| 审批 allow once / session / deny | UNTOUCHED | 链路与测试在 | 真实审批、强制审批、失败 |
| Inline Diff 接受 / 拒绝 | UNTOUCHED | Monaco 链路在 | 真实 `str_replace` / `write_file` |
| checkpoint 与文件刷新 | UNTOUCHED | 链路在 | dirty tab 保护与刷新反馈 |
| 附件、RAG 文档与 @ 引用 | UNTOUCHED | 功能在 | 真实上传、删除、引用和错误 |
| 中止、恢复与结果 | UNTOUCHED | API 在 | 真实中止/恢复/超时 |

## 6. 思考、论证与审稿

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 思维导图画布 | PARTIALLY_ADAPTED | 37 个真实节点已实机检查 | 节点编辑、深色、英文、多尺寸 |
| 自动布局 / fit / 缩放 / 缩略图 | PARTIALLY_ADAPTED | 实际操作通过 | 极端节点数与恢复状态 |
| AI 扩展 | PARTIALLY_ADAPTED | 入口保留，未做本轮真实调用 | 真实扩展、取消与失败 |
| 节点属性、浮动工具条、AI 提示 | PARTIALLY_ADAPTED | 1440×900 Tauri 已恢复默认可见；Tab 新建、Ctrl+Z 撤销通过；DeepSeek `/api/mindmap/analyze` 实际返回 200 与中文审查意见 | 深色、英文、1024×768 与 200% 缩放 |
| Reviewer-2 | PARTIALLY_ADAPTED | 顶部固定生产入口已恢复；Reviewer-2 / AC / 领域专家 / 友好评审和串并行模式可选；此前 DeepSeek 实际生成 12 条批评 | 恢复、深色、英文、长文本与错误 |
| 真实评审导入 | PARTIALLY_ADAPTED | 入口在，未实机导入 | 真实文本导入与解析失败 |
| Claim Ledger | PARTIALLY_ADAPTED | “承诺兑付 · Claim Ledger”独立入口与完整真实台账已恢复；真实建立并显示主张 | 编辑/删除/重定位/错误 |
| rebuttal | PARTIALLY_ADAPTED | 真实链路在，未本轮提交回应 | 提交、失败、状态更新 |
| Argument Map 主画布 | PARTIALLY_ADAPTED | 审稿区固定入口已恢复；真实图数据、自动布局、新建图和节点编辑链路保留 | 深色、英文、极端图规模与 Inspector 验收 |
| Argument Map 提取/批评/建议/扁平化 | UNTOUCHED | API 在 | 逐项真实验收 |
| Companion 旧面板 / LedgerList | UNTOUCHED | 仍可由旧路径触达 | 统一视觉或替换为等价新入口 |

## 7. 设置与系统能力

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 设置中心入口 | NOT_REACHABLE | 新侧栏齿轮事件无人监听 | 建立新设置中心 |
| Provider 选择 / API Key / Base URL / Model | NOT_REACHABLE | 原控件只存在于未渲染 AppTopBar | 恢复真实配置、确认与连接测试 |
| Ollama 模型 / 刷新 / 启动状态 | NOT_REACHABLE | 原控件不可达 | 恢复真实状态与操作 |
| Tectonic 状态 / 安装 | NOT_REACHABLE | 原控件不可达 | 恢复安装与错误反馈 |
| HTTP 代理 | NOT_REACHABLE | 原控件不可达 | 恢复配置、确认与反馈 |
| 阅读字体 / 行距 / 译文颜色 | NOT_REACHABLE | 原控件不可达 | 恢复并实时预览 |
| 自定义背景 / 透明度 | NOT_REACHABLE | 原控件不可达 | 恢复选择、清除和错误 |
| 主题切换 | NOT_REACHABLE | 语音事件可触发，UI 按钮缺失 | 在设置与用户区恢复 |
| 语言切换 | NOT_REACHABLE | 原控件不可达 | 在设置中心恢复中英文切换 |
| 语音开关 / 热键 / 唤醒词 / 灵敏度 | NOT_REACHABLE | 原控件不可达 | 恢复真实配置与支持状态 |
| 服务状态总览 | SHELL_ONLY | 仅有简化 ModelStatus | 增加按需详情，不占主界面 |
| Debug 面板 | NOT_REACHABLE | 原入口位于未渲染 AppTopBar | 明确生产可达性并适配或移除生产入口 |
| 更新检查 | NOT_REACHABLE | 启动逻辑在，无明显用户入口 | 恢复状态与反馈 |

## 8. 输出、弹窗与全局边界状态

| 入口 / 状态 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| Markdown 保存 | PARTIALLY_ADAPTED | 真实保存可用 | 失败、冲突与 dirty tab |
| Word 导出 | UNTOUCHED | API 在 | 真实导出与反馈 |
| LaTeX 导出 | UNTOUCHED | API 在 | 模板、真实导出与错误 |
| PDF 导出 | UNTOUCHED | API 在 | Tectonic 缺失、安装、导出 |
| 论文模板 / 新建论文 | UNTOUCHED | `TemplatePicker.vue` 旧视觉 | 真实模板与脚手架 |
| 合规弹窗 | UNTOUCHED | 旧视觉 | 统一 Dialog |
| Command Palette | UNTOUCHED | 旧视觉 | 键盘、位置、加载与错误 |
| 文件删除 / 覆盖确认 | UNTOUCHED | 浏览器 confirm/prompt 痕迹待审计 | 统一确认框且不破坏文件安全 |
| 空状态 | PARTIALLY_ADAPTED | 新旧 Empty 混用 | 收敛到统一组件 |
| 加载 / Skeleton | SHELL_ONLY | 基础组件在，页面未统一 | 逐旅程适配 |
| API 错误 / 后端离线 | UNTOUCHED | 多处各自处理 | 统一错误语言与恢复动作 |
| 权限 / 审批错误 | UNTOUCHED | Agent 路径存在 | 实际拒绝与失败反馈 |

## 初始统计

| 状态 | 数量 |
| --- | ---: |
| FULLY_ADAPTED | 0 |
| PARTIALLY_ADAPTED | 25 |
| SHELL_ONLY | 5 |
| UNTOUCHED | 42 |
| VISUALLY_BROKEN | 1 |
| NOT_REACHABLE | 14 |

> 本表为初始盘点，不代表完成。实施中每次调整状态都必须补充真实验收证据。

## 2026-07-18 入口回归修复记录

- 浅色 Tauri 主窗口关闭原生阴影，并统一 `html / body / #app` 暖白背景；1440×900 实机截图确认不再出现外圈黑边。
- 思维导图将编辑工具栏、节点属性摘要和 AI 审查面板恢复为桌面尺寸默认可见；工具栏按可用画布宽度换行，快捷键帮助不再被截断。
- 思维导图实机通过 `Tab` 新建子节点、`Ctrl+Z` 撤销；后端恢复后实际点击 AI 审查，日志确认 DeepSeek chat completion 与 `/api/mindmap/analyze` 均返回 200，中文审查意见定位到节点。
- 审稿工作区增加固定一级入口：对抗审查 Reviewer-2、承诺兑付 Claim Ledger、Argument Map；Reviewer-2 重新暴露评审角色与串并行模式。
- Claim Ledger 使用现有真实 ledger 状态与 API，完整显示全部承诺分组，未兑现/部分兑现仍可请求现有补实验建议接口。
- Agent 结果改用现有 `renderMarkdown` 安全渲染，表格、列表、代码和标题不再显示为原始 Markdown 符号。
- 修复 Tauri 开发启动器误选缺少 PyYAML 的 Python 解释器：启动前校验 PyYAML/FastAPI/Uvicorn，实机确认自动选择 `D:\env\anaconda\python.exe` 并在 1 秒内启动后端。

代表性实机截图：

- `mindmap-tab-shortcut-real.png`
- `mindmap-ai-review-real.png`
- `mindmap-ai-review-deepseek-real.png`
- `review-entry-restored.png`
- `claim-ledger-entry-restored.png`
- `argument-map-entry-restored.png`
