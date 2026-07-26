<template>
  <section class="recent-files">
    <h2>{{ t('shell.recentFiles') }}</h2>
    <button
      v-for="item in visibleItems"
      :key="item.path"
      type="button"
      class="recent-item"
      :title="item.path"
      @click="$emit('open', item.path)"
    >
      <FileText :size="15" aria-hidden="true" />
      <span>{{ item.name }}</span>
    </button>
    <p v-if="visibleItems.length === 0" class="recent-empty">{{ t('shell.recentEmpty') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FileText } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ items: Array<{ name: string; path: string }> }>()
defineEmits<{ open: [path: string] }>()
const visibleItems = computed(() => props.items.slice(0, 4))
const { t } = useI18n()
</script>

<style scoped>
.recent-files {
  padding-top: 18px;
  border-top: 1px solid var(--c-border);
}
.recent-files h2 {
  margin: 0 10px 9px;
  color: var(--c-text-3);
  font:
    600 12px/1.3 var(--font-sans),
    var(--font-zh);
}
.recent-item {
  width: 100%;
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 10px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--c-text-2);
  font:
    400 13px/1.3 var(--font-sans),
    var(--font-zh);
  cursor: pointer;
  text-align: left;
}
.recent-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-item:hover {
  background: color-mix(in srgb, var(--c-panel) 56%, transparent);
  color: var(--c-text-0);
}
.recent-empty {
  margin: 0;
  padding: 8px 10px;
  color: var(--c-text-3);
  font-size: 12px;
  line-height: 1.5;
}
</style>
