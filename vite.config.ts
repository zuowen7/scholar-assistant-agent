/// <reference types="vitest" />
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [],
  },
  clearScreen: false,
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18088',
        changeOrigin: true,
      },
    },
    watch: {
      ignored: [
        '**/python-dist/**',
        '**/src-tauri/python-dist/**',
        '**/src-tauri/target/**',
        '**/build/**',
        '**/src-tauri/resources/pandoc/**',
      ],
    },
  },
  optimizeDeps: {
    include: ['monaco-editor'],
    entries: ['index.html'],
    exclude: ['@tauri-apps/api'],
  },
  build: {
    sourcemap: false,
    // Monaco is intentionally isolated and ships its own large language workers.
    // Warn only when an application chunk exceeds that known editor boundary.
    chunkSizeWarningLimit: 4500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const moduleId = id.replaceAll('\\', '/')
          if (!moduleId.includes('/node_modules/')) return undefined
          if (moduleId.includes('/node_modules/monaco-editor/')) return 'monaco'
          if (moduleId.includes('/node_modules/@tauri-apps/')) return 'tauri'
          if (
            moduleId.includes('/node_modules/@vue-flow/')
            || moduleId.includes('/node_modules/dagre/')
          ) return 'graph'
          if (
            moduleId.includes('/node_modules/katex/')
            || moduleId.includes('/node_modules/highlight.js/')
            || moduleId.includes('/node_modules/marked/')
            || moduleId.includes('/node_modules/dompurify/')
          ) return 'document-rendering'
          if (moduleId.includes('/node_modules/lucide-vue-next/')) return 'icons'
          if (
            moduleId.includes('/node_modules/vue/')
            || moduleId.includes('/node_modules/vue-i18n/')
            || moduleId.includes('/node_modules/@vue/')
          ) return 'vue'
          return 'vendor'
        },
      },
    },
  },
});
