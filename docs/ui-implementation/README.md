# 参考图驱动前端重构验收记录

分支：`refactor/reference-driven-ui`

## 参考图与 Tauri 实现

| 页面 | 参考图 | 1440×900 Tauri 实现 |
| --- | --- | --- |
| 写作工作区 | [参考图](../ui-reference/2.png) | [实现截图](./writing-1440x900-clean.png) |
| LaTeX 编辑器 | [参考图](../ui-reference/3.png) | [实现截图](./latex-1440x900-clean-final.png) |
| 思维导图 | [参考图](../ui-reference/4.png) | [实现截图](./mindmap-1440x900-final4.png) |
| 对抗式审稿 | [参考图](../ui-reference/5.png) | [实现截图](./reviewer-1440x900-v3.png) |

`ui-reference/1.png` 用作共享导航、品牌区、模型状态和任务式 Agent 面板的辅助基线。

## 页面差异与保留偏差

- 写作工作区：构图、三栏关系和正文主体已对齐参考图；正文继续使用真实 Monaco/Markdown，因此标题标记和部分 Markdown 符号仍可见。未启动 Agent 任务时，右栏如实显示等待状态，不填充示例历史。
- LaTeX 编辑器：截图打开的是仓库真实 `python/pandoc_templates/neurips.tex`，文件树、标签、行号、语法模式、保存状态均为真实数据；右侧建议区在未调用 AI 前保持空白。
- 思维导图：使用当前项目的 37 个真实节点，双侧自动布局、语义色、连线、缩放、缩略图和 AI 扩展均保留。参考图节点更少，因此真实数据在 `fitView` 后卡片更小、连线密度更高。
- 对抗式审稿：Reviewer-2 通过当前 DeepSeek Provider 实际生成 12 条批评，Claim Ledger 也由当前文稿实际建立。Provider 返回英文批评，未为截图伪造中文内容；锚点与作者回应在卡片展开后显示。

## 响应式截图

- [1200×800](./writing-1200x800-final2.png)：右侧 Agent 自动折叠，正文优先。
- [1024×768](./writing-1024x768.png)：全局导航收为图标栏，正文和章节大纲保留。
- [1440×900、WebView 200%](./writing-1440x900-200pct-final.png)：章节大纲和右栏折叠，仅保留图标导航与正文，无页面级横向滚动。

共享 Shell 支持 `Ctrl/Cmd + +`、`Ctrl/Cmd + -` 和 `Ctrl/Cmd + 0` 调整 WebView 缩放。

## 复用的真实能力

- Agent V2 会话、工具步骤、审批与结果；
- `/api/edit` AI 写作动作；
- Monaco、文件树、文件读写、标签页和保存状态；
- Vue Flow 节点数据、自动布局、缩放、缩略图与 AI 扩展；
- Reviewer-2、真实评审导入、Claim Ledger、锚点、状态和 rebuttal；
- 原项目打开、最近文件、Provider 状态、翻译、导出及现有数据格式。

没有新增后端、Provider、Agent Runtime、项目格式或 Fixture。

## 验证结果

- `npx vitest run`：51 个测试文件、706 个测试全部通过。
- `npx vue-tsc --noEmit --pretty false`：通过。
- `npm run build`：通过；保留仓库原有动态导入和大 chunk 警告。
- Tauri：真实启动成功；1440×900、1200×800、1024×768 和 200% WebView 缩放均完成截图验收。
- Reviewer-2 与 Claim Ledger：实际 API 请求成功并生成真实结果。
- 验收结束后已停止本轮启动的 Tauri、Vite、Python API 和 Ollama 进程，端口 5173、18088、11434 已释放。
