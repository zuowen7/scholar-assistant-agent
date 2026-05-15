<template>
  <div class="arg-canvas">
    <button
      v-for="node in orderedNodes"
      :key="node.id"
      type="button"
      class="arg-node"
      :class="[node.logic_status, { selected: node.id === selectedNodeId, bound: node.references.length > 0 }]"
      :style="{ marginLeft: `${node.depth * 18}px` }"
      @click="$emit('select', node.id)"
    >
      <span class="arg-node-title">{{ node.topic }}</span>
      <span class="arg-node-meta">
        {{ node.status }}
        <template v-if="node.references.length"> · {{ node.references.length }} 条引用</template>
      </span>
    </button>
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

defineProps<{
  orderedNodes: ArgumentNode[]
  selectedNodeId: string
}>()

defineEmits<{
  select: [nodeId: string]
}>()
</script>
