<template>
  <div class="shell-toolbar"><slot /></div>
</template>

<style scoped>
.shell-toolbar {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-panel);
}
</style>
