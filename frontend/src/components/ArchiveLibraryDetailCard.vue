<template>
  <article class="detail-card" v-if="archive">
    <div class="archive-head">
      <div>
        <h4>{{ archive.entity_name }}</h4>
        <div class="archive-meta">
          {{ archive.project_name }} · {{ formatEntityType(archive.entity_type) }} ·
          {{ formatImportanceTier(archive.importance_tier) }}
        </div>
      </div>
      <button class="btn" @click.stop="$emit('toggle')">
        {{ selected ? "移除" : "选中" }}
      </button>
    </div>
    <div class="detail-block" v-for="item in detailSections" :key="item.label">
      <div class="detail-title">{{ item.label }}</div>
      <p>{{ item.value }}</p>
    </div>
  </article>
  <article class="detail-card empty" v-else>
    选择左侧档案后，这里会显示完整详情。
  </article>
</template>

<script setup>
import { computed } from "vue";

import { formatEntityType, formatImportanceTier } from "../utils/chineseDisplay.js";

const props = defineProps({
  archive: { type: Object, default: null },
  selected: { type: Boolean, default: false },
});

defineEmits(["toggle"]);

const detailSections = computed(() => {
  if (!props.archive) {
    return [];
  }
  return [
    { label: "故事定位", value: props.archive.entity_role || "暂无定位" },
    { label: "核心动机", value: props.archive.core_drive || "暂无动机" },
    { label: "表层伪装", value: props.archive.surface_mask || "暂无表层描述" },
    { label: "隐藏张力", value: props.archive.hidden_tension || "暂无隐藏张力" },
    { label: "关系摘要", value: props.archive.relationship_summary || "暂无关系摘要" },
  ];
});
</script>

<style scoped>
.detail-card {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffaf1;
  padding: 14px;
}

.archive-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.archive-meta,
.empty {
  color: var(--text-sub);
}

.detail-block + .detail-block {
  margin-top: 12px;
}

.detail-title {
  font-weight: 700;
  margin-bottom: 4px;
}

.detail-block p {
  margin: 8px 0 0;
}
</style>
