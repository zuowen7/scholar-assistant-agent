# 研墨生产前端 UI 覆盖矩阵

分支：`refactor/reference-driven-ui`

最后更新：2026-07-18（持续适配中）

状态仅允许：`FULLY_ADAPTED`、`PARTIALLY_ADAPTED`、`SHELL_ONLY`、`UNTOUCHED`、`VISUALLY_BROKEN`、`NOT_REACHABLE`。

`FULLY_ADAPTED` 的门槛：真实生产入口可达、真实数据或 API 已验证、主要交互已走通，并完成 1440×900、1200×800、1024×768、200% 缩放、深色和中英文检查。仅复用 AppShell 或 Token 不算完成。

## 1. 全局框架与启动

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| 主窗口 AppShell、统一导航、窗口控制 | PARTIALLY_ADAPTED | 四个核心模块统一一级导航；真实活动壳层已增加原生拖拽轨、双击最大化与回归测试；浅色原生黑边已去除 | Tauri 实机拖拽与全模式键盘焦点扫描 |
| 启动加载 InkBrushLoader | PARTIALLY_ADAPTED | 暖白低饱和加载层与 5 秒安全退出；PyMuPDF 原生扩展改为 PDF 布局解析时按需加载，`create_app` 冷启动不再预载 `fitz` | 真实后端超时与启动失败录屏 |
| 全局拖放文件遮罩 | PARTIALLY_ADAPTED | 统一面板、真实 Tauri drag-drop 路由和扩展名校验 | 真实拖放与不支持文件录屏 |
| 翻译恢复 Banner | PARTIALLY_ADAPTED | 恢复/丢弃接原有持久化 | 中断后重启恢复实验 |
| Toast 成功/错误/警告/信息 | PARTIALLY_ADAPTED | 统一 Toast；文件树失败、更新、设置均已接入 | 四类状态的实机触发 |
| 深色模式 | PARTIALLY_ADAPTED | `welcome-dark-en-1440x900.png`、`translation-dark-en-1440x900.png` | 全生产弹窗逐页检查 |
| 中文界面 | PARTIALLY_ADAPTED | 新增翻译、设置、语音、缩放文案均进 i18n | 长错误和窄屏文案检查 |
| 英文界面 | PARTIALLY_ADAPTED | 深色英文欢迎页、翻译页和设置已实机检查 | Reviewer/Agent 长文本全量检查 |
| 80%–200% WebView 缩放 | PARTIALLY_ADAPTED | 新增持久化设置与 Ctrl+/Ctrl-/Ctrl+0；`ui-zoom-200-percent-fixed-1440x900.png` | 编辑器、导图、Reviewer 的 200% 检查 |
| 键盘焦点、Escape、reduced-motion | PARTIALLY_ADAPTED | AppDialog 焦点陷阱/恢复、Escape；关键动效已降级 | 全弹窗 Tab 顺序录屏 |
| 旧 AppTopBar | NOT_REACHABLE | 不再被 App.vue 渲染，等价功能转入 AppShell/SettingsCenter | 等价入口全量回归后移除死代码 |

## 2. 首页与项目旅程

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| 欢迎页 / 最近项目 | PARTIALLY_ADAPTED | 暖白编辑入口、真实最近项目；深色英文和 200% 已检查 | 最近项目不存在/权限失败 |
| 新建工程 | PARTIALLY_ADAPTED | AppDialog 式表单、真实模板 API 和项目创建；`project-created-live.png` | 无权限目录与同名冲突 |
| 从模板新建 | PARTIALLY_ADAPTED | 真实 `/api/paper-assets/templates` 和 `/api/paper-scaffold` | 模板服务错误与长列表 |
| 打开文件夹 | PARTIALLY_ADAPTED | Tauri 目录选择器与真实文件树 | 取消、长路径、权限失败 |
| 最近项目打开/移除 | PARTIALLY_ADAPTED | 真实项目打开；移除不删除用户文件 | 失效路径恢复引导 |
| 项目关闭与返回欢迎页 | PARTIALLY_ADAPTED | 新 Header 回复入口；脏标签确认对话框已实机检查 | 多脏标签与保存失败 |
| 项目类型检测与恢复 | PARTIALLY_ADAPTED | 复用 useProject 与原有项目格式 | 损坏元数据和半创建项目 |

