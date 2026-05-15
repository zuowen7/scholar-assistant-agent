<template>
  <div>
    <div class="arg-toolbar">
      <input
        :value="modelValue"
        class="arg-input"
        placeholder="论证主题"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        @keydown.enter="$emit('create')"
      />
      <button class="arg-btn primary" :disabled="loading || !modelValue.trim()" @click="$emit('create')">新建</button>
    </div>

    <div v-if="message" class="arg-message">{{ message }}</div>

    <div v-if="!tree" class="arg-empty">
      新建一个论证图，把想法逐步展开成论文结构。
    </div>

    <template v-else>
      <div class="arg-actions">
        <button class="arg-btn" :disabled="loading || !selectedNodeId" @click="$emit('expand')">AI 展开</button>
        <button class="arg-btn" :disabled="loading || !selectedNodeId" @click="$emit('review')">逻辑审查</button>
        <button class="arg-btn" :disabled="loading" @click="$emit('flatten')">生成草稿</button>
      </div>

      <!-- 导出选项 -->
      <div class="arg-export-opts">
        <label class="arg-label-inline">
          格式
          <select :value="flattenOpts.template" class="arg-select" @change="$emit('update:flattenOpts', { ...flattenOpts, template: ($event.target as HTMLSelectElement).value })">
            <option value="markdown">Markdown</option>
            <option value="latex">LaTeX (.tex)</option>
            <option value="docx">Word (.docx)</option>
          </select>
        </label>
        <label v-if="flattenOpts.template === 'latex'" class="arg-label-inline">
          模板
          <select :value="flattenOpts.latex_template" class="arg-select" @change="$emit('update:flattenOpts', { ...flattenOpts, latex_template: ($event.target as HTMLSelectElement).value })">
            <option value="generic_article">Generic</option>
            <option value="ieee_conference">IEEE Conference</option>
            <option value="ieee_journal">IEEE Journal</option>
            <option value="acm">ACM</option>
            <option value="neurips">NeurIPS</option>
            <option value="lncs">LNCS (Springer)</option>
          </select>
        </label>
        <label class="arg-label-inline">
          <input type="checkbox" :checked="flattenOpts.include_references" @change="$emit('update:flattenOpts', { ...flattenOpts, include_references: ($event.target as HTMLInputElement).checked })" />
          含参考文献
        </label>
      </div>

      <!-- SSE 进度条 -->
      <div v-if="flattenProgress.active" class="arg-progress">
        <div class="arg-progress-bar">
          <div class="arg-progress-fill" :style="{ width: flattenProgress.pct + '%' }"></div>
        </div>
        <span class="arg-progress-text">{{ flattenProgress.text }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  tree: Record<string, unknown> | null
  loading: boolean
  selectedNodeId: string
  modelValue: string
  flattenOpts: {
    template: string
    latex_template: string
    include_references: boolean
  }
  flattenProgress: {
    active: boolean
    pct: number
    text: string
  }
  message: string
}>()

defineEmits<{
  create: []
  expand: []
  review: []
  flatten: []
  'update:modelValue': [value: string]
  'update:flattenOpts': [value: { template: string; latex_template: string; include_references: boolean }]
}>()
</script>
