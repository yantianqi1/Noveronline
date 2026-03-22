<template>
  <section class="facility-grid">
    <article class="workbench-card panel intro-card">
      <h2 class="card-title">全局设施面板</h2>
      <p>这里统一管理 LLM 渠道、模型缓存和业务模块绑定，后端后续的新调用都会走这里的最新配置。</p>
      <div class="kpis">
        <div class="kpi"><span class="mono">渠道数</span><strong>{{ channels.length }}</strong></div>
        <div class="kpi"><span class="mono">缓存模型数</span><strong>{{ modelCount }}</strong></div>
        <div class="kpi"><span class="mono">已绑定模块</span><strong>{{ boundModuleCount }}</strong></div>
      </div>
      <div class="toolbar-row">
        <button class="btn" :disabled="loading" @click="reloadSettings">{{ loading ? "刷新中..." : "刷新快照" }}</button>
      </div>
      <p v-if="statusText" class="status-text">{{ statusText }}</p>
      <p v-if="errorText" class="error-text">{{ errorText }}</p>
    </article>

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

    <LlmModuleBindingsPanel
      :modules="modules"
      :channels="channels"
      :saving-key="savingModuleKey"
      @save-binding="handleSaveBinding"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import {
  createLlmChannel,
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

const channelBusy = computed(() => !!submittingChannelKey.value);
const modelCount = computed(() => channels.value.reduce((sum, channel) => sum + (channel.models?.length || 0), 0));
const boundModuleCount = computed(() => modules.value.filter((item) => item.binding).length);

async function reloadSettings(message = "") {
  try {
    loading.value = true;
    errorText.value = "";
    if (message) {
      statusText.value = message;
    }
    const response = await getLlmSettings();
    channels.value = response.data.channels || [];
    modules.value = response.data.modules || [];
  } catch (error) {
    errorText.value = error.message || "设施面板加载失败";
  } finally {
    loading.value = false;
  }
}

async function handleCreateChannel(payload, resetForm) {
  try {
    submittingChannelKey.value = "creating";
    errorText.value = "";
    await createLlmChannel(payload);
    resetForm?.();
    statusText.value = "渠道已创建";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "创建渠道失败";
  } finally {
    submittingChannelKey.value = "";
  }
}

async function handleUpdateChannel(channelKey, payload, resetForm) {
  try {
    submittingChannelKey.value = channelKey;
    errorText.value = "";
    await updateLlmChannel(channelKey, payload);
    resetForm?.();
    statusText.value = "渠道已更新";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "更新渠道失败";
  } finally {
    submittingChannelKey.value = "";
  }
}

async function handleDeleteChannel(channelKey) {
  if (!window.confirm("确认删除这个渠道吗？相关模块绑定也会一并失效。")) {
    return;
  }
  try {
    deletingChannelKey.value = channelKey;
    errorText.value = "";
    await deleteLlmChannel(channelKey);
    statusText.value = "渠道已删除";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "删除渠道失败";
  } finally {
    deletingChannelKey.value = "";
  }
}

async function handleSyncChannel(channelKey) {
  try {
    syncingChannelKey.value = channelKey;
    errorText.value = "";
    await syncLlmChannelModels(channelKey);
    statusText.value = "模型列表已同步";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "同步模型失败";
  } finally {
    syncingChannelKey.value = "";
  }
}

async function handleSaveBinding(moduleKey, payload) {
  try {
    savingModuleKey.value = moduleKey;
    errorText.value = "";
    await updateLlmModuleBinding(moduleKey, payload);
    statusText.value = "模块绑定已保存";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "保存模块绑定失败";
  } finally {
    savingModuleKey.value = "";
  }
}

onMounted(() => {
  reloadSettings();
});
</script>

<style scoped>
.facility-grid {
  display: grid;
  gap: 14px;
}

.panel {
  padding: 18px;
}

.intro-card p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.kpi {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffbf0;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kpi span {
  color: var(--text-sub);
  font-size: 12px;
}

.status-text,
.error-text {
  margin: 12px 0 0;
}

.status-text {
  color: var(--accent-green);
}

.error-text {
  color: #b1452f;
}

@media (max-width: 900px) {
  .kpis {
    grid-template-columns: 1fr;
  }
}
</style>
