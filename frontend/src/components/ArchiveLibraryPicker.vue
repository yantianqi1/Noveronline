<template>
  <div class="archive-museum stack">
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

    <main class="museum-grid">
      <section class="museum-list stack">
        <div class="list-status">
          <span v-if="loading" class="mono">载入中...</span>
          <span v-else class="mono">找到 {{ total }} 条档案</span>
          <div class="selection-summary" v-if="selectedArchives.length">
            {{ selectedArchives.length }} 已选
          </div>
        </div>
        <p v-if="error" class="error-text">{{ error }}</p>

        <div class="scroll-list">
          <ArchiveLibraryGridItem
            v-for="item in items"
            :key="item.archive_id"
            :active="activeArchiveId === item.archive_id"
            :item="item"
            :selected="selectedIdSet.has(item.archive_id)"
            @select="selectActive(item)"
            @toggle="toggleSelected(item)"
          />
          <div v-if="!items.length && !loading" class="empty-museum">
            <div class="empty-icon">📜</div>
            <p>未找到符合条件的档案</p>
          </div>
        </div>
      </section>

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
import ArchiveLibraryGridItem from "./ArchiveLibraryGridItem.vue";
import { toggleArchiveSelection } from "../views/shared/worldlineSelectorState.js";

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

<style scoped src="./ArchiveLibraryPicker.css"></style>
