<template>
  <div>
    <div v-if="selectedNode" class="arg-detail">
      <label class="arg-label">
        主题
        <input
          :value="selectedDraft.topic"
          class="arg-input"
          @input="emit('update:selectedDraft', { topic: ($event.target as HTMLInputElement).value, content: selectedDraft.content })"
        />
      </label>
      <label class="arg-label">
        内容
        <textarea
          :value="selectedDraft.content"
          class="arg-textarea"
          rows="4"
          @input="emit('update:selectedDraft', { topic: selectedDraft.topic, content: ($event.target as HTMLTextAreaElement).value })"
        ></textarea>
      </label>
      <div class="arg-detail-actions">
        <button class="arg-btn primary" :disabled="loading" @click="emit('save')">保存节点</button>
        <button class="arg-btn" :disabled="loading" @click="emit('observe')">查找引用</button>
      </div>
      <div v-if="selectedNode.agent_feedback" class="arg-feedback">
        {{ selectedNode.agent_feedback }}
      </div>
    </div>

    <div v-if="recommendations.length" class="arg-recs">
      <div class="arg-section-title">推荐参考文献</div>
      <div v-for="rec in recommendations" :key="rec.doc_id" class="arg-rec">
        <div>
          <strong>{{ rec.title || rec.doc_id }}</strong>
          <span>{{ Math.round(rec.relevance_score * 100) }}%</span>
        </div>
        <p>{{ rec.excerpt }}</p>
        <button class="arg-btn tiny" @click="emit('bind', rec)">绑定</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface ArgumentReference {
  doc_id: string
  citation_key: string
  relevance_score: number
  binding_type: string
  bound_at: string
}

interface ArgumentNode {
  id: string
  parent_id: string | null
  topic: string
  content: string
  depth: number
  position: { x: number; y: number }
  domain_tags: string[]
  references: ArgumentReference[]
  logic_status: 'draft' | 'pass' | 'warning' | 'error'
  rule_issues: string[]
  agent_feedback: string | null
  status: 'draft' | 'expanded' | 'final'
  children: string[]
}

interface Recommendation {
  doc_id: string
  title: string
  relevance_score: number
  excerpt: string
}

defineProps<{
  selectedNode: ArgumentNode | null
  selectedDraft: { topic: string; content: string }
  loading: boolean
  recommendations: Recommendation[]
}>()

const emit = defineEmits<{
  save: []
  observe: []
  bind: [rec: Recommendation]
  'update:selectedDraft': [value: { topic: string; content: string }]
}>()
</script>
