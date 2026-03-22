<template>
  <div class="archive-museum stack">
    <!-- Top Filter Bar -->
    <header class="museum-header workbench-card">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input v-model="searchText" placeholder="搜寻角色、组织、动机、关系..." />
      </div>
      <div class="filter-controls">
        <div class="filter-group">
          <label>卷宗</label>
          <select v-model="localProjectFilter">
            <option value="">全部</option>
            <option v-for="item in projectOptions" :key="item.project_id" :value="item.project_id">
              {{ item.name }}
            </option>
          </select>
        </div>
        <div class="filter-group">
          <label>类别</label>
          <select v-model="entityType">
            <option value="">全部</option>
            <option value="Character">角色</option>
            <option value="Organization">组织</option>
          </select>
        </div>
        <div class="filter-group">
          <label>位阶</label>
          <select v-model="importanceTier">
            <option value="">全部</option>
            <option value="protagonist">主角</option>
            <option value="major">主要</option>
            <option value="supporting">次要</option>
          </select>
        </div>
      </div>
    </header>

    <!-- Main Content: Master-Detail -->
    <main class="museum-grid">
      <!-- Master List -->
      <section class="museum-list stack">
        <div class="list-status">
          <span v-if="loading" class="mono">载入中...</span>
          <span v-else class="mono">找到 {{ total }} 条档案</span>
          <div class="selection-summary" v-if="selectedArchives.length">
            {{ selectedArchives.length }} 已选
          </div>
        </div>

        <div class="scroll-list stack">
          <article
            v-for="item in items"
            :key="item.archive_id"
            class="museum-item"
            :class="{ active: activeArchiveId === item.archive_id, selected: selectedIdSet.has(item.archive_id) }"
            @click="selectActive(item)"
          >
            <div class="item-main">
              <div class="item-header">
                <h4 class="item-name">{{ item.entity_name }}</h4>
                <span class="status-tag mono" :class="item.entity_type.toLowerCase()">{{ formatEntityType(item.entity_type) }}</span>
              </div>
              <div class="item-meta">
                <span class="project-tag">{{ item.project_name }}</span>
                <span class="tier-tag">{{ formatImportanceTier(item.importance_tier) }}</span>
              </div>
              <p class="item-desc">{{ item.core_drive || item.entity_role || "档案尚简。" }}</p>
            </div>
            <div class="item-action" @click.stop="toggleSelected(item)">
              <div class="check-box" :class="{ checked: selectedIdSet.has(item.archive_id) }"></div>
            </div>
          </article>
          <div v-if="!items.length && !loading" class="empty-museum">
            <div class="empty-icon">📜</div>
            <p>未找到符合条件的档案</p>
          </div>
        </div>
      </section>

      <!-- Detail Inspector -->
      <aside class="museum-inspector">
        <ArchiveLibraryDetailCard
          :archive="activeDetail"
          :selected="selectedIdSet.has(activeDetail?.archive_id)"
          @toggle="toggleSelected(activeDetail)"
        />
      </aside>
    </main>
  </div>
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

watch(() => props.projectFilter, (v) => { localProjectFilter.value = v || ""; });
watch(localProjectFilter, (v) => { emit("update:projectFilter", v); });

watch([searchText, localProjectFilter, entityType, importanceTier], () => {
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(() => { loadItems(); }, 200);
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
      limit: 60,
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
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function selectActive(item) {
  activeArchiveId.value = item.archive_id;
  try {
    const response = await getArchiveLibraryDetail(item.archive_id);
    activeDetail.value = response.data || item;
  } catch {
    activeDetail.value = item;
  }
}

function toggleSelected(item) {
  if (!item) return;
  emit("update:modelValue", toggleArchiveSelection(selectedArchives.value, item));
}

function reload() { return loadItems(); }
defineExpose({ reload });

onMounted(async () => {
  await loadProjects();
  await loadItems();
});
</script>

<style scoped>
.archive-museum {
  height: calc(100vh - 160px);
  display: flex;
  flex-direction: column;
}

.museum-header {
  padding: var(--space-md) var(--space-lg);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-lg);
  z-index: 5;
}

.search-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  background: var(--bg-paper);
  padding: 0 var(--space-md);
  border-radius: var(--radius-full);
  border: 1px solid var(--line-soft);
}

.search-box input {
  border: none;
  background: transparent;
  padding: 10px 0;
  width: 100%;
  font-size: 15px;
}

.search-box input:focus { outline: none; }

.filter-controls {
  display: flex;
  gap: var(--space-md);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 13px;
  color: var(--text-sub);
}

.filter-group select {
  border: 1px solid var(--line-soft);
  background: transparent;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.museum-grid {
  display: grid;
  grid-template-columns: 1fr 420px;
  gap: var(--space-lg);
  flex: 1;
  min-height: 0;
}

.museum-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.list-status {
  display: flex;
  justify-content: space-between;
  padding: 0 var(--space-sm) var(--space-sm);
  font-size: 12px;
  color: var(--text-dim);
}

.scroll-list {
  flex: 1;
  overflow-y: auto;
  padding-right: var(--space-sm);
}

.museum-item {
  display: flex;
  background: #fff;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  cursor: pointer;
  transition: all 0.2s ease;
  gap: var(--space-md);
}

.museum-item:hover {
  transform: translateX(4px);
  border-color: var(--line-medium);
  box-shadow: var(--shadow-sm);
}

.museum-item.active {
  border-color: var(--accent-copper);
  background: var(--bg-paper-warm);
}

.item-main { flex: 1; min-width: 0; }

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs);
}

.item-name {
  font-size: 18px;
  font-family: "ZCOOL XiaoWei", serif;
  color: var(--text-main);
}

.item-meta {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
  font-size: 12px;
}

.project-tag { color: var(--text-dim); }
.tier-tag { color: var(--accent-copper); font-weight: 600; }

.item-desc {
  font-size: 13px;
  color: var(--text-sub);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-action {
  display: flex;
  align-items: center;
}

.check-box {
  width: 20px;
  height: 20px;
  border: 2px solid var(--line-medium);
  border-radius: 4px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.check-box.checked {
  background: var(--accent-copper);
  border-color: var(--accent-copper);
}

.check-box.checked::after {
  content: '✓';
  color: #fff;
  font-size: 14px;
}

.museum-inspector {
  min-height: 0;
  overflow-y: auto;
}

.empty-museum {
  padding: var(--space-xl);
  text-align: center;
  color: var(--text-dim);
}

.empty-icon { font-size: 48px; margin-bottom: var(--space-md); }

@media (max-width: 1200px) {
  .museum-grid { grid-template-columns: 1fr; }
  .museum-inspector { display: none; }
}
</style>
