<template>
  <div class="ui-empty">
    <div v-if="$slots.icon || icon" class="ui-empty-icon">
      <slot name="icon">
        <component :is="icon" :size="iconSize" :stroke-width="1.2" />
      </slot>
    </div>
    <div class="ui-empty-body">
      <p v-if="title" class="ui-empty-title">{{ title }}</p>
      <p v-if="subtitle" class="ui-empty-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions || actionLabel" class="ui-empty-actions">
      <slot name="actions">
        <UiButton variant="secondary" size="sm" @click="$emit('action')">
          {{ actionLabel }}
        </UiButton>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import UiButton from './UiButton.vue'

withDefaults(defineProps<{
  icon?: any
  iconSize?: number
  title?: string
  subtitle?: string
  actionLabel?: string
}>(), {
  iconSize: 32,
})

defineEmits<{
  action: []
}>()
</script>

<style scoped>
.ui-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding: var(--space-7) var(--space-5);
  text-align: center;
  min-height: 180px;
}

.ui-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  color: var(--c-text-3);
}

.ui-empty-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ui-empty-title {
  margin: 0;
  font-family: var(--font-serif-zh);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--c-text-1);
}

.ui-empty-subtitle {
  margin: 0;
  font-family: 'EB Garamond', serif;
  font-style: italic;
  font-size: var(--text-md);
  color: var(--c-text-3);
  max-width: 280px;
}

.ui-empty-actions {
  display: flex;
  gap: var(--space-2);
}
</style>
