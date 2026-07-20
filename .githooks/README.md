# Git Hooks for Scholar Assistant

本目录存放项目共享的 git hooks，通过 `git config core.hooksPath .githooks` 启用。

## 启用

```bash
# 方式一：npm script（推荐）
npm run setup

# 方式二：手动
git config core.hooksPath .githooks
```

新 clone 仓库后必须执行一次，否则 hooks 不会生效。

## 包含的 hooks

### pre-commit

提交前自动检查暂存文件的代码质量：

- **TypeScript 类型检查**（`vue-tsc --noEmit`）— 仅当有 `.ts`/`.vue` 改动时
- **ESLint 检查**（针对暂存文件）— 仅当有 `.ts`/`.vue` 改动时
- **Prettier 格式检查**（针对暂存文件）— 仅当有 `.ts`/`.vue` 改动时
- **Ruff 检查**（针对暂存 `.py` 文件）— 仅当有 Python 改动时
- **Ruff format 检查**（针对暂存 `.py` 文件）

任一失败即阻止提交。

## 跳过 hook

紧急情况下可跳过：

```bash
git commit --no-verify -m "..."
```

但**不要养成习惯**——hook 是代码质量的最后一道防线。

## 修改 hook

编辑 `.githooks/pre-commit` 后立即生效，无需重新启用。

## 故障排查

### `Permission denied` / 权限问题

在 Unix 系统上需要赋予执行权限：

```bash
chmod +x .githooks/pre-commit
```

### `command not found: npx` / `python`

确保 `node`、`python`、`ruff` 在 PATH 中。`ruff` 通过 `python -m ruff` 调用，只要装了 `requirements-dev.txt` 即可。

### hook 太慢

只检查暂存文件，正常应 < 5 秒。如果 tsc 全量检查慢，可临时注释掉 pre-commit 里的 tsc 段，依赖 CI 兜底。
