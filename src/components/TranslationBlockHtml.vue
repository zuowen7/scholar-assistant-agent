<template>
  <!-- eslint-disable-next-line vue/no-v-html -- block 模式经 DOMPurify 消毒，sentence 模式全量 escapeHtml -->
  <div v-html="renderedHtml"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderBlock } from '../utils/markdown'
import { renderSentenceMarkedHtml } from '../utils/sentenceAlign'

const props = withDefaults(
  defineProps<{
    text: string
    blockType?: string
    mode?: 'block' | 'sentence'
    lang?: 'en' | 'zh'
    blockId?: string
    side?: 'orig' | 'trans'
  }>(),
  {
    blockType: undefined,
    mode: 'block',
    lang: 'en',
    blockId: '',
    side: 'orig',
  },
)

// Keeping block rendering in a child component lets Vue skip parsing every
// unchanged paragraph when progress, retry, hover, or toolbar state updates.
const renderedHtml = computed(() =>
  props.mode === 'sentence'
    ? renderSentenceMarkedHtml(props.text, props.lang, props.blockId, props.side)
    : renderBlock(props.text, props.blockType),
)
</script>
