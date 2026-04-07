<template>
  <n-card title="渠道管理" class="panel">
    <template #header-extra>
      <n-button :disabled="submitting" @click="resetForm">新建渠道</n-button>
    </template>

    <p class="panel-desc">维护 OpenAI 兼容渠道，保存 `base_url`、密钥与同步状态。</p>

    <n-form class="editor" @submit.prevent="submitForm">
      <div class="editor-grid">
        <n-form-item label="渠道名称">
          <n-input v-model:value="form.name" placeholder="例如：OpenAI Main" />
        </n-form-item>
        <n-form-item label="Base URL">
          <n-input v-model:value="form.baseUrl" placeholder="https://api.openai.com/v1" />
        </n-form-item>
        <n-form-item label="并发上限">
          <n-input v-model:value="form.maxConcurrency" placeholder="4" />
        </n-form-item>
        <n-form-item label="API Key" class="field-wide">
          <n-input
            v-model:value="form.apiKey"
            :placeholder="editingChannelKey ? '留空表示保留现有密钥' : '请输入渠道密钥'"
            type="password"
            show-password-on="click"
          />
        </n-form-item>
      </div>
      <div class="form-footer">
        <n-checkbox v-model:checked="form.isEnabled">启用该渠道</n-checkbox>
        <div class="toolbar-row">
          <n-button type="primary" attr-type="submit" :disabled="submitting" :loading="submitting">{{ submitLabel }}</n-button>
          <n-button v-if="editingChannelKey" :disabled="submitting" @click="resetForm">取消编辑</n-button>
        </div>
      </div>
    </n-form>

    <div class="channel-list">
      <section v-for="channel in channels" :key="channel.channel_key" class="channel-card">
        <div class="channel-top">
          <div>
            <strong>{{ channel.name }}</strong>
            <div class="meta mono">{{ channel.base_url }}</div>
          </div>
          <div class="channel-actions">
            <n-tag :type="channel.is_enabled ? 'success' : 'warning'" size="small">
              {{ channel.is_enabled ? "启用中" : "已停用" }}
            </n-tag>
            <n-button size="small" :disabled="submitting" @click="startEdit(channel)">编辑</n-button>
            <n-button
              size="small"
              :disabled="syncingKey === channel.channel_key || submitting"
              :loading="syncingKey === channel.channel_key"
              @click="$emit('sync-channel', channel.channel_key)"
            >
              {{ syncingKey === channel.channel_key ? "同步中..." : "同步模型" }}
            </n-button>
            <n-button
              size="small"
              type="error"
              :disabled="deletingKey === channel.channel_key || submitting"
              :loading="deletingKey === channel.channel_key"
              @click="$emit('delete-channel', channel.channel_key)"
            >
              {{ deletingKey === channel.channel_key ? "删除中..." : "删除" }}
            </n-button>
          </div>
        </div>
        <div class="channel-meta">
          <n-tag size="small" :bordered="false">{{ channel.api_key_masked }}</n-tag>
          <n-tag size="small" :bordered="false">状态：{{ channel.last_sync_status || "idle" }}</n-tag>
          <n-tag size="small" :bordered="false">上次同步：{{ channel.last_sync_at || "未同步" }}</n-tag>
          <n-tag size="small" :bordered="false">模型：{{ channel.models?.length || 0 }}</n-tag>
          <n-tag size="small" :bordered="false">并发上限：{{ channel.max_concurrency || 4 }}</n-tag>
          <n-tag size="small" :bordered="false">当前占用：{{ channel.runtime?.inflight || 0 }}</n-tag>
          <n-tag size="small" :bordered="false">排队数：{{ channel.runtime?.waiting || 0 }}</n-tag>
        </div>
        <p v-if="channel.last_sync_error" class="channel-error">{{ channel.last_sync_error }}</p>
        <div class="model-cloud">
          <n-tag v-for="model in previewModels(channel.models)" :key="model.model_id" size="small" round :bordered="false" type="info">
            {{ model.model_id }}
          </n-tag>
          <n-tag v-if="(channel.models?.length || 0) > MAX_PREVIEW_MODELS" size="small" :bordered="false">
            +{{ channel.models.length - MAX_PREVIEW_MODELS }}
          </n-tag>
        </div>
      </section>
      <n-empty v-if="!channels.length" description="还没有配置任何渠道，可先新增一条 OpenAI 兼容渠道。" />
    </div>
  </n-card>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { NButton, NCard, NCheckbox, NEmpty, NForm, NFormItem, NInput, NTag } from "naive-ui";

const MAX_PREVIEW_MODELS = 8;

const props = defineProps({
  channels: { type: Array, required: true },
  submitting: { type: Boolean, default: false },
  syncingKey: { type: String, default: "" },
  deletingKey: { type: String, default: "" },
});

const emit = defineEmits(["create-channel", "update-channel", "sync-channel", "delete-channel"]);

const editingChannelKey = ref("");
const form = reactive({
  name: "",
  baseUrl: "",
  apiKey: "",
  maxConcurrency: "4",
  isEnabled: true,
});

const submitLabel = computed(() => {
  if (props.submitting) {
    return editingChannelKey.value ? "保存中..." : "创建中...";
  }
  return editingChannelKey.value ? "保存渠道" : "创建渠道";
});

function resetForm() {
  editingChannelKey.value = "";
  form.name = "";
  form.baseUrl = "";
  form.apiKey = "";
  form.maxConcurrency = "4";
  form.isEnabled = true;
}

function startEdit(channel) {
  editingChannelKey.value = channel.channel_key;
  form.name = channel.name;
  form.baseUrl = channel.base_url;
  form.apiKey = "";
  form.maxConcurrency = String(channel.max_concurrency || 4);
  form.isEnabled = !!channel.is_enabled;
}

function submitForm() {
  const payload = {
    name: form.name.trim(),
    base_url: form.baseUrl.trim(),
    api_key: form.apiKey.trim(),
    max_concurrency: Math.max(1, Number(form.maxConcurrency || 4)),
    is_enabled: form.isEnabled,
  };
  if (editingChannelKey.value) {
    emit("update-channel", editingChannelKey.value, payload, resetForm);
    return;
  }
  emit("create-channel", payload, resetForm);
}

function previewModels(models = []) {
  return models.slice(0, MAX_PREVIEW_MODELS);
}
</script>

<style scoped>
.panel-desc {
  margin: 0 0 8px;
  color: var(--text-sub);
  font-size: 13px;
}

.editor {
  padding: 10px;
  border-radius: 10px;
  border: 1px solid var(--line-soft);
  background: #fffaf1;
}

.editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.field-wide {
  grid-column: 1 / -1;
}

.form-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
}

.toolbar-row {
  display: flex;
  gap: 8px;
}

.channel-list {
  margin-top: 10px;
  display: grid;
  gap: 8px;
}

.channel-card {
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  padding: 10px;
  background: #fffdf7;
}

.channel-top,
.channel-actions,
.channel-meta,
.model-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.channel-top {
  justify-content: space-between;
  align-items: start;
}

.channel-actions {
  align-items: center;
}

.meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-sub);
}

.channel-meta,
.model-cloud {
  margin-top: 6px;
}

.channel-error {
  margin: 10px 0 0;
  color: #b1452f;
}

@media (max-width: 900px) {
  .editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
