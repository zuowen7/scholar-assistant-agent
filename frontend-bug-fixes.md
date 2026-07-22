# 前端功能 Bug 修复清单

> 用户验收反馈（2026-07-21 11:43）| 测试 PDF：`C:\Users\zuowen\Desktop\science.adn8744.pdf`
>
> 目标：把重构后所有断掉的功能全部修复上线，然后进入视觉打磨阶段。

## 📋 问题总览（15 个用户反馈 + 控制台错误）

### P1 · 控制台错误（最优先，3 项）

| # | 问题 | 证据 |
|---|------|------|
| E1 | i18n key 缺失：`project.removeRecent` / `editor.collapseSidebar` / `aiPanel.presetPolish` | console: `[intlify] Not found ... key in 'zh' locale messages` |
| E2 | i18n HTML 警告：多语言消息含 `<code>` 标签，建议改用 linked messages | console: `[intlify] Detected HTML in '...' message. Recommend not using HTML messages` |
| E3 | `/api/companion/ledger?doc_id=...` 返回 404 | console: `Failed to load resource: 404` |
| E4 | 语音助手 `[voice] triggerVoiceCommand, state= error` | console: 语音命令触发后立即进 error 态 |

### P1 · 核心功能 bug（4 项）

| # | 问题 | 现象 |
|---|------|------|
| #9 | 最近文件打不开 | 必须先关闭现有项目，再点才能打开 |
| #12 | Ollama 模型列表没加载 | 前端要手写模型名，后端 `/api/ollama/models` 实际有数据 |
| #13 | 背景更新选完图片不变 | Tauri dialog 选了图但背景不切换 |
| #14 | 文件树功能没找到 | 编辑器没显示文件树，或挂载条件错了 |

### P1 · 交互 bug（4 项）

| # | 问题 | 现象 |
|---|------|------|
| #1 | 窗口无法拖拽移动 | 刚打开时拖不动窗口 |
| #2 | 翻译无逐句逐段对照 | 原文和译文没有左右对照显示 |
| #3 | 写作时右边 tab 栏打不开 | 右侧 tab 按钮没反应 |
| #4 | AI Panel 无表面反应 | 点精简/扩写/润色/检查论证看不到反馈，必须开左下角 Agent 才看到运行；逻辑错；右边 Agent tab 打不开只能用左下角 |

### P1 · 缺失功能（4 项）

| # | 问题 | 现象 |
|---|------|------|
| #5 | 调试面板打不开 | 设置里点击调试面板没反应 |
| #6 | 无 Zotero API 配置入口 | 设置里找不到 |
| #7 | Agent 精确修改文件不能用 | str_replace 工具调用失败 |
| #8 | 思维导图无右键菜单 | 用户想要右键点击节点弹出编辑功能 |

### P2 · 视觉/布局（功能上线后做，2 项）

| # | 问题 | 证据 |
|---|------|------|
| #10 | 反驳字颜色看不清 | 截图：橙色「反驳」标签颜色与背景对比度低 |
| #11 | Claim Ledger 布局问题大 | 截图：左中右三栏比例失调，中间卡片过于窄 |

---

## 🔧 修复计划（分批）

- **第 1 批（现在）**：P1 控制台错误（E1-E4）— i18n 缺失、404、语音 error
- **第 2 批**：P1 核心功能 bug（#9 #12 #13 #14）
- **第 3 批**：P1 交互 bug（#1 #2 #3 #4）
- **第 4 批**：P1 缺失功能（#5 #6 #7 #8）
- **第 5 批（推后）**：P2 视觉打磨（#10 #11）

每批：修代码 → 跑 vitest 737 全绿 + tsc 0 错误 → 汇报。
