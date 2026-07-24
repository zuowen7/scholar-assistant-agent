<template>
  <div v-html="renderedHtml"></div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { renderMarkdown } from '../utils/markdown'

const props = withDefaults(
  defineProps<{
    source: string
    streaming?: boolean
  }>(),
  {
    streaming: false,
  },
)

// Parsing + KaTeX + sanitizing is comparatively expensive. During SSE
// streaming, coalesce token bursts while still flushing the final response
// immediately when streaming ends.
const renderedSource = ref(props.source)
let renderTimer: ReturnType<typeof setTimeout> | null = null

function clearRenderTimer() {
  if (renderTimer !== null) {
    clearTimeout(renderTimer)
    renderTimer = null
  }
}

watch(
  () => [props.source, props.streaming] as const,
  ([source, streaming]) => {
    if (!streaming) {
      clearRenderTimer()
      renderedSource.value = source
      return
    }
    if (renderTimer !== null) return
    renderTimer = setTimeout(() => {
      renderTimer = null
      renderedSource.value = props.source
    }, 40)
  },
)

onBeforeUnmount(clearRenderTimer)

const renderedHtml = computed(() => renderMarkdown(renderedSource.value))
</script>
