<template>
  <div class="scene-list-panel">
    <div class="scene-list-header">
      <span class="scene-list-title">场景列表</span>
      <button class="scene-add-btn" @click="$emit('add')" title="添加场景">+</button>
    </div>
    <div class="scene-list-body">
      <div
        v-for="scene in scenes"
        :key="scene.scene_id"
        :class="['scene-item', { 'scene-item--active': scene.scene_id === selectedSceneId }]"
        @click="$emit('select', scene.scene_id)"
      >
        <div class="scene-item-header">
          <span class="scene-order">{{ scene.scene_order }}</span>
          <span class="scene-status" :class="'status-' + scene.status">
            {{ statusLabel(scene.status) }}
          </span>
        </div>
        <div class="scene-item-title">{{ scene.title || `场景 ${scene.scene_order}` }}</div>
        <div class="scene-item-meta">{{ scene.word_count || 0 }} 字</div>
        <button
          class="scene-delete-btn"
          @click.stop="$emit('delete', scene.scene_id)"
          title="删除"
        >×</button>
      </div>
      <div v-if="!scenes.length" class="scene-list-empty">
        暂无场景，点击 + 添加
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  scenes: { type: Array, default: () => [] },
  selectedSceneId: { type: String, default: "" },
});

defineEmits(["select", "add", "delete"]);

function statusLabel(status) {
  const map = { draft: "草稿", review: "审阅中", final: "定稿" };
  return map[status] || status;
}
</script>

<style scoped>
.scene-list-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-right: 1px solid #e0e0e0;
  background: #fafafa;
}
.scene-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
  font-weight: 600;
}
.scene-add-btn {
  background: none;
  border: 1px solid #ccc;
  border-radius: 4px;
  width: 28px;
  height: 28px;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  color: #666;
}
.scene-add-btn:hover { background: #e8e8e8; }
.scene-list-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.scene-item {
  position: relative;
  padding: 10px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  cursor: pointer;
  background: #fff;
  border: 1px solid #eee;
  transition: all 0.15s;
}
.scene-item:hover { border-color: #aaa; }
.scene-item--active {
  border-color: #409eff;
  background: #ecf5ff;
}
.scene-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.scene-order {
  font-size: 12px;
  color: #999;
  font-weight: 600;
}
.scene-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
}
.status-draft { background: #fdf6ec; color: #e6a23c; }
.status-review { background: #ecf5ff; color: #409eff; }
.status-final { background: #f0f9eb; color: #67c23a; }
.scene-item-title {
  font-size: 13px;
  color: #333;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.scene-item-meta {
  font-size: 11px;
  color: #aaa;
}
.scene-delete-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: none;
  border: none;
  color: #ccc;
  cursor: pointer;
  font-size: 16px;
  display: none;
}
.scene-item:hover .scene-delete-btn { display: block; }
.scene-delete-btn:hover { color: #f56c6c; }
.scene-list-empty {
  text-align: center;
  color: #ccc;
  padding: 40px 0;
  font-size: 13px;
}
</style>
