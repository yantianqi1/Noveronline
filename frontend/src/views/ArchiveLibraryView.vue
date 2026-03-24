<template>
  <section class="archive-layout">
    <header class="archive-header">
      <div class="header-copy">
        <p class="header-kicker mono">GLOBAL ARCHIVE INDEX</p>
        <h2 class="card-title">全局档案库</h2>
        <p>把所有项目已生成的角色与势力档案汇总到一处，统一检索、查看和选择。</p>
      </div>

      <button class="btn" :disabled="busy" @click="rebuildIndex">
        {{ busy ? "刷新中..." : "刷新索引" }}
      </button>
    </header>

    <p class="status-text" :class="{ error: !!error }">{{ error || message }}</p>

    <ArchiveLibraryPicker
      ref="pickerRef"
      v-model="selectedArchives"
      v-model:project-filter="projectFilter"
    />
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
.archive-layout {
  display: grid;
  gap: 10px;
}

.archive-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.header-copy {
  display: grid;
  gap: 6px;
}

.header-kicker {
  margin: 0;
  color: var(--accent-copper-deep);
  letter-spacing: 0.14em;
  font-size: 11px;
}

.header-copy p,
.status-text {
  margin: 0;
  color: var(--text-sub);
}

.status-text.error {
  color: var(--accent-seal);
}

@media (max-width: 900px) {
  .archive-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
