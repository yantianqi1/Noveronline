<template>
  <section class="archive-layout">
    <article class="workbench-card panel">
      <div class="header-row">
        <div>
          <h2 class="card-title">全局档案库</h2>
          <p>把所有项目已生成的角色与势力档案汇总到一处，统一检索、查看和选择。</p>
        </div>
        <button class="btn" :disabled="busy" @click="rebuildIndex">
          {{ busy ? "刷新中..." : "刷新索引" }}
        </button>
      </div>
      <p class="status-text" :class="{ error: !!error }">{{ error || message }}</p>
      <ArchiveLibraryPicker ref="pickerRef" v-model="selectedArchives" v-model:project-filter="projectFilter" />
    </article>
  </section>
</template>

<script setup>
import { ref } from "vue";

import ArchiveLibraryPicker from "../components/ArchiveLibraryPicker.vue";
import { reindexArchiveLibrary } from "../api/archive.js";

const pickerRef = ref(null);
const selectedArchives = ref([]);
const projectFilter = ref("");
const busy = ref(false);
const message = ref("等待操作");
const error = ref("");

async function rebuildIndex() {
  try {
    busy.value = true;
    error.value = "";
    const response = await reindexArchiveLibrary();
    message.value = `索引已刷新，共 ${response.data?.count || 0} 条档案`;
    await pickerRef.value?.reload();
  } catch (err) {
    error.value = err.message || "刷新索引失败";
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.panel {
  padding: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.panel p,
.status-text {
  color: var(--text-sub);
}

.status-text.error {
  color: #9b4326;
}
</style>
