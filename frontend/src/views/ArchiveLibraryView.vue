<template>
  <section class="archive-layout">
    <ArchiveLibraryPicker
      ref="pickerRef"
      v-model="selectedArchives"
      v-model:project-filter="projectFilter"
      :reindex-busy="busy"
      :reindex-message="error || message"
      :reindex-error="!!error"
      @reindex="rebuildIndex"
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
const message = ref("");
const error = ref("");

async function rebuildIndex() {
  try {
    busy.value = true;
    error.value = "";
    const response = await reindexArchiveLibrary();
    message.value = `索引已刷新，共 ${response.data?.count || 0} 条`;
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
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px - var(--space-xl) * 2);
  min-height: 520px;
}
</style>
