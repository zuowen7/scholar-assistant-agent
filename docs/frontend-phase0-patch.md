# Phase 0 具体改动清单(代码级)

> 配套 `frontend-consistency-audit.md` §6 Phase 0。所有改动为**增量、非破坏性**,每步可独立提交。本文给出可直接落盘的 before/after。

---

## P0-1 · 亮色主题不可见边框(真 bug)

**文件**:`src/components/EditorLayout.vue:912`(`.sidebar-rail-button`)

```css
/* before */
border: 1px solid rgba(255, 255, 255, 0.05);

/* after */
border: 1px solid var(--border-color);
```

`--border-color` 已按主题定义:亮 `#E8E1D3`(tokens.css:323)、暗 `#232328`(tokens.css:201)。改后两主题均可见。
hover 态(`EditorLayout.vue:934-935`)同步见 P0-2。

---

## P0-2 · accent 辉光硬编码 → token

**文件**:`src/components/EditorLayout.vue:934-935`(`.sidebar-rail-button:hover`)

```css
/* before */
border-color: rgba(91, 108, 255, 0.2);
box-shadow: 0 8px 24px rgba(91, 108, 255, 0.15);

/* after */
border-color: rgba(var(--c-accent-rgb), 0.2);
box-shadow: 0 8px 24px rgba(var(--c-accent-rgb), 0.15);
```

`--c-accent-rgb: 91, 108, 255` 已存在(tokens.css:169)。改后换 accent 色时自动跟随,不再漏改。

---

## P1-1 · 收紧全局焦点环(去除过宽 + 冗余)

**文件**:`src/App.vue:815`(全局 `:focus-visible`)

```css
/* before —— 裸选择器,误伤非交互元素且强制圆角 */
:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
  border-radius: var(--radius-xs);
}

/* after —— 仅交互目标,去掉聚焦瞬间改圆角 */
:where(button, [role="button"], a, input, select, textarea, .u-interactive, [tabindex]:not([tabindex="-1"])):focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
```

随后可逐步删除组件内冗余的 `:focus-visible` 本地副本(如 `AiPanel.vue` 的 666/724/739/745/765、`UiButton.vue:60`),统一由全局收口。非阻断,可随相关组件改动顺手清理。

---

## P1-2 · 导航反馈(WS3 N1 / N2)

**N1 — 侧边栏高亮错位**:收敛 `setMode` 调用,使 `shellSection` 同源。
- 位置:`src/composables/useAppMode.ts:9` 的 `setMode`,调用点 `src/App.vue:46,138,280,390`。
- 动作:新增 `navigateTo(module)` 定向 helper,所有入口走它,内部同时置 `mode` 与 `shellSection`。

**N2 — 导出静默 no-op**:`src/components/EditorLayout.vue:507,526`
- 动作:导出前 `if (!selectedTemplate) { showExportToast(t('editor.selectTemplate')); return }`,把静默失败转为明确反馈。

> 右面板 N4(`toggleRightPanel` / 默认 `'ai'`)经核查**已正确**,不改动。AI 面板默认常驻且为默认标签,保持。

---

## 验收(Phase 0 完成后)

- 亮色主题下侧栏收起按钮边框可见(P0-1)。
- Tab 走查任意按钮/链接/输入:键盘聚焦有 `--ring-focus` 环,且非交互元素不再误伤(P1-1)。
- 切换 accent 色(若日后调整),hover 辉光自动跟随(P0-2)。
- 点侧边栏高亮即时同步视图(N1);未选模板导出给 toast 而非无反应(N2)。
- `npm run typecheck` / `npm run build` / `npx vitest run` 全绿。
