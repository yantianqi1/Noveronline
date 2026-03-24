<template>
  <div
    ref="stageRef"
    class="archive-museum"
    :class="[
      layoutMode,
      `variant-${pickerLayout.variant}`,
      {
        resizing,
        'compact-toolbar': pickerLayout.compactToolbar,
        'single-column-list': pickerLayout.singleColumnList,
        'viewport-bound': pickerLayout.bindViewportHeight,
      },
    ]"
    :style="stageStyle"
  >
    <header class="museum-toolbar workbench-card" :class="{ compact: pickerLayout.compactToolbar }">
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

    <main class="museum-stage" :class="{ 'no-divider': !pickerLayout.enableResize }">
      <section class="archive-pane list-pane">
        <div class="pane-head">
          <div class="pane-copy">
            <p class="pane-kicker mono">ARCHIVE SHELVES</p>
            <h3>档案目录</h3>
            <p>统一检索、筛选并挑选进入会话的角色与组织档案。</p>
          </div>
          <div class="list-summary">
            <span v-if="loading" class="mono">载入中...</span>
            <span v-else class="mono">找到 {{ total }} 条档案</span>
            <span v-if="selectedArchives.length" class="selection-summary">
              {{ selectedArchives.length }} 已选
            </span>
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

      <button
        v-if="pickerLayout.enableResize"
        class="museum-divider"
        type="button"
        aria-label="拖拽调整档案列表与详情宽度"
        aria-orientation="vertical"
        @pointerdown.prevent="beginResize"
      >
        <span></span>
      </button>

      <aside class="archive-pane detail-pane">
        <div class="pane-head detail-head">
          <div class="pane-copy">
            <p class="pane-kicker mono">DOSSIER VIEW</p>
            <h3>{{ activeDetail ? activeDetail.entity_name : "档案详情" }}</h3>
            <p>右侧保留完整档案，便于边筛选边确认人物、势力与关系脉络。</p>
          </div>
          <p class="detail-hint">{{ activeDetail ? "当前聚焦卷宗" : "等待选中档案" }}</p>
        </div>

        <div class="detail-scroll">
          <ArchiveLibraryDetailCard
            :archive="activeDetail"
            :selected="selectedIdSet.has(activeDetail?.archive_id)"
            @toggle="toggleSelected(activeDetail)"
          />
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { getArchiveLibraryDetail, listArchiveLibrary } from "../api/archive.js";
import { listProjects } from "../api/project.js";
import ArchiveLibraryDetailCard from "./ArchiveLibraryDetailCard.vue";
import ArchiveLibraryGridItem from "./ArchiveLibraryGridItem.vue";
import { useArchiveLibraryLayout } from "../composables/useArchiveLibraryLayout.js";
import { resolveArchiveLibraryPickerLayoutVariant } from "../views/shared/archiveLibraryPickerLayout.js";
import { toggleArchiveSelection } from "../views/shared/worldlineSelectorState.js";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  projectFilter: { type: String, default: "" },
  layoutVariant: { type: String, default: "default" },
});

const emit = defineEmits(["update:model-value", "update:project-filter"]);

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
const pickerLayout = computed(() => resolveArchiveLibraryPickerLayoutVariant(props.layoutVariant));
const { beginResize, layoutMode, resizing, stageRef, stageStyle } = useArchiveLibraryLayout();

watch(() => props.projectFilter, (value) => {
  localProjectFilter.value = value || "";
});

watch(localProjectFilter, (value) => {
  emit("update:project-filter", value);
});

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

function toggleSelected(item) {
  if (!item) {
    return;
  }
  emit("update:model-value", toggleArchiveSelection(selectedArchives.value, item));
}

function reload() {
  return loadItems();
}

defineExpose({ reload });

onMounted(async () => {
  await loadProjects();
  await loadItems();
});

onBeforeUnmount(() => {
  clearTimeout(reloadTimer);
});
</script>

<style scoped src="./ArchiveLibraryPicker.css"></style>
