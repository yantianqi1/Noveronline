<template>
  <article class="workbench-card panel full">
    <h2 class="card-title">对象对话入口</h2>
    <p>从右侧对象名册选中一个对象后，直接向它发送一句话并查看回应。</p>

    <div class="chat-grid">
      <div class="field">
        <label>当前对话对象</label>
        <div class="chat-chip">{{ selectedAgent?.display_name || "请先从右侧点选对象" }}</div>
      </div>
      <div class="field">
        <label>生成模式</label>
        <n-select
          :value="chatMode"
          :options="chatModeOptions"
          @update:value="emitMode"
        />
      </div>
      <div class="field">
        <label>你要说的话</label>
        <n-input
          type="textarea"
          :value="chatMessage"
          placeholder="例如：你是否愿意在今晚之前公开证据？"
          @update:value="emitUpdate"
        />
      </div>
    </div>

    <div class="toolbar-row">
      <n-button type="primary" :disabled="busy || !sessionId || !selectedAgent" @click="$emit('submit')">发送对话</n-button>
    </div>

    <div v-if="chatReply" class="chat-reply">
      <div class="seed-title">对象回复</div>
      <p>{{ chatReply.reply || "暂无回复文本" }}</p>
      <div class="seed-title">生成信息</div>
      <div class="mono">{{ chatReply.generator_mode || chatMode }} · {{ chatReply.model_name || "无模型" }}</div>
      <div class="seed-title">建议动作</div>
      <div class="suggestion-item" v-for="(item, idx) in chatReply.suggested_actions || []" :key="`chat_action_${idx}`">
        {{ idx + 1 }}. {{ item }}
      </div>
    </div>
    <div class="chat-reply" v-if="dialogues.length">
      <div class="seed-title">最近对话历史</div>
      <div class="suggestion-item" v-for="item in dialogues" :key="item.dialogue_id">
        <div class="mono">{{ item.generator_mode }} · {{ formatTime(item.created_at) }}</div>
        <div>Q: {{ item.message }}</div>
        <div>A: {{ item.reply }}</div>
      </div>
    </div>
    <n-tag v-if="chatError" type="error" style="margin-top: 8px">{{ chatError }}</n-tag>
  </article>
</template>

<script setup>
import { NButton, NInput, NSelect, NTag } from "naive-ui";

const chatModeOptions = [
  { label: "template", value: "template" },
  { label: "llm", value: "llm" },
];

defineProps({
  sessionId: { type: String, default: "" },
  selectedAgent: { type: Object, default: null },
  chatMode: { type: String, default: "template" },
  chatMessage: { type: String, default: "" },
  chatReply: { type: Object, default: null },
  dialogues: { type: Array, default: () => [] },
  chatError: { type: String, default: "" },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits(["update:chatMessage", "update:chatMode", "submit"]);

function emitUpdate(value) {
  emit("update:chatMessage", value);
}

function emitMode(value) {
  emit("update:chatMode", value);
}

function formatTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
</script>

<style scoped>
.full {
  grid-column: 1 / -1;
}

.panel {
  padding: 10px;
}

.panel p {
  color: var(--text-sub);
}

.chat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.chat-reply,
.chat-chip {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #fffaf1;
}

.chat-reply {
  margin-top: 8px;
  padding: 10px;
}

.chat-chip {
  padding: 10px 12px;
}

.seed-title {
  font-weight: 700;
  margin: 8px 0 5px;
}

.seed-title:first-child {
  margin-top: 0;
}

.suggestion-item {
  border-top: 1px dashed var(--line-soft);
  padding: 7px 0;
}

.suggestion-item:first-of-type {
  border-top: none;
}

@media (max-width: 1200px) {
  .chat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
