<template>
  <aside class="document-outline">
    <div class="outline-header"><strong>{{ t('outline.title') }}</strong><button type="button" :title="t('outline.add')" @click="$emit('add')">+</button></div>
    <div class="outline-list">
      <button
        v-for="heading in headings"
        :key="`${heading.line}-${heading.text}`"
        type="button"
        class="outline-item"
        :class="{ active: activeLine === heading.line }"
        :style="{ paddingLeft: `${12 + Math.max(0, heading.level - 1) * 14}px` }"
        @click="$emit('navigate', heading.line)"
      >
        <ChevronRight v-if="heading.level <= 2" :size="13" aria-hidden="true" />
        <span>{{ heading.text }}</span>
      </button>
      <p v-if="headings.length === 0" class="outline-empty">{{ t('outline.empty') }}</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const props = defineProps<{ content: string; activeLine?: number }>()
defineEmits<{ navigate: [line: number]; add: [] }>()
const headings = computed(() => props.content.split(/\r?\n/).flatMap((line, index) => {
  const match = /^(#{1,6})\s+(.+?)\s*$/.exec(line)
  return match ? [{ level: match[1].length, text: match[2].replace(/[*_`]/g, ''), line: index + 1 }] : []
}))
</script>

<style scoped>
.document-outline { height: 100%; min-height: 0; display: flex; flex-direction: column; border-right: 1px solid var(--c-border); background: var(--c-panel); }
.outline-header { height: 52px; flex: 0 0 52px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-bottom: 1px solid var(--c-border); }
.outline-header strong { color: var(--c-text-1); font-size: 13px; }.outline-header button{width:28px;height:28px;border:0;border-radius:6px;background:transparent;color:var(--c-text-2);font-size:20px;cursor:pointer}.outline-header button:hover{background:var(--c-surface-2);color:var(--c-text-0)}
.outline-list { flex: 1; min-height: 0; overflow: auto; padding: 10px 8px; }.outline-item{width:100%;min-height:35px;display:flex;align-items:center;gap:4px;padding-right:8px;border:0;border-radius:7px;background:transparent;color:var(--c-text-2);font:400 12px/1.3 var(--font-sans),var(--font-zh);text-align:left;cursor:pointer}.outline-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.outline-item:hover{background:var(--c-surface-2);color:var(--c-text-0)}.outline-item.active{background:var(--c-accent-soft);color:var(--c-accent);font-weight:600}.outline-empty{padding:14px 8px;color:var(--c-text-3);font-size:11px;line-height:1.6}
</style>
