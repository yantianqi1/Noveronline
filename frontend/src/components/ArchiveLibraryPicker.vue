<template>
  <div
    class="archive-picker"
    :class="[`variant-${pickerLayout.variant}`, {
      'compact-toolbar': pickerLayout.compactToolbar,
      'single-column-list': pickerLayout.singleColumnList,
      'sticky-filters': pickerLayout.stickyFilters,
    }]"
  >
    <header class="picker-toolbar workbench-card" :class="{ compact: pickerLayout.compactToolbar }">
      <div class="search-field">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="8.5" cy="8.5" r="5.5" />
          <line x1="13" y1="13" x2="18" y2="18" />
        </svg>
        <input v-model="searchText" placeholder="搜索角色、组织、动机、关系..." />
      </div>

      <div class="picker-filters">
        <select v-model="localProjectFilter">
          <option value="">全部项目</option>
          <option v-for="item in projectOptions" :key="item.project_id" :value="item.project_id">
            {{ item.name }}
          </option>
        </select>

        <select v-model="entityType">
          <option value="">全部类型</option>
          <option value="Character">角色</option>
          <option value="Organization">组织</option>
        </select>

        <select v-model="importanceTier">
          <option value="">全部位阶</option>
          <option value="protagonist">主角</option>
          <option value="major">主要</option>
          <option value="supporting">次要</option>
        </select>
      </div>
    </header>

    <div class="picker-summary">
      <div class="summary-left">
        <span v-if="loading">载入中...</span>
        <span v-else>找到 {{ total }} 条档案</span>
        <span v-if="selectedArchives.length" class="selection-count">{{ selectedArchives.length }} 已选</span>
        <span v-if="reindexMessage" class="reindex-msg" :class="{ error: reindexError }">{{ reindexMessage }}</span>
      </div>
      <button v-if="$attrs.onReindex" class="btn subtle reindex-btn" :disabled="reindexBusy" @click="$emit('reindex')">
        {{ reindexBusy ? "刷新中..." : "刷新索引" }}
      </button>
    </div>

    <p v-if="error" class="picker-error">{{ error }}</p>

    <main class="picker-body">
      <section class="picker-list">
        <div class="list-grid">
          <template v-for="item in items" :key="item.archive_id">
            <ArchiveLibraryGridItem
              :active="isArchiveExpanded(expandedArchiveId, item.archive_id) || activeArchiveId === item.archive_id"
              :item="item"
              :selected="selectedIdSet.has(item.archive_id)"
              @expand="handleArchiveExpand(item)"
              @toggle="toggleSelected(item)"
            />

            <div v-if="pickerLayout.showInlineDetail && isArchiveExpanded(expandedArchiveId, item.archive_id)" class="inline-detail-slot">
              <ArchiveLibraryDetailCard
                :archive="resolveInlineDetail(item)"
                :selected="selectedIdSet.has(item.archive_id)"
                @toggle="toggleSelected(resolveInlineDetail(item))"
              />
            </div>
          </template>

          <div v-if="!items.length && !loading" class="picker-empty">
            <h4>未找到符合条件的档案</h4>
            <p>尝试调整搜索关键词或筛选条件</p>
          </div>
        </div>
      </section>

      <section v-if="pickerLayout.showStandaloneDetailPane" class="picker-detail">
        <div class="detail-scroll">
          <ArchiveLibraryDetailCard
            :archive="activeDetail"
            :selected="selectedIdSet.has(activeDetail?.archive_id)"
            @toggle="toggleSelected(activeDetail)"
          />
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { getArchiveLibraryDetail, listArchiveLibrary } from "../api/archive.js";
import { listProjects } from "../api/project.js";
import ArchiveLibraryDetailCard from "./ArchiveLibraryDetailCard.vue";
import ArchiveLibraryGridItem from "./ArchiveLibraryGridItem.vue";
import { resolveArchiveLibraryPickerLayoutVariant } from "../views/shared/archiveLibraryPickerLayout.js";
import { isArchiveExpanded, toggleArchiveExpansion, toggleArchiveSelection } from "../views/shared/worldlineSelectorState.js";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  projectFilter: { type: String, default: "" },
  layoutVariant: { type: String, default: "default" },
  reindexBusy: { type: Boolean, default: false },
  reindexMessage: { type: String, default: "" },
  reindexError: { type: Boolean, default: false },
});