## 3. 翻译旅程

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| 翻译首页 / 上传区 | PARTIALLY_ADAPTED | 已重构为学术翻译工作台；浅/深、中/英、1440/1024 实机 | 真实拖放录屏 |
| PDF/DOCX/TXT/Markdown 等选择 | PARTIALLY_ADAPTED | 真实 TXT 已完成翻译；接原有解析器 | PDF、DOCX 大文件实验 |
| 翻译引擎/模型选择 | PARTIALLY_ADAPTED | SettingsCenter 真实 Provider/Ollama/模型配置 | 切换 Provider 后立即翻译回归 |
| SSE 五阶段进度 | PARTIALLY_ADAPTED | 步骤列表、块进度、实时预览；真实进度截图 | 长文稳定性和中途恢复 |
| 取消翻译 | PARTIALLY_ADAPTED | 新增处理中取消，直接 abort 现有 SSE | 大文件中途取消实机 |
| 块级失败与重试 | PARTIALLY_ADAPTED | 失败卡、单块 loading/错误接原 `retry_block` API；路由契约已验证重试会同步块、chunk、最终 Markdown、QA、fallback 和输出文件，重复调用不会负计数 | 可控真实 Provider 失败后的 Tauri 点击重试 |
| 术语/QA 警告 | PARTIALLY_ADAPTED | 真实 qaWarnings 折叠阅读；已修复生产 SSE `chunk_index`/旧 `index` 与前端 `chunkIndex` 不一致 | 多警告长列表实机 |
| 双栏阅读/译文阅读 | PARTIALLY_ADAPTED | 真实 2 块翻译；1440、1200、1024 无横向页面滚动 | 百页级长文滚动性能 |
| 句子联动高亮 | PARTIALLY_ADAPTED | sentenceAlign 保留无标点尾句、段落换行和真实字符范围；中文分号不再误切；按句序支持一对多联动，32 项专项测试通过 | 真实 Provider 的错位块、一对多与百页长文滚动 |
| 结果搜索/筛选 | PARTIALLY_ADAPTED | 新增基于真实 original/translated 块的搜索、计数和无结果 | 长文搜索和键盘清除 |
| 双语/译文 Markdown 导出 | PARTIALLY_ADAPTED | 真实菜单与现有导出函数 | 保存、取消、文件内容校验 |
| 双语/译文 Word 导出 | PARTIALLY_ADAPTED | 重启后真实翻译结果导出 37,399B DOCX；本机 Word 已打开，XML 验证两段英文与两段中文均存在 | 取消保存与写入失败反馈 |
| PPTX / Data Availability 导出 | PARTIALLY_ADAPTED | 接原有真实导出 API，新菜单可达 | 产物打开和可选依赖失败 |

## 4. 写作、LaTeX 与编辑器

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| Markdown 写作工作区 | PARTIALLY_ADAPTED | 1440/1200/1024/200% 已检查；中央正文优先 | 深色长稿和键盘全旅程 |
| LaTeX 编辑器 | PARTIALLY_ADAPTED | 真实 `.tex`、Monaco、文件树、标签和任务助手 | 编译错误、多标签与 200% |
| 文件树 | PARTIALLY_ADAPTED | 真实创建/重命名/剪切/复制/粘贴/删除；统一对话框与 Toast | 权限失败和跨盘符粘贴 |
| 标签页与脏状态 | PARTIALLY_ADAPTED | 打开即脏问题已修；关项目前确认；Agent Inline Diff 接受后恢复已保存状态 | 多标签关闭与代理写入冲突 |
| 编辑器工具栏 | PARTIALLY_ADAPTED | 低密度工具栏与按需更多菜单；恢复 Ctrl+B 和标题栏左右侧栏开关；右侧 Dock 接通文字 Tab，窄窗不再被 1280px 媒体规则强制隐藏 | Tauri 1024/200% Dock 覆盖与全 Tooltip/键盘入口扫描 |
| 正文/大纲/预览 | PARTIALLY_ADAPTED | 共享 SegmentedControl；真实 Markdown Preview | 超长文稿与滚动位置保留 |
| 选文浮动工具栏 | PARTIALLY_ADAPTED | 润色/压缩/扩写/论证检查连真实编辑能力 | 多行/跨段选区实机 |
| AI 编辑 `/api/edit` | PARTIALLY_ADAPTED | 预设已与 Agent V2 分离；真实 SSE 返回已验证；累积 delta 重复 bug 已修 | 取消、错误、实际接受/撤销录屏 |
| Command Palette | PARTIALLY_ADAPTED | Ctrl+K 上下文编辑、真实 `/api/edit` | 屏幕边缘定位和连续命令 |
| 合规检查 | PARTIALLY_ADAPTED | 共享 AppDialog、加载/错误/报告、真实 `/api/compliance` | 真实长报告和重试 |
| 图片 / Vision / OCR / Chart / Table | PARTIALLY_ADAPTED | 统一工具菜单与现有真实 API/插入链路 | 实物图片、可选依赖与失败 |
| 引用索引/提取 | PARTIALLY_ADAPTED | 现有 citation API、预览和回写文稿 | 真实 BibTeX/无结果/异常 |
| Zotero 状态/搜索/插入 | PARTIALLY_ADAPTED | AppPromptDialog 和真实 Zotero API；未连接有就地错误 | 本机 Zotero 真实插入 |
| Ghost Text / 完成建议 | PARTIALLY_ADAPTED | 现有 `/api/complete`、Tab 接受和测试保留 | 真实模型延迟、取消与输入冲突 |

