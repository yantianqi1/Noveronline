<template>
  <aside class="detail">
    <template v-if="selectedNode">
      <h3>节点档案</h3>
      <p><strong>名称:</strong> {{ selectedNode.name }}</p>
      <p><strong>类型:</strong> {{ selectedNode.entity_type || "未标注" }}</p>
      <p><strong>ID:</strong> <span class="mono">{{ selectedNode.id }}</span></p>
      <p v-if="selectedNode.summary"><strong>摘要:</strong> {{ selectedNode.summary }}</p>
    </template>
    <template v-else-if="selectedEdge">
      <h3>关系档案</h3>
      <p><strong>关系:</strong> {{ selectedEdge.name || "关系" }}</p>
      <p><strong>来源:</strong> {{ selectedEdge.source_name || selectedEdge.source_id }}</p>
      <p><strong>目标:</strong> {{ selectedEdge.target_name || selectedEdge.target_id }}</p>
      <p v-if="selectedEdge.fact"><strong>说明:</strong> {{ selectedEdge.fact }}</p>
    </template>
    <template v-else>
      <h3>档案侧栏</h3>
      <p>点击图中的节点或关系线，查看详细信息。</p>
    </template>
  </aside>
</template>

<script setup>
defineProps({
  selectedNode: { type: Object, default: null },
  selectedEdge: { type: Object, default: null },
});
</script>

<style scoped>
.detail {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffcf4;
  padding: 12px;
  height: 100%;
  min-height: 680px;
}

.detail h3 {
  margin: 0 0 8px;
  font-family: "ZCOOL XiaoWei", serif;
}

.detail p {
  margin: 6px 0;
  line-height: 1.45;
  color: #564a36;
}
</style>
