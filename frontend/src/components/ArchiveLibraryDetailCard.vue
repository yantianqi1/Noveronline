<template>
  <article class="archive-detail" v-if="archive">
    <header class="detail-header">
      <div class="detail-identity">
        <h3>{{ archive.entity_name }}</h3>
        <div class="detail-meta">
          <span class="status-tag" :class="entityTone">{{ formatEntityType(archive.entity_type) }}</span>
          <span class="status-tag ok">{{ formatImportanceTier(archive.importance_tier) }}</span>
          <span class="detail-project">{{ archive.project_name }}</span>
        </div>
      </div>
      <button class="btn primary" @click.stop="$emit('toggle')">
        {{ toggleLabel }}
      </button>
    </header>

    <div class="detail-sections">
      <template v-for="item in detailSections" :key="item.key">
        <!-- Collapsible group (agent profile) -->
        <section v-if="item.variant === 'collapsible'" class="detail-block collapsible-block">
          <button class="block-toggle" type="button" @click="toggleCollapse(item.key)">
            <h4 class="block-title">{{ item.label }}</h4>
            <span class="block-chevron" :class="{ open: expandedMap[item.key] }">&#9662;</span>
          </button>
          <div v-show="expandedMap[item.key]" class="block-body">
            <div v-for="entry in item.items" :key="entry.label" class="profile-field">
              <dt class="field-label">{{ entry.label }}</dt>
              <dd v-if="Array.isArray(entry.value)" class="field-tags">
                <span v-for="(tag, ti) in entry.value" :key="ti" class="field-tag">{{ tag }}</span>
              </dd>
              <dd v-else class="field-value">{{ entry.value }}</dd>
            </div>
          </div>
        </section>

        <!-- Text section -->
        <section v-else-if="item.variant === 'text'" class="detail-block">
          <h4 class="block-title">{{ item.label }}</h4>
          <p class="block-text">{{ item.text }}</p>
        </section>

        <!-- Entries section -->
        <section v-else-if="item.variant === 'entries'" class="detail-block">
          <h4 class="block-title">{{ item.label }}</h4>
          <dl class="block-entries">
            <div v-for="entry in item.entries" :key="`${item.key}-${entry.label}`" class="block-entry">
              <dt>{{ entry.label }}</dt>
              <dd>{{ entry.value }}</dd>
            </div>
          </dl>
        </section>

        <!-- Items section -->
        <section v-else class="detail-block">
          <h4 class="block-title">{{ item.label }}</h4>
          <ul class="block-items">
            <li v-for="entry in item.items" :key="`${item.key}-${entry}`">{{ entry }}</li>
          </ul>
        </section>
      </template>
    </div>
  </article>

  <article class="archive-detail archive-detail--empty" v-else>
    <h4>选择档案查看详情</h4>
    <p class="empty-hint">点击左侧列表中的任意档案卡片。</p>
  </article>
</template>

<script setup>
import { computed, reactive, watch } from "vue";

import { buildArchiveDetailSections } from "./archiveDetailSections.js";
import { formatEntityType, formatImportanceTier } from "../utils/chineseDisplay.js";

const props = defineProps({
  archive: { type: Object, default: null },
  selected: { type: Boolean, default: false },
});

defineEmits(["toggle"]);

const entityTone = computed(() => String(props.archive?.entity_type || "unknown").toLowerCase());
const detailSections = computed(() => buildArchiveDetailSections(props.archive));
const toggleLabel = computed(() => (props.selected ? "移出会话" : "加入会话"));

const expandedMap = reactive({});

function toggleCollapse(key) {
  expandedMap[key] = !expandedMap[key];
}

watch(detailSections, (sections) => {
  for (const section of sections) {
    if (section.variant === "collapsible" && !(section.key in expandedMap)) {
      expandedMap[section.key] = section.defaultExpanded ?? false;
    }
  }
}, { immediate: true });
</script>

<style scoped>
.archive-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-height: 100%;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  align-items: flex-start;
}

.detail-identity {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.detail-identity h3 {
  margin: 0;
  font-size: 22px;
  font-family: "ZCOOL XiaoWei", serif;
  color: var(--text-main);
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.detail-project {
  font-size: 12px;
  color: var(--text-dim);
}

.detail-sections {
  display: flex;
  flex-direction: column;
}

/* ── Standard sections ── */

.detail-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md) 0;
  border-bottom: 1px solid var(--line-soft);
}

.detail-block:last-child {
  border-bottom: none;
}

.block-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary);
  letter-spacing: 0.02em;
}

.block-text,
.empty-hint,
.block-entry dd,
.block-items li {
  margin: 0;
  color: var(--text-main);
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 14px;
}

.block-entries {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin: 0;
}

.block-entry {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.block-entry dt {
  font-size: 12px;
  color: var(--text-dim);
  letter-spacing: 0.03em;
}

.block-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.block-items li {
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: rgba(155, 44, 44, 0.06);
  color: var(--color-primary);
  font-size: 13px;
  line-height: 1.4;
}

/* ── Collapsible sections (agent profile) ── */

.collapsible-block {
  gap: 0;
  padding: 0;
  border-bottom: 1px solid var(--line-soft);
}

.collapsible-block:last-child {
  border-bottom: none;
}

.block-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
}

.block-toggle:hover {
  background: var(--bg-paper);
}

.block-toggle .block-title {
  margin: 0;
}

.block-chevron {
  font-size: 10px;
  color: var(--text-dim);
  transition: transform 0.2s ease;
}

.block-chevron.open {
  transform: rotate(180deg);
}

.block-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 0 14px;
}

.profile-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 0;
}

.profile-field + .profile-field {
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}

.field-label {
  font-size: 11.5px;
  color: var(--text-dim);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.field-value {
  margin: 0;
  font-size: 13.5px;
  color: var(--text-main);
  line-height: 1.65;
  word-break: break-word;
}

.field-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 2px 0 0;
}

.field-tag {
  display: inline-block;
  padding: 3px 9px;
  border-radius: var(--radius-full);
  background: var(--bg-paper-warm);
  border: 1px solid var(--line-soft);
  font-size: 12.5px;
  color: var(--text-sub);
  line-height: 1.4;
}

/* ── Empty state ── */

.archive-detail--empty {
  justify-content: center;
  align-items: center;
  min-height: 280px;
  text-align: center;
  color: var(--text-dim);
}

.archive-detail--empty h4 {
  margin: 0 0 var(--space-xs);
  font-size: 15px;
  color: var(--text-sub);
}

.empty-hint {
  color: var(--text-dim);
  font-size: 13px;
}

@media (max-width: 640px) {
  .detail-header {
    flex-direction: column;
  }

  .detail-header .btn {
    width: 100%;
  }
}
</style>
