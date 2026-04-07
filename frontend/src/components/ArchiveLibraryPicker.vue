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
        <n-input v-model:value="searchText" placeholder="搜索角色、组织、动机、关系..." clearable />
      </div>

      <div class="picker-filters">
        <n-select
          v-model:value="localProjectFilter"
          :options="projectSelectOptions"
          placeholder="全部项目"
          clearable
          style="min-width: 140px"
        />

        <n-select
          v-model:value="entityType"
          :options="entityTypeOptions"
          placeholder="全部类型"
          clearable
          style="min-width: 120px"
        />

        <n-select
          v-model:value="importanceTier"
          :options="importanceTierOptions"
          placeholder="全部位阶"
          clearable
          style="min-width: 120px"
        />
      </div>
    </header>

    <div class="picker-summary">
      <div class="summary-left">
        <span v-if="loading">载入中...</span>
        <span v-else>找到 {{ total }} 条档案</span>
        <span v-if="selectedArchives.length" class="selection-count">{{ selectedArchives.length }} 已选</span>
        <span v-if="reindexMessage" class="reindex-msg" :class="{ error: reindexError }">{{ reindexMessage }}</span>
      </div>
      <n-button v-if="$attrs.onReindex" quaternary :loading="reindexBusy" @click="$emit('reindex')">
        {{ reindexBusy ? "刷新中..." : "刷新索引" }}
      </n-button>
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

          <n-empty v-if="!items.length && !loading" description="尝试调整搜索关键词或筛选条件">
            <template #extra><span>未找到符合条件的档案</span></template>
          </n-empty>
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
import { NButton, NEmpty, NInput, NSelect } from "naive-ui";

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

const projectSelectOptions = computed(() =>
  projectOptions.value.map((p) => ({ label: p.name || p.project_id, value: p.project_id })),
);

const entityTypeOptions = [
  { label: "角色", value: "character" },
  { label: "组织", value: "organization" },
  { label: "关系", value: "relationship" },
];

const importanceTierOptions = [
  { label: "主角", value: "protagonist" },
  { label: "主要", value: "major" },
  { label: "次要", value: "supporting" },
  { label: "配角", value: "minor" },
];

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
