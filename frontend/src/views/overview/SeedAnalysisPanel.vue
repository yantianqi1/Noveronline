<template>
  <article class="workbench-card panel seed-panel">
    <h2 class="card-title">种子分析</h2>
    <p>读取项目种子后，快速查看角色、组织、关系抽取结果，可用于后续世界线建模。</p>
    <div class="field">
      <label>项目</label>
      <select v-model="seedProjectId" :disabled="!seedProjectOptions.length || seedBusy">
        <option value="">{{ seedProjectPlaceholder }}</option>
        <option v-for="item in seedProjectOptions" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
      <p class="field-hint" v-if="selectedSeedProject">
        已从项目档案簿同步当前可选项目，当前选择：
        <span class="mono">{{ selectedSeedProject.project_id }}</span>
      </p>
    </div>
    <div class="toolbar-row">
      <button class="btn" :disabled="seedBusy" @click="emitRefresh">刷新项目</button>
      <button class="btn primary" :disabled="seedBusy || !seedProjectId" @click="analyzeSeed()">
        运行种子分析
      </button>
      <span class="mono">{{ seedBusy ? "分析中..." : seedProjectHint }}</span>
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
          <strong>{{ item.name }}</strong>
          <span class="mono">{{ formatImportanceTier(item.importance_tier) }}</span>
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
  buildSeedProjectOptions,
  resolveSeedProjectId,
  resolveSeedProjectSelection,
} from "./seedProjectId";
import {
  formatImportanceTier,
  formatOrganizationType,
} from "../../utils/chineseDisplay";

const props = defineProps({
  projects: { type: Array, default: () => [] },
});

const emit = defineEmits(["refresh-projects"]);

const seedProjectId = ref("");
const seedResult = ref(null);
const seedError = ref("");
const seedBusy = ref(false);

const seedProjectOptions = computed(() => buildSeedProjectOptions(props.projects));
const selectedSeedProject = computed(() =>
  props.projects.find((item) => item.project_id === seedProjectId.value) || null,
);
const seedProjectPlaceholder = computed(() =>
  seedProjectOptions.value.length ? "请选择要分析的项目" : "暂无可分析项目",
);
const seedProjectHint = computed(() => {
  if (!seedProjectOptions.value.length) {
    return "请先上传小说种子，系统会自动创建项目";
  }
  if (!seedProjectId.value) {
    return "请先从列表里选择一个项目";
  }
  return "项目已从档案簿列表同步，无需手动填写 ID";
});
const seedCharacterCount = computed(() => seedResult.value?.characters?.length || 0);
const seedOrganizationCount = computed(() => seedResult.value?.organizations?.length || 0);
const seedRelationCount = computed(() => seedResult.value?.relations?.length || 0);
const seedCharactersPreview = computed(() => (seedResult.value?.characters || []).slice(0, 6));
const seedOrganizationsPreview = computed(() => (seedResult.value?.organizations || []).slice(0, 6));

function emitRefresh() {
  emit("refresh-projects", { preferredProjectId: seedProjectId.value });
}

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
  seedProjectId.value = resolveSeedProjectSelection(props.projects, projectId);
  await analyzeSeed(projectId);
}

watch(
  () => props.projects,
  (projects) => {
    seedProjectId.value = resolveSeedProjectSelection(projects, seedProjectId.value);
  },
  { immediate: true },
);

watch(seedProjectId, (value, previousValue) => {
  if (value === previousValue) {
    return;
  }
  seedResult.value = null;
  seedError.value = "";
});

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
  justify-content: space-between;
  gap: 10px;
}

.seed-item:first-of-type {
  border-top: none;
}

.seed-error {
  margin-top: 10px;
  color: #9b4326;
}

.field-hint {
  margin: 8px 0 0;
  color: var(--text-sub);
  font-size: 12px;
}

@media (max-width: 980px) {
  .seed-lists {
    grid-template-columns: 1fr;
  }
}
</style>
