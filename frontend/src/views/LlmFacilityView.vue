<template>
  <div class="facility-stage stack">
    <!-- Header: Stats & Operations -->
    <header class="facility-header workbench-card">
      <div class="header-main">
        <h2 class="title-ancient">全局设施面板</h2>
        <div class="header-actions">
          <button class="btn subtle small" :disabled="loading" @click="reloadSettings">
            {{ loading ? "同步中..." : "刷新状态" }}
          </button>
        </div>
      </div>
      <div class="stats-row">
        <div class="stat-item"><label>渠道</label><strong class="mono">{{ channels.length }}</strong></div>
        <div class="stat-item"><label>模型</label><strong class="mono">{{ modelCount }}</strong></div>
        <div class="stat-item"><label>绑定</label><strong class="mono">{{ boundModuleCount }}</strong></div>
      </div>
      <div v-if="statusText || errorText" class="message-row">
        <span v-if="statusText" class="status-tag ok">{{ statusText }}</span>
        <span v-if="errorText" class="status-tag danger">{{ errorText }}</span>
      </div>
    </header>

    <div class="facility-grid container-7-5">
      <!-- Channel Management -->
      <LlmChannelPanel
        :channels="channels"
        :submitting="channelBusy"
        :syncing-key="syncingChannelKey"
        :deleting-key="deletingChannelKey"
        @create-channel="handleCreateChannel"
        @update-channel="handleUpdateChannel"
        @sync-channel="handleSyncChannel"
        @delete-channel="handleDeleteChannel"
      />

      <!-- Module Bindings -->
      <LlmModuleBindingsPanel
        :modules="modules"
        :channels="channels"
        :saving-key="savingModuleKey"
        :removing-key="removingModuleKey"
        @save-binding="handleSaveBinding"
        @remove-binding="handleRemoveBinding"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import {
  createLlmChannel,
  deleteLlmModuleBinding,
  deleteLlmChannel,
  getLlmSettings,
  syncLlmChannelModels,
  updateLlmChannel,
  updateLlmModuleBinding,
} from "../api/llm.js";
import LlmChannelPanel from "./llm-facility/LlmChannelPanel.vue";
import LlmModuleBindingsPanel from "./llm-facility/LlmModuleBindingsPanel.vue";

const channels = ref([]);
const modules = ref([]);
const loading = ref(false);
const errorText = ref("");
const statusText = ref("");
const submittingChannelKey = ref("");
const syncingChannelKey = ref("");
const deletingChannelKey = ref("");
const savingModuleKey = ref("");
const removingModuleKey = ref("");

const channelBusy = computed(() => !!submittingChannelKey.value);
const modelCount = computed(() => channels.value.reduce((sum, channel) => sum + (channel.models?.length || 0), 0));
const boundModuleCount = computed(() => modules.value.filter((item) => item.binding).length);

async function reloadSettings() {
  try {
    loading.value = true;
    errorText.value = "";
    const response = await getLlmSettings();
    channels.value = response.data.channels || [];
    modules.value = response.data.modules || [];
  } catch (error) {
    errorText.value = error.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function handleCreateChannel(payload, resetForm) {
  try {
    submittingChannelKey.value = "creating";
    await createLlmChannel(payload);
    resetForm?.();
    statusText.value = "渠道已创建";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "创建失败";
  } finally {
    submittingChannelKey.value = "";
  }
}

async function handleUpdateChannel(channelKey, payload, resetForm) {
  try {
    submittingChannelKey.value = channelKey;
    await updateLlmChannel(channelKey, payload);
    resetForm?.();
    statusText.value = "渠道已更新";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "更新失败";
  } finally {
    submittingChannelKey.value = "";
  }
}

async function handleDeleteChannel(channelKey) {
  if (!window.confirm("确认删除？")) return;
  try {
    deletingChannelKey.value = channelKey;
    await deleteLlmChannel(channelKey);
    statusText.value = "渠道已删除";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "删除失败";
  } finally {
    deletingChannelKey.value = "";
  }
}

async function handleSyncChannel(channelKey) {
  try {
    syncingChannelKey.value = channelKey;
    await syncLlmChannelModels(channelKey);
    statusText.value = "已同步";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "同步失败";
  } finally {
    syncingChannelKey.value = "";
  }
}

async function handleSaveBinding(moduleKey, payload) {
  try {
    savingModuleKey.value = moduleKey;
    await updateLlmModuleBinding(moduleKey, payload);
    statusText.value = "绑定已保存";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "保存失败";
  } finally {
    savingModuleKey.value = "";
  }
}

async function handleRemoveBinding(moduleKey) {
  if (!window.confirm("确认解绑？")) return;
  try {
    removingModuleKey.value = moduleKey;
    await deleteLlmModuleBinding(moduleKey);
    statusText.value = "绑定已解绑";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "解绑失败";
  } finally {
    removingModuleKey.value = "";
  }
}

onMounted(() => { reloadSettings(); });
</script>

<style scoped>
.facility-stage {
  max-width: 1200px;
  margin: 0 auto;
}

.facility-header {
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats-row {
  display: flex;
  gap: var(--space-xl);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--line-soft);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-item label {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.stat-item strong {
  font-size: 18px;
  color: var(--text-main);
}

.message-row {
  display: flex;
  gap: var(--space-sm);
}

@media (max-width: 900px) {
  .facility-grid { grid-template-columns: 1fr; }
}
</style>
