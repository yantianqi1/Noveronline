<template>
  <n-card title="模块绑定" class="bindings-panel">
    <p class="panel-desc">为每个业务模块指定"渠道 + 模型"组合。</p>

    <div v-for="group in groupedModules" :key="group.label" class="binding-group">
      <h3 class="group-label">{{ group.label }}</h3>
      <div class="binding-rows">
        <div
          v-for="module in group.modules"
          :key="module.module_key"
          class="binding-row"
          :class="{ bound: !!module.binding, warn: bindingWarning(module) }"
        >
          <div class="row-label">
            <strong>{{ module.label }}</strong>
            <span class="status-dot" :class="bindingStatusClass(module)"></span>
          </div>

          <n-select
            size="small"
            :value="drafts[module.module_key]?.channelKey || null"
            :options="channelOptions"
            placeholder="渠道"
            @update:value="(val) => handleChannelChange(module.module_key, val || '')"
          />

          <n-select
            size="small"
            :value="drafts[module.module_key]?.modelId || null"
            :options="modelOptions(drafts[module.module_key]?.channelKey)"
            placeholder="模型"
            @update:value="(val) => handleModelChange(module.module_key, val || '')"
          />

          <div class="row-actions">
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-button
                  size="tiny"
                  type="primary"
                  :disabled="saveDisabled(module.module_key) || savingKey === module.module_key"
                  :loading="savingKey === module.module_key"
                  @click="saveBinding(module.module_key)"
                >保存</n-button>
              </template>
              保存当前绑定
            </n-tooltip>
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-button
                  size="tiny"
                  :disabled="!module.binding || removingKey === module.module_key"
                  :loading="removingKey === module.module_key"
                  @click="removeBinding(module.module_key)"
                >解绑</n-button>
              </template>
              解除模块绑定
            </n-tooltip>
          </div>
        </div>
      </div>
    </div>

    <n-empty v-if="!modules.length" description="模块注册表为空。" />
  </n-card>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { NButton, NCard, NEmpty, NSelect, NTooltip } from "naive-ui";

import {
  syncBindingDrafts,
  updateBindingDraft,
} from "./llmModuleBindingDrafts.js";

const MODULE_GROUPS = [
  { label: "种子分析", prefixes: ["story_ontology", "local_block_facts", "contextual_block_analysis", "anchor_point_summary", "entity_resolution", "sequential_reading", "character_agent_profile"] },
  { label: "档案与图谱", prefixes: ["narrative_archives", "novel_chapter_summarizer"] },
  { label: "世界线推演", prefixes: ["worldline_", "parallel_world_config"] },
  { label: "写作", prefixes: ["writer_"] },
];

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

const channelOptions = computed(() =>
  props.channels.map((ch) => ({
    label: ch.name,
    value: ch.channel_key,
    disabled: !ch.is_enabled,
  })),
);

function modelOptions(channelKey) {
  const models = availableModels(channelKey);
  return models.map((m) => ({
    label: m.model_id,
    value: m.model_id,
  }));
}

const groupedModules = computed(() => {
  const assigned = new Set();
  const groups = [];
  for (const groupDef of MODULE_GROUPS) {
    const matched = props.modules.filter((m) => {
      if (assigned.has(m.module_key)) return false;
      return groupDef.prefixes.some((p) => m.module_key.startsWith(p) || m.module_key === p);
    });
    if (matched.length) {
      matched.forEach((m) => assigned.add(m.module_key));
      groups.push({ label: groupDef.label, modules: matched });
    }
  }
  const remaining = props.modules.filter((m) => !assigned.has(m.module_key));
  if (remaining.length) {
    groups.push({ label: "其他", modules: remaining });
  }
  return groups;
});

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

function bindingStatusClass(module) {
  if (!module.binding) return "unbound";
  return bindingWarning(module) ? "warn" : "ok";
}

function bindingWarning(module) {
  if (!module.binding) return "";
  const channel = channelByKey(module.binding.channel_key);
  if (!channel) return "渠道已删除";
  if (!channel.is_enabled) return "渠道已停用";
  return "";
}

function saveDisabled(moduleKey) {
  const draft = drafts.value[moduleKey];
  if (!draft?.channelKey || !draft?.modelId) return true;
  const channel = channelByKey(draft.channelKey);
  return !channel || !channel.is_enabled;
}

function saveBinding(moduleKey) {
  if (saveDisabled(moduleKey)) return;
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
.panel-desc {
  margin: 0 0 12px;
  color: var(--text-sub);
  font-size: 13px;
}

/* -- Groups -- */

.binding-group {
  margin-top: 14px;
}

.group-label {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-dim);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(176, 125, 75, 0.12);
}

/* -- Compact rows -- */

.binding-rows {
  display: grid;
  gap: 0;
}

.binding-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(200, 190, 175, 0.12);
  transition: background 0.15s ease;
}

.binding-row:hover {
  background: rgba(255, 250, 241, 0.6);
}

.binding-row:last-child {
  border-bottom: none;
}

.row-label {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.row-label strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* -- Status dot -- */

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.ok {
  background: #5a9a6a;
}

.status-dot.warn {
  background: #c97a3a;
}

.status-dot.unbound {
  background: rgba(160, 150, 140, 0.35);
}

/* -- Action buttons -- */

.row-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

/* -- Responsive -- */

@media (max-width: 900px) {
  .binding-row {
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .row-label {
    grid-column: 1 / -1;
  }

  .row-actions {
    grid-column: 1 / -1;
    justify-content: flex-end;
  }
}
</style>
