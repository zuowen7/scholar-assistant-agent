<template>
  <section class="shell-panel" :class="{ padded, scrollable }">
    <slot />
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ padded?: boolean; scrollable?: boolean }>(), {
  padded: false,
  scrollable: false,
})
</script>

<style scoped>
.shell-panel {
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  background: var(--c-panel);
}
.padded {
  padding: 16px;
}
.scrollable {
  overflow: auto;
}
</style>