const emit = defineEmits(["update:model-value", "update:project-filter", "reindex"]);

const searchText = ref("");
const localProjectFilter = ref(props.projectFilter);
const entityType = ref("");
const importanceTier = ref("");
const projectOptions = ref([]);
const items = ref([]);
const total = ref(0);
const activeArchiveId = ref("");
const activeDetail = ref(null);
const expandedArchiveId = ref("");
const expandedDetail = ref(null);
const loading = ref(false);
const error = ref("");
let reloadTimer = 0;

const selectedArchives = computed(() => props.modelValue || []);
const selectedIdSet = computed(() => new Set(selectedArchives.value.map((item) => item.archive_id)));
const pickerLayout = computed(() => resolveArchiveLibraryPickerLayoutVariant(props.layoutVariant));
const usesInlineDetail = computed(() => pickerLayout.value.showInlineDetail);

watch(() => props.projectFilter, (value) => { localProjectFilter.value = value || ""; });
watch(localProjectFilter, (value) => { emit("update:project-filter", value); });

watch([searchText, localProjectFilter, entityType, importanceTier], scheduleReload);

async function loadProjects() {
  const response = await listProjects(100);
  projectOptions.value = response.data || [];
}

function scheduleReload() {
  clearTimeout(reloadTimer);
  reloadTimer = window.setTimeout(() => {
    loadItems();
  }, 200);
}

async function syncActiveArchive(nextItems) {
  if (usesInlineDetail.value) {
    syncExpandedArchive(nextItems);
    return;
  }
  if (!nextItems.length) {
    activeArchiveId.value = "";
    activeDetail.value = null;
    return;
  }
  const currentItem = nextItems.find((item) => item.archive_id === activeArchiveId.value);
  if (currentItem) {
    if (!activeDetail.value || activeDetail.value.archive_id !== currentItem.archive_id) {
      activeDetail.value = currentItem;
    }
    return;
  }
  await selectActive(nextItems[0]);
}

function syncExpandedArchive(nextItems) {
  const currentItem = nextItems.find((item) => item.archive_id === expandedArchiveId.value);
  if (!currentItem) {
    expandedArchiveId.value = "";
    expandedDetail.value = null;
    return;
  }
  if (!expandedDetail.value || expandedDetail.value.archive_id !== currentItem.archive_id) {
    expandedDetail.value = currentItem;
  }
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
    await syncActiveArchive(items.value);
  } catch (err) {
    items.value = [];
    total.value = 0;
    activeArchiveId.value = "";
    activeDetail.value = null;
    error.value = err.message || "档案读取失败";
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

async function handleArchiveExpand(item) {
  if (usesInlineDetail.value) {
    await toggleExpanded(item);
    return;
  }
  await selectActive(item);
}

async function toggleExpanded(item) {
  const nextId = toggleArchiveExpansion(expandedArchiveId.value, item?.archive_id);
  if (!nextId) {
    expandedArchiveId.value = "";
    expandedDetail.value = null;
    return;
  }
  expandedArchiveId.value = nextId;
  try {
    const response = await getArchiveLibraryDetail(item.archive_id);
    expandedDetail.value = response.data || item;
  } catch {
    expandedDetail.value = item;
  }
}

function toggleSelected(item) {
  if (!item) {
    return;
  }
  emit("update:model-value", toggleArchiveSelection(selectedArchives.value, item));
}

function reload() {
  return loadItems();
}

function resolveInlineDetail(item) {
  return expandedDetail.value?.archive_id === item.archive_id ? expandedDetail.value : item;
}

defineExpose({ reload });

onMounted(async () => {
  await loadProjects();
  await loadItems();
});
onBeforeUnmount(() => { clearTimeout(reloadTimer); });
</script>

<style scoped src="./ArchiveLibraryPicker.css"></style>
