<template>
  <div class="companion-panel">
    <!-- Sub-tab bar -->
    <div class="sub-tab-bar">
      <button
        class="sub-tab"
        :class="{ active: activeSubTab === 'ledger' }"
        @click="activeSubTab = 'ledger'"
      >
        论证账本
      </button>
      <button
        class="sub-tab"
        :class="{ active: activeSubTab === 'reviewer' }"
        @click="activeSubTab = 'reviewer'"
      >
        Reviewer 2
      </button>
    </div>

    <!-- Staleness banner -->
    <div v-if="companion.state.ledgerStale" class="stale-banner">
      草稿已改，可能过期
      <button class="reanalyze-btn" @click="handleAnalyze">重新分析</button>
    </div>

    <!-- Ledger sub-page -->
    <div v-if="activeSubTab === 'ledger'" class="sub-page">
      <LedgerList
        :ledger="companion.state.ledger"
        :building="companion.state.building"
        @analyze="handleAnalyze"
        @focus-anchor="companion.focusAnchor"
      />
    </div>

    <!-- Reviewer 2 sub-page (Phase 3) -->
    <div v-else class="sub-page reviewer-placeholder">
      <p class="placeholder-text">Reviewer 2 对抗功能将在 Phase 3 开放。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useArgumentCompanion } from '../../composables/useArgumentCompanion'
import LedgerList from './LedgerList.vue'

const companion = useArgumentCompanion()
const activeSubTab = ref<'ledger' | 'reviewer'>('ledger')

const props = defineProps<{
  content: string
}>()

async function handleAnalyze() {
  await companion.buildOrRebuildLedger(props.content)
}
</script>

<style scoped>
.companion-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  font-size: 12px;
}

.sub-tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border, #2a2a2a);
  flex-shrink: 0;
}

.sub-tab {
  flex: 1;
  padding: 6px 8px;
  font-size: 11px;
  border: none;
  background: none;
  color: var(--text-dim, #888);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.sub-tab.active {
  color: var(--accent, #60a5fa);
  border-bottom-color: var(--accent, #60a5fa);
}

.sub-tab:hover:not(.active) {
  color: var(--text, #ccc);
}

.stale-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background: #3a2f00;
  color: #fbbf24;
  font-size: 11px;
  flex-shrink: 0;
}

.reanalyze-btn {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #fbbf24;
  background: none;
  color: #fbbf24;
  cursor: pointer;
}

.sub-page {
  flex: 1;
  overflow-y: auto;
}

.reviewer-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-text {
  color: var(--text-dim, #666);
  font-size: 12px;
}
</style>
