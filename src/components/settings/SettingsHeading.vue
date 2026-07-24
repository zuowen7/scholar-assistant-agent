<template>
  <header class="settings-heading" :class="{ compact }">
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
  </header>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ title: string; description: string; compact?: boolean }>(), {
  compact: false,
})
</script>

<style scoped>
.settings-heading {
  margin-bottom: 20px;
}
.settings-heading.compact {
  margin-bottom: 12px;
}
h3 {
  margin: 0;
  color: var(--c-text-0);
  font-size: 17px;
  font-weight: 650;
  letter-spacing: -0.015em;
}
p {
  max-width: 540px;
  margin: 7px 0 0;
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.6;
}
</style>
