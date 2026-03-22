<template>
  <article class="workbench-card panel">
    <div class="panel-head">
      <div>
        <h2 class="card-title">模块绑定</h2>
        <p>为每个业务模块指定唯一的“渠道 + 模型”组合，保存后对后续调用立即生效。</p>
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
            <select v-model="drafts[module.module_key].channelKey" @change="handleChannelChange(module.module_key)">
              <option value="">请选择渠道</option>
              <option v-for="channel in channels" :key="channel.channel_key" :value="channel.channel_key">
                {{ channel.name }}{{ channel.is_enabled ? "" : "（停用）" }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>模型</label>
            <select v-model="drafts[module.module_key].modelId">
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
          <span class="status" :class="module.binding ? 'ok' : 'warn'">
            {{ module.binding ? "已绑定" : "未绑定" }}
          </span>
          <span class="mono binding-current">
            {{ currentBindingText(module) }}
          </span>
        </div>

        <div class="toolbar-row">
          <button
            class="btn primary"
            :disabled="saveDisabled(module.module_key) || savingKey === module.module_key"
            @click="saveBinding(module.module_key)"
          >
            {{ savingKey === module.module_key ? "保存中..." : "保存绑定" }}
          </button>
        </div>
      </section>
      <div v-if="!modules.length" class="empty">模块注册表为空，暂时没有可绑定的大模型模块。</div>
    </div>
  </article>
</template>

<script setup>
import { reactive, watch } from "vue";

const props = defineProps({
  modules: { type: Array, required: true },
  channels: { type: Array, required: true },
  savingKey: { type: String, default: "" },
});

const emit = defineEmits(["save-binding"]);

const drafts = reactive({});

watch(
  () => props.modules,
  (modules) => {
    for (const module of modules) {
      drafts[module.module_key] = {
        channelKey: module.binding?.channel_key || "",
        modelId: module.binding?.model_id || "",
      };
    }
  },
  { immediate: true, deep: true },
);

function availableModels(channelKey) {
  return props.channels.find((item) => item.channel_key === channelKey)?.models || [];
}

function handleChannelChange(moduleKey) {
  const models = availableModels(drafts[moduleKey].channelKey);
  const hasCurrentModel = models.some((item) => item.model_id === drafts[moduleKey].modelId);
  drafts[moduleKey].modelId = hasCurrentModel ? drafts[moduleKey].modelId : (models[0]?.model_id || "");
}

function currentBindingText(module) {
  if (!module.binding) {
    return "尚未配置";
  }
  const channelName = props.channels.find((item) => item.channel_key === module.binding.channel_key)?.name || module.binding.channel_key;
  return `${channelName} / ${module.binding.model_id}`;
}

function saveDisabled(moduleKey) {
  return !drafts[moduleKey]?.channelKey || !drafts[moduleKey]?.modelId;
}

function saveBinding(moduleKey) {
  emit("save-binding", moduleKey, {
    channel_key: drafts[moduleKey].channelKey,
    model_id: drafts[moduleKey].modelId,
  });
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
