<template>
  <article class="workbench-card panel">
    <div class="panel-head">
      <div>
        <h2 class="card-title">渠道管理</h2>
        <p>维护 OpenAI 兼容渠道，保存 `base_url`、密钥与同步状态。</p>
      </div>
      <button class="btn" :disabled="submitting" @click="resetForm">新建渠道</button>
    </div>

    <form class="editor" @submit.prevent="submitForm">
      <div class="field">
        <label>渠道名称</label>
        <input v-model="form.name" placeholder="例如：OpenAI Main" />
      </div>
      <div class="field">
        <label>Base URL</label>
        <input v-model="form.baseUrl" placeholder="https://api.openai.com/v1" />
      </div>
      <div class="field field-wide">
        <label>API Key</label>
        <input
          v-model="form.apiKey"
          :placeholder="editingChannelKey ? '留空表示保留现有密钥' : '请输入渠道密钥'"
          type="password"
        />
      </div>
      <label class="checkbox-row">
        <input v-model="form.isEnabled" type="checkbox" />
        <span>启用该渠道</span>
      </label>
      <div class="toolbar-row">
        <button class="btn primary" :disabled="submitting">{{ submitLabel }}</button>
        <button v-if="editingChannelKey" class="btn" type="button" :disabled="submitting" @click="resetForm">取消编辑</button>
      </div>
    </form>

    <div class="channel-list">
      <section v-for="channel in channels" :key="channel.channel_key" class="channel-card">
        <div class="channel-top">
          <div>
            <strong>{{ channel.name }}</strong>
            <div class="meta mono">{{ channel.base_url }}</div>
          </div>
          <div class="channel-actions">
            <span class="status" :class="channel.is_enabled ? 'ok' : 'warn'">
              {{ channel.is_enabled ? "启用中" : "已停用" }}
            </span>
            <button class="btn" :disabled="submitting" @click="startEdit(channel)">编辑</button>
            <button
              class="btn"
              :disabled="syncingKey === channel.channel_key || submitting"
              @click="$emit('sync-channel', channel.channel_key)"
            >
              {{ syncingKey === channel.channel_key ? "同步中..." : "同步模型" }}
            </button>
            <button
              class="btn danger"
              :disabled="deletingKey === channel.channel_key || submitting"
              @click="$emit('delete-channel', channel.channel_key)"
            >
              {{ deletingKey === channel.channel_key ? "删除中..." : "删除" }}
            </button>
          </div>
        </div>
        <div class="channel-meta">
          <span class="chip mono">{{ channel.api_key_masked }}</span>
          <span class="chip mono">状态：{{ channel.last_sync_status || "idle" }}</span>
          <span class="chip mono">上次同步：{{ channel.last_sync_at || "未同步" }}</span>
          <span class="chip mono">模型：{{ channel.models?.length || 0 }}</span>
        </div>
        <p v-if="channel.last_sync_error" class="channel-error">{{ channel.last_sync_error }}</p>
        <div class="model-cloud">
          <span v-for="model in previewModels(channel.models)" :key="model.model_id" class="model-pill mono">
            {{ model.model_id }}
          </span>
          <span v-if="(channel.models?.length || 0) > MAX_PREVIEW_MODELS" class="chip mono">
            +{{ channel.models.length - MAX_PREVIEW_MODELS }}
          </span>
        </div>
      </section>
      <div v-if="!channels.length" class="empty">还没有配置任何渠道，可先新增一条 OpenAI 兼容渠道。</div>
    </div>
  </article>
</template>

<script setup>
import { computed, reactive, ref } from "vue";

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
  form.isEnabled = true;
}

function startEdit(channel) {
  editingChannelKey.value = channel.channel_key;
  form.name = channel.name;
  form.baseUrl = channel.base_url;
  form.apiKey = "";
  form.isEnabled = !!channel.is_enabled;
}

function submitForm() {
  const payload = {
    name: form.name.trim(),
    base_url: form.baseUrl.trim(),
    api_key: form.apiKey.trim(),
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
.panel {
  padding: 18px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}

.panel-head p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.editor {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--line-soft);
  background: #fffaf1;
}

.field-wide {
  grid-column: 1 / -1;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-sub);
}

.channel-list {
  margin-top: 16px;
  display: grid;
  gap: 12px;
}

.channel-card {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  padding: 14px;
  background: #fffdf7;
}

.channel-top,
.channel-actions,
.channel-meta,
.model-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.channel-top {
  justify-content: space-between;
  align-items: start;
}

.meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-sub);
}

.channel-meta,
.model-cloud {
  margin-top: 10px;
}

.model-pill {
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(39, 90, 120, 0.08);
  color: var(--accent-blue);
  font-size: 12px;
}

.channel-error {
  margin: 10px 0 0;
  color: #b1452f;
}

.btn.danger {
  border-color: #b1452f;
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
  .editor {
    grid-template-columns: 1fr;
  }
}
</style>