## 5. Agent V2

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| 写作页任务式 Agent | PARTIALLY_ADAPTED | Agent 成为写作右侧常驻 Dock：当前文件/选区、连续对话、工具活动、步骤、审批和新任务均接 Agent V2 真状态 | Tauri 长任务、多次审批与脏标签写入冲突 |
| 全局 Agent 主面板 | PARTIALLY_ADAPTED | 从左下角图标提升为主导航明确入口；任务、工具、审批、结果层级与安全 Markdown 渲染保持 | 1024/200% 长输出与跨模块上下文 |
| Agent 独立窗口 | PARTIALLY_ADAPTED | 复用同一 AgentPanel 和真实会话单例 | 独立窗口恢复、缩放和多屏 |
| 会话列表/恢复 | PARTIALLY_ADAPTED | 会话列表读取真实 JSONL 元数据、首条任务、消息数和时间；已完成/持久化会话可打开真实文本与工具轨迹；新增不删除历史的“新会话”入口，均已 Tauri 实机 | 运行中会话跨窗口恢复、空/损坏会话 |
| 工具调用过程/错误 | PARTIALLY_ADAPTED | `tool_name` 协议、折叠参数和结果 | 超长参数、二进制结果、超时 |
| 审批 allow once/session/deny | PARTIALLY_ADAPTED | allow once/deny 已实机；修复 SSE 适配层硬编码 `force_approval` 后，“本次会话”入口真实可达；Tauri 中一次会话许可连续执行两个独立 `str_replace`，仅首次审批且两次均写盘；超时自动 deny、终止且不写盘 | 敏感工具强制逐次审批与长任务 |
| Inline Diff 接受/拒绝 | PARTIALLY_ADAPTED | 真实 `str_replace` 内联差异已实机接受和拒绝；脏标签中找不到或存在多个替换锚点时会可靠回退到文本审批，不再丢失审批入口 | 超长差异与 `write_file` 大文件预览 |
| checkpoint 与文件刷新 | PARTIALLY_ADAPTED | 实机验证 Agent 把磁盘日期写为 2028 时，Monaco 仍保留未保存的 2027 和本地草稿、脏状态未清；干净标签继续即时同步并保留光标 | 多文件写入和跨标签刷新 |
| 附件、RAG 文档、@引用 | PARTIALLY_ADAPTED | 真实上传/文档 API/文件引用 | 删除、重名和大文件 |
| Skills 发现/选择/调用 | PARTIALLY_ADAPTED | 真实 `/api/agent/v2/skills`；8 个 Nature 工作流；`nature_reviewer` 真实 SSE/Claim Ledger 调用 | 连续切换和失效 Skill |
| 中止/恢复/结果 | PARTIALLY_ADAPTED | abort/resume/result API 和面板状态保留 | 真实长任务中断与超时 |

