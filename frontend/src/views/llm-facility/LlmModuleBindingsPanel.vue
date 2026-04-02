<template>
  <article class="workbench-card panel">
    <div class="panel-head">
      <div>
        <h2 class="card-title">模块绑定</h2>
        <p>为每个业务模块指定唯一的“渠道 + 模型”组合，保存后对后续调用立即生效，并继承该渠道的并发设置。</p>
      </div>
    </div>

    <div class="binding-list">
      <section v-for="module in modules" :key="module.module_key" class="binding-card">
        <div class="binding-top">
          <div>
            <strong>{{ module.label }}</strong>
            <p>{{ module.description }}</p>
          </div>
          <span class="chip mono">{{ module.module_key }}</span>
        </div>

        <div class="binding-grid">
          <div class="field">
            <label>渠道</label>
            <select :value="drafts[module.module_key].channelKey" @change="handleChannelChange(module.module_key, $event.target.value)">
              <option value="">请选择渠道</option>
              <option
                v-for="channel in channels"
                :key="channel.channel_key"
                :value="channel.channel_key"
                :disabled="!channel.is_enabled"
              >
                {{ channel.name }}{{ channel.is_enabled ? "" : "（停用）" }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>模型</label>
            <select :value="drafts[module.module_key].modelId" @change="handleModelChange(module.module_key, $event.target.value)">
              <option value="">请选择模型</option>
              <option
                v-for="model in availableModels(drafts[module.module_key].channelKey)"
                :key="model.model_id"
                :value="model.model_id"
              >
                {{ model.model_id }}
              </option>
            </select>
          </div>
        </div>

        <div class="binding-meta">
          <span class="status" :class="bindingStatusClass(module)">
            {{ bindingStatusText(module) }}
          </span>
          <span class="mono binding-current">
            {{ currentBindingText(module) }}
          </span>
          <span v-if="module.binding?.updated_at" class="mono binding-stamp">
            更新时间：{{ module.binding.updated_at }}
          </span>
        </div>
        <p v-if="bindingWarning(module)" class="binding-warning">{{ bindingWarning(module) }}</p>

        <div class="toolbar-row">
          <button
            class="btn primary"
            :disabled="saveDisabled(module.module_key) || savingKey === module.module_key"
            @click="saveBinding(module.module_key)"
          >
            {{ savingKey === module.module_key ? "保存中..." : "保存绑定" }}
          </button>
          <button
            class="btn"
            :disabled="!module.binding || removingKey === module.module_key"
            @click="removeBinding(module.module_key)"
          >
            {{ removingKey === module.module_key ? "解绑中..." : "解绑" }}
          </button>
        </div>
      </section>
      <div v-if="!modules.length" class="empty">模块注册表为空，暂时没有可绑定的大模型模块。</div>
    </div>
  </article>
</template>

<script setup>
import { ref, watch } from "vue";

import {
  syncBindingDrafts,
  updateBindingDraft,
} from "./llmModuleBindingDrafts.js";

const props = defineProps({
  modules: { type: Array, required: true },
  channels: { type: Array, required: true },
  savingKey: { type: String, default: "" },
  removingKey: { type: String, default: "" },
});

const emit = defineEmits(["save-binding", "remove-binding"]);

const drafts = ref({});
const dirtyKeys = ref(new Set());

watch(
  () => props.modules,
  (modules) => {
    const nextState = syncBindingDrafts({
      modules,
      drafts: drafts.value,
      dirtyKeys: dirtyKeys.value,
    });
    drafts.value = nextState.drafts;
    dirtyKeys.value = nextState.dirtyKeys;
  },
  { immediate: true, deep: true },
);

function availableModels(channelKey) {
  return channelByKey(channelKey)?.models || [];
}

function channelByKey(channelKey) {
  return props.channels.find((item) => item.channel_key === channelKey);
}

function handleChannelChange(moduleKey, channelKey) {
  applyDraftPatch(moduleKey, { channelKey });
  const models = availableModels(channelKey);
  const currentModelId = drafts.value[moduleKey]?.modelId || "";
  const hasCurrentModel = models.some((item) => item.model_id === currentModelId);
  applyDraftPatch(moduleKey, {
    modelId: hasCurrentModel ? currentModelId : (models[0]?.model_id || ""),
  });
}

function handleModelChange(moduleKey, modelId) {
  applyDraftPatch(moduleKey, { modelId });
}

function currentBindingText(module) {
  if (!module.binding) {
    return "尚未配置";
  }
  const channelName = channelByKey(module.binding.channel_key)?.name || module.binding.channel_key;
  return `${channelName} / ${module.binding.model_id}`;
}

function bindingStatusText(module) {
  if (!module.binding) {
    return "未绑定";
  }
  return bindingWarning(module) ? "绑定失效" : "已绑定";
}

function bindingStatusClass(module) {
  if (!module.binding) {
    return "warn";
  }
  return bindingWarning(module) ? "warn" : "ok";
}

function bindingWarning(module) {
  if (!module.binding) {
    return "";
  }
  const channel = channelByKey(module.binding.channel_key);
  if (!channel) {
    return "当前绑定渠道已不存在，请改绑或解绑。";
  }
  if (!channel.is_enabled) {
    return "当前绑定渠道已停用，请改绑或解绑。";
  }
  return "";
}

function saveDisabled(moduleKey) {
  const draft = drafts.value[moduleKey];
  if (!draft?.channelKey || !draft?.modelId) {
    return true;
  }
  const channel = channelByKey(draft.channelKey);
  return !channel || !channel.is_enabled;
}

function saveBinding(moduleKey) {
  if (saveDisabled(moduleKey)) {
    return;
  }
  emit("save-binding", moduleKey, {
    channel_key: drafts.value[moduleKey].channelKey,
    model_id: drafts.value[moduleKey].modelId,
  });
}

function removeBinding(moduleKey) {
  emit("remove-binding", moduleKey);
}

function applyDraftPatch(moduleKey, patch) {
  const nextState = updateBindingDraft({
    drafts: drafts.value,
    dirtyKeys: dirtyKeys.value,
    moduleKey,
    patch,
  });
  drafts.value = nextState.drafts;
  dirtyKeys.value = nextState.dirtyKeys;
}
</script>

<style scoped>
.panel {
  padding: 18px;
}

.panel-head p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.binding-list {
  margin-top: 16px;
  display: grid;
  gap: 12px;
}

.binding-card {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  padding: 14px;
  background:
    linear-gradient(180deg, rgba(255, 250, 241, 0.98), rgba(255, 255, 251, 0.98)),
    radial-gradient(circle at top right, rgba(39, 90, 120, 0.08), transparent 32%);
}

.binding-top,
.binding-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}

.binding-top p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.binding-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.binding-meta {
  margin-top: 12px;
  flex-wrap: wrap;
}

.binding-current {
  color: var(--text-sub);
  font-size: 12px;
}

.binding-stamp {
  color: var(--text-sub);
  font-size: 12px;
}

.binding-warning {
  margin: 10px 0 0;
  color: #b1452f;
}

.empty {
  border: 1px dashed var(--line-soft);
  border-radius: 14px;
  padding: 20px;
  color: var(--text-sub);
  background: rgba(255, 251, 241, 0.78);
}

@media (max-width: 900px) {
  .binding-grid {
    grid-template-columns: 1fr;
  }
}
</style>
