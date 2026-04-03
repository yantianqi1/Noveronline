<template>
  <article class="workbench-card panel seed-panel">
    <h2 class="card-title">分析结果</h2>
    <p>查看角色、组织、关系的分析结果。</p>
    <div class="toolbar-row">
      <button class="btn primary" :disabled="seedBusy || !seedProjectId" @click="analyzeSeed()">
        {{ seedBusy ? "分析中..." : "运行分析" }}
      </button>
    </div>

    <div class="kpis seed-kpis" v-if="seedResult">
      <div class="kpi"><span class="mono">角色</span><strong>{{ seedCharacterCount }}</strong></div>
      <div class="kpi"><span class="mono">组织</span><strong>{{ seedOrganizationCount }}</strong></div>
      <div class="kpi"><span class="mono">关系</span><strong>{{ seedRelationCount }}</strong></div>
    </div>

    <div class="seed-lists" v-if="seedResult">
      <div class="seed-col">
        <div class="seed-title">角色列表（预览）</div>
        <div class="seed-item" v-for="item in seedCharactersPreview" :key="item.name">
          <div class="seed-item-main">
            <strong>{{ item.name }}</strong>
            <span class="mono">{{ formatImportanceTier(item.importance_tier) }}</span>
          </div>
          <div class="seed-item-detail" v-if="item.personality_traits?.length || item.speech_style">
            <span v-if="item.personality_traits?.length" class="trait-chips">
              <span class="trait-chip" v-for="trait in item.personality_traits.slice(0, 3)" :key="trait">{{ trait }}</span>
            </span>
            <span v-if="item.speech_style" class="speech-hint">{{ item.speech_style }}</span>
          </div>
        </div>
      </div>
      <div class="seed-col">
        <div class="seed-title">组织列表（预览）</div>
        <div class="seed-item" v-for="item in seedOrganizationsPreview" :key="item.name">
          <strong>{{ item.name }}</strong>
          <span class="mono">{{ formatOrganizationType(item.organization_type) }}</span>
        </div>
      </div>
    </div>

    <p class="seed-error" v-if="seedError">{{ seedError }}</p>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { runSeedAnalysis } from "../../api/novel";
import {
  resolveSeedProjectId,
} from "./seedProjectId";
import {
  formatImportanceTier,
  formatOrganizationType,
} from "../../utils/chineseDisplay";

const props = defineProps({
  projects: { type: Array, default: () => [] },
  projectId: { type: String, default: "" },
});

const seedProjectId = ref(props.projectId);
const seedResult = ref(null);
const seedError = ref("");
const seedBusy = ref(false);
const seedCharacterCount = computed(() => seedResult.value?.characters?.length || 0);
const seedOrganizationCount = computed(() => seedResult.value?.organizations?.length || 0);
const seedRelationCount = computed(() => seedResult.value?.relations?.length || 0);
const seedCharactersPreview = computed(() => (seedResult.value?.characters || []).slice(0, 6));
const seedOrganizationsPreview = computed(() => (seedResult.value?.organizations || []).slice(0, 6));

async function analyzeSeed(projectIdOverride = "") {
  try {
    seedBusy.value = true;
    seedError.value = "";
    const targetProjectId = resolveSeedProjectId(projectIdOverride, seedProjectId.value);
    const response = await runSeedAnalysis({
      projectId: targetProjectId,
    });
    seedResult.value = response.data || null;
  } catch (error) {
    seedError.value = error.message || "种子分析请求失败";
    seedResult.value = null;
  } finally {
    seedBusy.value = false;
  }
}

async function runForProject(projectId) {
  seedProjectId.value = projectId;
  await analyzeSeed(projectId);
}

watch(
  () => props.projectId,
  (value) => {
    if (value && value !== seedProjectId.value) {
      seedProjectId.value = value;
      seedResult.value = null;
      seedError.value = "";
    }
  },
);

defineExpose({ runForProject });
</script>

<style scoped>
.panel {
  padding: 18px;
}

.panel p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.seed-panel {
  grid-column: 1 / -1;
}

.kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.kpi {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffbf0;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kpi span {
  color: var(--text-sub);
  font-size: 12px;
}

.kpi strong {
  font-size: 16px;
}

.seed-kpis {
  margin-top: 12px;
}

.seed-lists {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.seed-col {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffaf0;
  padding: 10px;
}

.seed-title {
  font-weight: 700;
  margin-bottom: 6px;
}

.seed-item {
  border-top: 1px dashed var(--line-soft);
  padding: 7px 0;
  display: flex;
  flex-direction: column;
}

.seed-item-main {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.seed-item-detail {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.trait-chips {
  display: flex;
  gap: 3px;
}

.trait-chip {
  background: rgba(176, 125, 75, 0.1);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  color: var(--accent-copper-deep);
}

.speech-hint {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}

.seed-item:first-of-type {
  border-top: none;
}

.seed-error {
  margin-top: 10px;
  color: #9b4326;
}

@media (max-width: 980px) {
  .seed-lists {
    grid-template-columns: 1fr;
  }
}
</style>