## 6. 思考、论证与审稿

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| 思维导图画布 | PARTIALLY_ADAPTED | 37 个真实节点、Vue Flow 和 body 往返保留 | 深色/英文/200% |
| 缩放/fit/缩略图/自动布局 | PARTIALLY_ADAPTED | 全入口恢复；自动布局和 fit 已实机 | 极端节点数和布局恢复 |
| 快捷键/撤销/节点编辑 | PARTIALLY_ADAPTED | Tab 新建、Ctrl+Z 撤销实机；快捷键帮助恢复 | 全快捷键和焦点冲突 |
| AI 扩展 | PARTIALLY_ADAPTED | 选中节点后调原 `/api/mindmap/expand` | 真实扩展、取消与失败 |
| AI 审查/提示 | PARTIALLY_ADAPTED | DeepSeek `/api/mindmap/analyze` 真实 200 与中文意见定位 | 多意见定位、英文和错误 |
| Reviewer-2 对抗审稿 | PARTIALLY_ADAPTED | 固定一级入口、角色/串并行、真实 12 条批评；评审卡已统一规范语义 token、亮/暗输入对比度与键盘焦点环 | 恢复、长文、深色/英文实机复核 |
| 真实评审导入 | PARTIALLY_ADAPTED | 导入表单连现有 Reviewer-2 解析 | 真实长评审和解析失败 |
| Claim Ledger / 承诺兑付 | PARTIALLY_ADAPTED | 独立入口、真实 doc_id 查询和补实验建议 | 编辑/删除/重定位 |
| rebuttal | PARTIALLY_ADAPTED | 作者回应编辑与现有真实保存链路 | 提交、失败与状态刷新 |
| Argument Map 主画布 | PARTIALLY_ADAPTED | 固定入口、真实图数据、自动布局、新建图和 Inspector | 深色/英文/极端图规模 |
| 提取/批评/建议/扁平化/导出 | PARTIALLY_ADAPTED | 原有真实 Argument API 和 Inspector 入口保留 | 五个动作逐项实机 |
| Companion 旧面板 | NOT_REACHABLE | ReviewerWorkspace 提供 Reviewer/Ledger/Map 等价新入口 | 等价链路全回归后清理死样式 |

## 7. 设置、系统、语音

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| 设置中心 | PARTIALLY_ADAPTED | 统一 Drawer，六个真实分区；浅/深、中/英已实机 | 1024/200% 和全表单键盘 |
| Provider/API Key/Base URL/Model | PARTIALLY_ADAPTED | DeepSeek 真实连接状态、测试、保存；不创建新 Provider | 失败、密钥清空和确认边界 |
| Ollama 模型/刷新/启动 | PARTIALLY_ADAPTED | 真实模型列表和服务状态 | 本机 Ollama 停止/重启 |
| Tectonic 状态/安装 | PARTIALLY_ADAPTED | 真实就绪状态已实机 | 未安装机器和安装失败 |
| HTTP 代理 | PARTIALLY_ADAPTED | 真实 runtime config 保存 | 非法 URL、重启后生效 |
| 阅读字号/行距/字体/译文色 | PARTIALLY_ADAPTED | 实时预览与真实双栏 CSS 变量 | 极端值和长文稿 |
| 界面缩放 | PARTIALLY_ADAPTED | Tauri `setZoom`、持久化滑块、快捷键；200% 遮挡已修 | 核心四页 200% 全部录屏 |
| 自定义背景/透明度 | PARTIALLY_ADAPTED | Tauri 选择、清除、持久化和预览 | 大图/视频/损坏文件 |
| 主题切换 | PARTIALLY_ADAPTED | 设置实机切换与持久化 | 所有生产弹窗深色 |
| 语言切换 | PARTIALLY_ADAPTED | 设置实机 zh-CN/en-US 切换与持久化 | 全页长文溢出 |
| 语音开关/热键/唤醒词/灵敏度 | PARTIALLY_ADAPTED | 真实 localStorage 配置、支持检测；识别器统一持有/释放 busy 锁；低/中/高灵敏度分别控制同音词与 interim 触发，测试覆盖自然结束和手动停止后的唤醒恢复 | 真实麦克风口述唤醒与系统权限拒绝 |
| 语音助手浮层 | PARTIALLY_ADAPTED | Alt+Shift+V 实机打开；无语音超时保留本地化错误及重试；重试实机恢复监听；Agent 忙碌不再静默丢指令；各类命令会先激活真实写作/翻译/导图工作区再分发 | 真实口述逐项走通命令与 Agent fallback |
| 服务状态/Debug/更新 | PARTIALLY_ADAPTED | 系统页真实后端/Provider/Tectonic；修复 DebugPanel Teleport 被设置 Drawer 层级遮挡；GitHub Release 检查 | Tauri 离线、新版本、前后端日志与日志目录打开 |

