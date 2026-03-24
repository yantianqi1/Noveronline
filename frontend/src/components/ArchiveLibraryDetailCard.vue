<template>
  <article class="detail-card" v-if="archive">
    <header class="archive-head">
      <div class="archive-summary">
        <p class="archive-kicker mono">ARCHIVE DOSSIER</p>
        <h4>{{ archive.entity_name }}</h4>
        <div class="archive-meta">
          <span class="archive-chip">{{ archive.project_name }}</span>
          <span class="archive-chip">{{ formatEntityType(archive.entity_type) }}</span>
          <span class="archive-chip accent">{{ formatImportanceTier(archive.importance_tier) }}</span>
        </div>
      </div>
      <button class="btn primary detail-toggle" @click.stop="$emit('toggle')">
        {{ toggleLabel }}
      </button>
    </header>

    <div class="detail-sections">
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

  <article class="detail-card empty" v-else>
    <p class="archive-kicker mono">DETAIL</p>
    <h4>等待选中档案</h4>
    <p class="empty-copy">选择左侧档案后，这里会显示完整详情。</p>
  </article>
</template>

<script setup>
import { computed } from "vue";

import { buildArchiveDetailSections } from "./archiveDetailSections.js";
import { formatEntityType, formatImportanceTier } from "../utils/chineseDisplay.js";

const props = defineProps({
  archive: { type: Object, default: null },
  selected: { type: Boolean, default: false },
});

defineEmits(["toggle"]);

const detailSections = computed(() => buildArchiveDetailSections(props.archive));
const toggleLabel = computed(() => (props.selected ? "移出会话" : "加入会话"));
</script>

<style scoped>
.detail-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
  border: 1px solid rgba(176, 125, 75, 0.18);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(244, 239, 226, 0.9), rgba(255, 255, 255, 0.98));
  padding: 20px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.archive-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.archive-summary {
  display: grid;
  gap: 8px;
}

.archive-kicker {
  margin: 0;
  color: var(--accent-copper-deep);
  letter-spacing: 0.14em;
  font-size: 11px;
}

.archive-summary h4,
.empty h4 {
  font-size: 28px;
}

.archive-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.archive-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(159, 141, 106, 0.24);
  color: var(--text-sub);
  font-size: 12px;
}

.archive-chip.accent {
  color: var(--accent-copper-deep);
  background: rgba(176, 125, 75, 0.12);
}

.detail-toggle {
  flex-shrink: 0;
  padding-inline: 16px;
}

.detail-sections {
  display: grid;
  gap: 14px;
}

.detail-block {
  display: grid;
  gap: 10px;
  border: 1px solid rgba(159, 141, 106, 0.14);
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(249, 245, 238, 0.68));
  padding: 15px 16px;
}

.detail-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent-copper-deep);
}

.detail-text,
.empty-copy,
.detail-entry dd,
.detail-items li {
  margin: 0;
  color: var(--text-main);
  white-space: pre-wrap;
  line-height: 1.75;
}

.detail-entries {
  display: grid;
  gap: 10px;
  margin: 0;
}

.detail-entry {
  display: grid;
  gap: 4px;
}

.detail-entry dt {
  font-size: 12px;
  color: var(--text-dim);
  letter-spacing: 0.04em;
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
  padding: 5px 10px;
  border-radius: var(--radius-full);
  background: rgba(176, 125, 75, 0.1);
  color: var(--accent-copper-deep);
  font-size: 13px;
  line-height: 1.5;
}

.empty {
  justify-content: center;
  min-height: 320px;
}

@media (max-width: 760px) {
  .archive-head {
    flex-direction: column;
  }

  .detail-toggle {
    width: 100%;
  }
}
</style>
