<template>
  <div v-if="visible" class="configurator-backdrop" @click.self="$emit('close')">
    <article class="configurator-panel workbench-card">
      <header class="configurator-header">
        <div>
          <h3 class="title-ancient">档案模板确认</h3>
          <p class="subtitle">系统已按叙事重要度推荐档位，你只需调整少量对象。</p>
        </div>
        <n-button @click="$emit('close')">关闭</n-button>
      </header>

      <p v-if="error" class="status-box error">{{ error }}</p>
      <div v-else class="configurator-groups">
        <section v-for="group in groupedCandidates" :key="group.kind" class="candidate-group">
          <div class="group-title">{{ group.label }} · {{ group.items.length }}</div>
          <div v-for="item in group.items" :key="item.entity_uuid" class="candidate-card">
            <div class="candidate-head">
              <div>
                <strong>{{ item.display_name }}</strong>
                <div class="candidate-meta mono">
                  推荐 {{ formatArchiveTierLabel(item.recommended_importance_tier) }} · 当前 {{ formatArchiveTierLabel(resolvedTier(item.entity_uuid)) }}
                </div>
              </div>
              <n-select
                :value="resolvedTier(item.entity_uuid)"
                :options="tierSelectOptions"
                style="width: 140px"
                size="small"
                @update:value="(val) => updateTier(item.entity_uuid, val)"
              />
            </div>
            <p class="candidate-summary">{{ item.summary }}</p>
            <div class="candidate-sections">
              <n-tag v-for="section in previewSections(item)" :key="section" size="small" :bordered="false" round>
                {{ formatArchiveSectionLabel(section) }}
              </n-tag>
            </div>
          </div>
        </section>
      </div>

      <footer class="configurator-footer">
        <n-button @click="$emit('close')">取消</n-button>
        <n-button type="primary" :disabled="busy" :loading="busy" @click="confirm">
          确认并生成档案
        </n-button>
      </footer>
    </article>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from "vue";
import { NButton, NSelect, NTag } from "naive-ui";
import {
  formatArchiveKindLabel,
  formatArchiveSectionLabel,
  formatArchiveTierLabel,
  sectionKeysByTier,
  tierSelectOptions,
} from "./archiveTemplateLabels.js";

const props = defineProps({
  visible: { type: Boolean, default: false },
  candidates: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
});

const emit = defineEmits(["close", "confirm"]);

const tierState = reactive({});

watch(
  () => props.candidates,
  (candidates) => {
    Object.keys(tierState).forEach((key) => { delete tierState[key]; });
    for (const item of candidates) {
      tierState[item.entity_uuid] = item.selected_importance_tier || item.recommended_importance_tier || "supporting";
    }
  },
  { immediate: true },
);

const groupedCandidates = computed(() => {
  const groups = new Map();
  for (const item of props.candidates) {
    const kind = item.agent_kind || "generic";
    if (!groups.has(kind)) {
      groups.set(kind, { kind, label: formatArchiveKindLabel(kind), items: [] });
    }
    groups.get(kind).items.push(item);
  }
  return Array.from(groups.values());
});

function resolvedTier(entityUuid) {
  return tierState[entityUuid] || "supporting";
}

function updateTier(entityUuid, value) {
  tierState[entityUuid] = value;
}

function previewSections(item) {
  return sectionKeysByTier[resolvedTier(item.entity_uuid)] || item.template_sections || [];
}

function confirm() {
  emit("confirm", props.candidates.map((item) => ({
    ...item,
    selected_importance_tier: resolvedTier(item.entity_uuid),
  })));
}
</script>

<style scoped>
.configurator-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(41, 30, 18, 0.56);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px;
  z-index: 40;
}

.configurator-panel {
  width: min(920px, 100%);
  max-height: min(88vh, 920px);
  overflow: auto;
  padding: 18px;
}

.configurator-header,
.candidate-head,
.configurator-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.configurator-groups,
.candidate-group,
.candidate-card {
  display: grid;
  gap: 10px;
}

.configurator-groups {
  margin-top: 14px;
}

.candidate-card {
  padding: 12px;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffaf1;
}

.candidate-meta,
.candidate-summary,
.subtitle {
  color: var(--text-sub);
}

.candidate-sections {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.section-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f5ead4;
  color: var(--text-main);
  font-size: 12px;
}

.group-title {
  font-weight: 700;
}

.configurator-footer {
  margin-top: 16px;
}

.status-box.error {
  color: #9b4326;
}
</style>
