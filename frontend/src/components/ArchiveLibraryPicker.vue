<template>
  <article class="archive-picker">
    <div class="header-row">
      <div>
        <h3 class="card-title">{{ title }}</h3>
        <p class="hint-text">{{ description }}</p>
      </div>
      <span class="chip mono">{{ selectedArchives.length }} 已选</span>
    </div>

    <div class="filters-grid">
      <div class="field">
        <label>搜索</label>
        <input v-model="searchText" placeholder="搜索角色名、动机、关系摘要" />
      </div>
      <div class="field">
        <label>项目</label>
        <select v-model="localProjectFilter">
          <option value="">全部项目</option>
          <option v-for="item in projectOptions" :key="item.project_id" :value="item.project_id">
            {{ item.name }}
          </option>
        </select>
      </div>
      <div class="field">
        <label>类型</label>
        <select v-model="entityType">
          <option value="">全部类型</option>
          <option value="Character">角色</option>
          <option value="Organization">组织</option>
        </select>
      </div>
      <div class="field">
        <label>重要度</label>
        <select v-model="importanceTier">
          <option value="">全部重要度</option>
          <option value="protagonist">主角</option>
          <option value="major">重要角色</option>
          <option value="supporting">配角</option>
          <option value="minor">次要角色</option>
        </select>
      </div>
    </div>

    <div class="selection-row" v-if="selectedArchives.length">
      <button
        v-for="item in selectedArchives"
        :key="item.archive_id"
        class="selection-chip"
        @click="removeSelected(item.archive_id)"
      >
        <span>{{ item.entity_name }}</span>
        <small>{{ item.project_name }}</small>
      </button>
    </div>

    <p class="status-text error" v-if="error">{{ error }}</p>
    <p class="status-text" v-else>{{ loading ? "档案库检索中..." : `共找到 ${total} 条档案` }}</p>

    <div class="picker-grid">
      <div class="list-column">
        <button
          v-for="item in items"
          :key="item.archive_id"
          class="archive-row"
          :class="{ active: activeArchiveId === item.archive_id, selected: selectedIdSet.has(item.archive_id) }"
          @click="selectActive(item)"
        >
          <div class="archive-head">
            <strong>{{ item.entity_name }}</strong>
            <span class="chip mono">{{ formatEntityType(item.entity_type) }}</span>
          </div>
          <div class="archive-meta">
            {{ item.project_name }} · {{ formatImportanceTier(item.importance_tier) }}
          </div>
          <p>{{ item.core_drive || item.entity_role || "暂无档案摘要" }}</p>
        </button>
        <div class="empty" v-if="!items.length && !loading">当前筛选条件下没有档案。</div>
      </div>

      <ArchiveLibraryDetailCard
        :archive="activeDetail"
        :selected="selectedIdSet.has(activeDetail?.archive_id)"
        @toggle="toggleSelected(activeDetail)"
      />
    </div>
  </article>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { getArchiveLibraryDetail, listArchiveLibrary } from "../api/archive.js";
import { listProjects } from "../api/project.js";
import ArchiveLibraryDetailCard from "./ArchiveLibraryDetailCard.vue";
import { formatEntityType, formatImportanceTier } from "../utils/chineseDisplay.js";
import { removeArchiveSelection, toggleArchiveSelection } from "../views/shared/worldlineSelectorState.js";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  projectFilter: { type: String, default: "" },
  title: { type: String, default: "全局档案库" },
  description: { type: String, default: "从所有项目档案里统一检索并选择角色、组织档案。" },
});

const emit = defineEmits(["update:modelValue", "update:projectFilter"]);

const searchText = ref("");
const localProjectFilter = ref(props.projectFilter);
const entityType = ref("");
const importanceTier = ref("");
const projectOptions = ref([]);
const items = ref([]);
const total = ref(0);
const activeArchiveId = ref("");
const activeDetail = ref(null);
const loading = ref(false);
const error = ref("");
let reloadTimer = 0;

const selectedArchives = computed(() => props.modelValue || []);
const selectedIdSet = computed(() => new Set(selectedArchives.value.map((item) => item.archive_id)));

watch(
  () => props.projectFilter,
  (value) => {
    localProjectFilter.value = value || "";
  },
);

watch(localProjectFilter, (value) => {
  emit("update:projectFilter", value);
});

watch([searchText, localProjectFilter, entityType, importanceTier], () => {
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(() => {
    loadItems();
  }, 180);
});

async function loadProjects() {
  const response = await listProjects(100);
  projectOptions.value = response.data || [];
}

async function loadItems() {
  try {
    loading.value = true;
    error.value = "";
    const response = await listArchiveLibrary({
      q: searchText.value.trim(),
      projectId: localProjectFilter.value,
      entityType: entityType.value,
      importanceTier: importanceTier.value,
      limit: 40,
    });
    items.value = response.data?.items || [];
    total.value = response.data?.total || 0;
    if (!activeArchiveId.value && items.value[0]) {
      await selectActive(items.value[0]);
    }
  } catch (err) {
    items.value = [];
    total.value = 0;
    activeDetail.value = null;
    error.value = err.message || "读取全局档案失败";
  } finally {
    loading.value = false;
  }
}

async function selectActive(item) {
  activeArchiveId.value = item.archive_id;
  try {
    const response = await getArchiveLibraryDetail(item.archive_id);
    activeDetail.value = response.data || item;
  } catch (err) {
    activeDetail.value = item;
    error.value = err.message || "读取档案详情失败";
  }
}

function toggleSelected(item) {
  emit("update:modelValue", toggleArchiveSelection(selectedArchives.value, item));
}

function removeSelected(archiveId) {
  emit("update:modelValue", removeArchiveSelection(selectedArchives.value, archiveId));
}

function reload() {
  return loadItems();
}

defineExpose({ reload });

onMounted(async () => {
  await loadProjects();
  await loadItems();
});
</script>

<style scoped>
.archive-picker {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.header-row,
.archive-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.hint-text,
.archive-meta,
.status-text,
.empty {
  color: var(--text-sub);
}

.filters-grid,
.picker-grid {
  display: grid;
  gap: 12px;
}

.filters-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.picker-grid {
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.9fr);
}

.selection-row,
.list-column {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.selection-chip,
.archive-row {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffaf1;
}

.selection-chip {
  text-align: left;
  padding: 9px 12px;
  cursor: pointer;
}

.selection-chip small {
  margin-left: 8px;
  color: var(--text-sub);
}

.archive-row {
  text-align: left;
  padding: 12px;
  cursor: pointer;
}

.archive-row.active {
  border-color: var(--line-strong);
}

.archive-row.selected {
  background: #fff1de;
}

.archive-row p,
.detail-block p {
  margin: 8px 0 0;
}

.status-text.error {
  color: #9b4326;
}

@media (max-width: 1100px) {
  .filters-grid,
  .picker-grid {
    grid-template-columns: 1fr;
  }
}
</style>
