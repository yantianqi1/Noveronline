<template>
  <article class="workbench-card panel detail-panel">
    <h2 class="card-title">对象详情</h2>
    <p>展示当前对象的结构化档案字段，直接来自 worldline agent state。</p>

    <n-empty v-if="!selectedAgent" description="选择对象后，这里会显示身份、动机、关系与行动倾向。" />
    <div v-else class="detail-sections">
      <section class="detail-block" v-for="item in detailSections" :key="item.key">
        <div class="detail-title">{{ item.label }}</div>

        <p v-if="item.variant === 'text'" class="detail-text">{{ item.text }}</p>

        <dl v-else-if="item.variant === 'entries'" class="detail-entries">
          <div
            v-for="entry in item.entries"
            :key="`${item.key}-${entry.label}`"
            class="detail-entry"
          >
            <dt>{{ entry.label }}</dt>
            <dd>{{ entry.value }}</dd>
          </div>
        </dl>

        <ul v-else class="detail-items">
          <li v-for="entry in item.items" :key="`${item.key}-${entry}`">
            {{ entry }}
          </li>
        </ul>
      </section>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";
import { NEmpty } from "naive-ui";

import { buildSelectedAgentDetailSections } from "./agentDetailPresentation.js";

const props = defineProps({
  selectedAgent: { type: Object, default: null },
});

const detailSections = computed(() => buildSelectedAgentDetailSections(props.selectedAgent));
</script>

<style scoped>
.panel {
  padding: 10px;
}

.panel p {
  color: var(--text-sub);
}

.detail-sections {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.detail-block {
  display: grid;
  gap: 6px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 10px;
  background: #fffaf1;
}

.detail-title {
  font-weight: 700;
  color: var(--accent-copper-deep);
}

.detail-text,
.detail-entry dd,
.detail-items li {
  margin: 0;
  color: var(--text-main);
  white-space: pre-wrap;
  line-height: 1.7;
}

.detail-entries {
  display: grid;
  gap: 8px;
  margin: 0;
}

.detail-entry {
  display: grid;
  gap: 4px;
}

.detail-entry dt {
  color: var(--text-dim);
  font-size: 12px;
}

.detail-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.detail-items li {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(176, 125, 75, 0.12);
  color: var(--accent-copper-deep);
  font-size: 13px;
}
</style>
