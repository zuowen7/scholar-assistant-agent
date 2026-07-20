# Scholar Assistant 团队技术能力提升方案

> 由 Senior Developer（高级开发工程师）基于实际代码扫描后产出
> 扫描日期：2026-07-20 · 项目版本：v0.4.2

## 一、评估结论

基于实际代码扫描，项目在 **架构设计 / 测试覆盖 / 文档协作** 三个维度成熟度高（8-9/10），但在 **代码规范 / CI/CD / 类型安全** 三个维度有明显凹陷（3-7/10）。凹陷项就是团队技术能力提升的最大机会点。

| 维度 | 现状评分 | 关键发现 |
|------|---------|---------|
| 架构设计 | 9/10 | Agent V2 runtime 模块边界清晰，SSE 事件契约明确，AGENTS.md 给出意图→路径决策表 |
| 测试覆盖 | 8/10 | 后端 100+ 测试文件（unit/integration/e2e/stress），前端 50+（含 voice 5 层 tier） |
| 文档协作 | 8/10 | docstring 规范，跨层契约（`tool_name`、SSE 事件名）有强约束 |
| 类型安全 | 7/10 | TS strict 已开，但 `noUnusedLocals/Params/ImplicitReturns` 全关，测试文件被 tsconfig 排除 |
| CI/CD | 4/10 | `.github/workflows/` 仅 `release.yml`，无 push/PR 触发的 test/lint |
| 代码规范 | 3/10 | 无 ESLint、无 Ruff/Black、无 Prettier，仅靠 `tsc --noEmit` 兜底 |

## 二、团队特征与策略

- **团队规模**：1-2 人独立开发
- **策略**：用工具链 + git hook 替代人工流程，让一个人也能维持大团队的工程质量
- **原则**：自动化优先、本地拦截优先于 CI 拦截、规范严格度匹配团队规模

## 三、分阶段提升路线图

### Phase 1 — 代码规范体系（优先级最高，立即落地）

**目标**：统一前后端代码风格，消除风格争议，为后续 CI 类型检查打基础。

| 子任务 | 产物 | 验收 |
|--------|------|------|
| 后端 Ruff + Black 配置 | `python/ruff.toml` 或 `pyproject.toml` | `ruff check .` 通过，`ruff format --check .` 通过 |
| 前端 ESLint + Prettier | `eslint.config.js`、`.prettierrc.json` | `npm run lint` 通过，`npm run format:check` 通过 |
| npm scripts 整合 | `package.json` 新增 `lint`/`lint:fix`/`format` | 一键命令可用 |

**规则集选择**：
- 后端：`ruff` 启用 `E`（pycodestyle errors）、`F`（pyflakes）、`I`（isort）、`B`（bugbear）、`UP`（pyupgrade）、`SIM`（simplify）
- 前端：`@vue/eslint-config-typescript` recommended + `eslint-plugin-vue` recommended + Prettier

### Phase 2 — Git Hook 本地拦截

**目标**：commit 前自动跑 lint + type check，阻止低质量代码进入仓库。

| 子任务 | 产物 | 验收 |
|--------|------|------|
| pre-commit shell 脚本 | `.githooks/pre-commit` | 提交含 lint 错误的代码会被拒绝 |
| 启用 hook | `git config core.hooksPath .githooks` | 新 clone 后 `npm run setup` 即可启用 |
| 性能优化 | 只检查暂存文件（lint-staged 思路） | 单次 commit hook < 5s |

**为什么不用 husky**：1-2 人团队不需要 husky 的多 hook 编排能力，shell 脚本 + `core.hooksPath` 更轻、依赖更少。

### Phase 3 — CI/CD 质量门禁

**目标**：CI 作为本地 hook 的兜底，确保任何分支推送都通过质量检查。

| 子任务 | 产物 | 验收 |
|--------|------|------|
| `ci.yml` workflow | `.github/workflows/ci.yml` | push/PR 触发，跑前端 + 后端双矩阵 |
| 前端 job | vitest + tsc + eslint | 失败阻断合并 |
| 后端 job | pytest + ruff | 失败阻断合并 |
| 缓存优化 | `actions/cache` 缓存 node_modules / pip | CI 总时长 < 3min |

### Phase 4 — 类型安全收紧

**目标**：让 TypeScript 编译器真正成为代码质量的第一道防线。

| 子任务 | 产物 | 验收 |
|--------|------|------|
| 开启严格选项 | `tsconfig.json` 修改 | `tsc --noEmit` 通过 |
| 测试纳入类型检查 | `tsconfig.test.json` | 测试代码也能享受类型保护 |
| Python mypy（可选） | `python/mypy.ini` | `mypy src/` 通过（先 warn-only） |

### Phase 5 — 架构深度 Review（已完成首轮）

**目标**：对核心模块做 code review，找出潜在 bug、并发问题、重构机会。

**首轮 review 报告**: 见 [`code-review-agent-v2.md`](./code-review-agent-v2.md)

**首轮发现摘要**:

| 优先级 | 问题 | 状态 |
|--------|------|------|
| 🔴 P0 | `_cleanup_pool` 空实现，session 池内存泄漏 | 待修复 |
| 🟠 P1 | `workflow cleanup/delete` 接口是 stub | 待修复 |
| 🟠 P1 | 配置加载 `except Exception: pass` 吞异常 | 待修复 |
| 🟡 P2 | `registry._provider` 直接访问私有属性 | 待重构 |
| 🟡 P2 | `_approval_events` 异常路径可能泄漏 | 待加固 |
| 🟡 P2 | `_SESSION_POOL` 模块级全局可变状态 | 长期改进 |

**抽样模块**: `python/src/agent_v2/router.py`, `runtime/conversation.py`

**后续 review 计划**: 每次聚焦一个模块，按 P0→P1→P2 顺序修复。下一轮建议 review `permissions.py` 和前端 `useAgentChat.ts`。

## 四、推进节奏建议

1-2 人团队不要一次全推，按以下节奏：

- **本周**：Phase 1（代码规范）— 半天落地，立竿见影
- **本周**：Phase 2（git hook）— 1-2 小时，让规范真正执行
- **下周**：Phase 3（CI/CD）— 半天，兜底保障
- **下周**：Phase 4（类型收紧）— 视暴露问题数量决定深度
- **后续**：Phase 5（架构 review）— 持续进行，每次 review 一个模块

## 五、不在本方案范围内

- 不引入 husky/lint-staged（shell 脚本足够）
- 不引入 commitlint（1-2 人不需要强制 commit message 规范）
- 不引入 code owner / 分支保护（小团队靠自律 + CI 即可）
- 不重写架构（现有 Agent V2 设计良好，仅做局部优化）