## 8. 输出、弹窗与边界状态

| 入口 / 状态 | 当前状态 | 当前证据 | 未完成验收 |
| --- | --- | --- | --- |
| Markdown 保存 | PARTIALLY_ADAPTED | Monaco 真实文件 I/O 与 dirty tab | 冲突、权限和磁盘失败 |
| Word 导出 | PARTIALLY_ADAPTED | 真实 `/api/export/word` 和 Tauri 保存器 | 产物打开与失败 |
| LaTeX 导出 | PARTIALLY_ADAPTED | 真实模板 API、转换和 `.tex` 保存 | 全模板产物检查 |
| PDF 导出 | PARTIALLY_ADAPTED | Tectonic 检查和真实 `/api/export/pdf` | Tectonic 缺失/编译错误/产物 |
| 论文模板/新建论文 | PARTIALLY_ADAPTED | 统一 AppDialog 和真实 scaffold | 全模板回归 |
| 合规弹窗 | PARTIALLY_ADAPTED | 共享 AppDialog 与真实报告 | 长报告、错误、重试 |
| 确认/输入对话框 | PARTIALLY_ADAPTED | 文件创建/删除、Zotero、关项目均使用共享对话框 | 所有长文本与 Tab 顺序 |
| 空状态 | PARTIALLY_ADAPTED | 项目、文件树、翻译搜索、Agent、Reviewer 均有任务型空状态 | 全入口无数据录屏 |
| 加载/Skeleton | PARTIALLY_ADAPTED | 文件树、模板、翻译、审稿、Agent 分层加载 | 慢网络和超时 |
| API 错误/后端离线 | PARTIALLY_ADAPTED | 重启改为异步 60 秒冷启动并校验新监听 PID；定位 Windows 冷启动曾卡在 `pymupdf._extra`，改为请求时加载后，真实单击重启由 PID 38516 在 1.5 秒接管、health 200 且窗口持续响应；恢复后清除本地化离线提示但不清任务结果 | 启动阶段连续崩溃和强制占端口失败 |
| 权限/审批错误 | PARTIALLY_ADAPTED | Agent V2 拒绝路径已实机：一次审批、会话终止、磁盘不变；审批超时确定性验证自动 deny 且不写盘 | 越界写入实机 |

## 当前统计

<!-- UI_COVERAGE_STATS_START -->
| 状态 | 数量 |
| --- | ---: |
| FULLY_ADAPTED | 0 |
| PARTIALLY_ADAPTED | 90 |
| SHELL_ONLY | 0 |
| UNTOUCHED | 0 |
| VISUALLY_BROKEN | 0 |
| NOT_REACHABLE | 2 |
<!-- UI_COVERAGE_STATS_END -->

> 当前不能声称全量完成：所有生产可达入口已纳入统一外壳或交互流，但尚未每一项都完成真实数据、三尺寸、200%、深色和中英文的交叉验收。

## 2026-07-18 当前迭代记录

