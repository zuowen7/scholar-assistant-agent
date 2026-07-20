// ESLint flat config for Scholar Assistant frontend
// Docs: https://eslint.org/docs/latest/use/configure/configuration-files
//
// 用途：Vue 3 + TypeScript 代码静态检查，统一代码风格
// 配套命令（见 package.json scripts）：
//   npm run lint           # 检查所有 .ts/.vue 文件
//   npm run lint:fix       # 自动修复
//   npm run format         # Prettier 格式化
//   npm run format:check   # 检查格式（CI 用）
//
// 依赖（需 npm install -D）：
//   eslint @typescript-eslint/eslint-plugin @typescript-eslint/parser
//   eslint-plugin-vue vue-eslint-parser
//   prettier eslint-config-prettier

import js from '@eslint/js'
import vuePlugin from 'eslint-plugin-vue'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import prettierConfig from 'eslint-config-prettier'

export default [
  // ── 全局忽略 ──────────────────────────────────────────
  {
    ignores: [
      'dist/**',
      'build/**',
      'node_modules/**',
      'src-tauri/**',
      'python/**',
      'outputs/**',
      'docs/**',
      '*.config.ts',        // vite.config.ts 等配置文件暂不 lint
      'scripts/**',
    ],
  },

  // ── JS 基础规则 ──────────────────────────────────────
  js.configs.recommended,

  // ── Vue 规则（apply 后才有 .vue 文件的 parser） ──────
  ...vuePlugin.configs['flat/recommended'],

  // ── TypeScript + Vue 组合 ────────────────────────────
  {
    files: ['src/**/*.{ts,vue}'],
    languageOptions: {
      parser: vueParserWithTs(tsParser),
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
    },
    rules: {
      // 启用 TS 推荐规则
      ...tsPlugin.configs.recommended.rules,

      // ── 项目实际放宽的规则 ──────────────────────────
      // Vue 模板里多字组件名允许（项目里 UiButton 等已用）
      'vue/multi-word-component-names': 'off',
      // 允许 console.warn / console.error（生产代码需要）
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      // TS 项目里用 no-unused-vars 替代会被 ts 接管的规则
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          // Vue setup 里有些 ref 声明后只在模板使用，TS 看不到
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      // 允许 any 但 warn（渐进收紧）
      '@typescript-eslint/no-explicit-any': 'warn',
      // 函数返回类型推断复杂时不强制
      '@typescript-eslint/explicit-module-boundary-types': 'off',
    },
  },

  // ── 测试文件放宽 ────────────────────────────────────
  {
    files: ['src/__tests__/**/*.{ts,vue}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': 'off',
    },
  },

  // ── Prettier 兼容（关闭所有与 Prettier 冲突的规则） ──
  prettierConfig,
]

// ── 工具函数：让 vue-eslint-parser 内部用 TS parser ──
function vueParserWithTs(tsParser) {
  // 动态引入 vue-eslint-parser 避免在非 vue 项目里报错
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const vueParser = require('vue-eslint-parser')
  return vueParser
}