- 去除浅色 Tauri 主窗口原生黑边，统一 `html/body/#app` 背景。
- 收敛全局设计 token：历史别名调用迁移到规范词汇，仅保留 3 个跨组件派生语义；静态未定义引用仅剩 5 个有意的运行时变量，并加入自动扫描门禁。ReviewerThread 输入框亮/暗对比度分别为 15.84:1 / 13.84:1。
- 修复真实 AppShell 无拖拽区的问题；顶部原生拖拽轨支持左键拖动和双击最大化，旧 AppTopBar 不再承担无效拖拽逻辑。
- 修复写作右侧栏在 1280px 以下被 CSS 永久隐藏；接通文字 Tab 与窄屏覆盖式 Dock，并将 Agent 上下文、对话、工具活动、审批和新任务留在当前文稿旁。
- 修复系统页 DebugPanel 已打开却被 Drawer 遮住的问题；Popover 浮层现在位于 AppDialog 之上。
- 修复翻译句对照丢尾句、中文分号误切、换行丢失和按字符长度错配；一对多句子会联动高亮完整对应范围。
- 恢复思维导图快捷键、编辑工具和 AI 审查；Tab、Ctrl+Z 和 DeepSeek 真实审查通过。
- 恢复 Reviewer-2、Claim Ledger、Argument Map 固定一级入口与真实数据链路。
- Agent Skills 接真实目录，加入 8 个 Nature 工作流；保留 Agent V2 单一运行时。
- 修复 Agent 审批在 CRLF SSE 暂停点不显示、真实 session_id 丢失；写入审批、Inline Diff 接受和 checkpoint 已完成真实 Tauri 验收。
- 修复 Agent 文件修改被拒后换用另一写入工具重试的问题；运行时现在确定性终止本轮，真实 Tauri 验证会话 persisted 且磁盘内容未变。
- 修复 SSE 适配层把全部写入都错误标记为强制逐次审批；真实 Tauri 点击一次“本次会话”后，两个独立 `str_replace` 连续完成且磁盘内容一致，未出现第二张审批卡。
- 补齐 Agent “新会话”和历史会话读取：真实 JSONL 文本、工具调用与结果可在会话页重新打开，历史不会因新建会话被删除。
- 修复 Agent checkpoint 直接覆盖未保存 Monaco 标签并清脏状态的问题；真实 Agent 写盘后用户草稿保持不变，并补齐内联差异无法定位时的文本审批回退。
- Agent 系统提示注入运行时当前日期，避免日期任务依赖模型旧知识；真实验收文件已从错误的 2025 修正为 2026。
- 恢复编辑器 Ctrl+B/标题栏侧栏开关；修复后端 error 状态停止健康轮询和恢复后模型状态不刷新的问题。
- 重构翻译空态、SSE 进度、双栏结果、QA、重试、搜索、取消和导出；真实 TXT 2 块翻译通过。
- 修复翻译重试只更新单块、未同步 chunk/QA/最终内容与导出的问题；重启后再次完成真实 2 块翻译并打开 37,399B 双语 Word 产物。
- 修复桌面端后端冷启动 15 秒超时、同步命令卡住窗口、旧端口误判成功及恢复后残留英文错误；真实离线→单击重启→新 PID/health 200 已通过。
- 将 PyMuPDF 原生扩展从 API 启动路径移到 PDF 布局解析请求路径，消除 Windows 偶发 `_extra` 冷启动阻塞；修复后真实重启 1.5 秒恢复。
- AI 编辑预设回到 `/api/edit`，自由任务留在 Agent V2；修复 SSE 累积 delta 重复拼接。
- 建立系统/更新/诊断设置页，恢复 Provider、Ollama、Tectonic、代理、阅读、背景、语音、主题和语言入口。
- 新增 Tauri 界面 80%–200% 缩放及快捷键；修复 200% 时欢迎页标题越界。
- 重构语音助手为安静任务浮层；去除文件树、共享按钮和诊断入口的发光涟漪。
- 修复语音超时/不支持错误随浮层消失、命令结果不可见、静默提交后识别器未停止、自然结束后 speech busy 锁不释放；Tauri 中完成热键→超时错误→重新聆听回归。
- 修复未进入目标工作区时语音导图、翻译导出、编辑命令事件无人消费却报告成功；命令现在先激活对应生产页面再调用原有真实入口。

下一项未完成入口：继续 Agent 多文件 checkpoint；随后走 Provider 失败和输出失败分支。语音仍保留真实麦克风逐命令口述验收。

代表性实机证据：

- `translation-real-result-1440x900.png`
- `translation-real-result-1200x800.png`
- `translation-real-result-1024x768.png`
- `translation-dark-en-1440x900.png`
- `translation-export-menu-redesign-1440x900.png`
- `ui-zoom-200-percent-fixed-1440x900.png`
- `settings-display-dark-en-zoom-1440x900.png`
- `settings-system-1440x900.png`
- `voice-assistant-redesign-1440x900.png`
- `voice-timeout-retry-live.png`
- `voice-retry-listening-live.png`
- `mindmap-ai-review-real.png`
- `argument-map-fitted-real.png`
- `agent-nature-reviewer-selected-1440x900.png`
- `agent-approval-after-sse-fix-live.png`
- `agent-inline-diff-accepted-checkpoint.png`
- `agent-session-approval-enabled-live2.png`
- `agent-session-two-edits-complete-live.png`
- `agent-session-history-open-live.png`
- `agent-new-session-cleared-live.png`
- `agent-dirty-preserved-live.png`
- `agent-dirty-fallback-approval-live.png`
- `settings-offline-restart-visible-fixed.png`
