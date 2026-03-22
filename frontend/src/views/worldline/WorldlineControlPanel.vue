<template>
  <article class="workbench-card panel">
    <h2 class="card-title">世界线控制台</h2>
    <p class="description">从全局主档案库选取角色与组织，直接创建并推进平行世界会话。</p>

    <ArchiveLibraryPicker
      :model-value="selectedArchives"
      :project-filter="archiveProjectFilter"
      title="世界线源档案"
      description="支持跨项目混选；单项目会话会沿用该项目上下文，混合档案会进入全局会话空间。"
      @update:model-value="emit('update:selectedArchives', $event)"
      @update:project-filter="emit('update:archiveProjectFilter', $event)"
    />

    <div class="field">
      <label>初始变量 (每行一个)</label>
      <textarea :value="variablesText" @input="emitUpdate('variablesText', $event.target.value)"></textarea>
    </div>
    <div class="toolbar-row">
      <button class="btn primary" :disabled="busy || !selectedArchives.length" @click="createSession">创建世界线会话</button>
      <span class="chip mono">{{ sessionId || "未创建会话" }}</span>
      <span class="chip" v-if="sessionScope">{{ formatSessionScope(sessionScope) }}</span>
    </div>
    <div class="toolbar-row">
      <button class="btn" :disabled="!sessionId || busy" @click="stepForward">推进一步</button>
      <button class="btn" :disabled="!sessionId || busy" @click="injectVariable">注入变量</button>
    </div>

    <div class="field">
      <label>临时注入变量</label>
      <input :value="singleVariable" placeholder="例如：二号角色获得预知能力" @input="emitUpdate('singleVariable', $event.target.value)" />
    </div>

    <p class="feedback" :class="{ error: !!error }">{{ error || feedback }}</p>
  </article>
</template>

<script setup>
import ArchiveLibraryPicker from "../../components/ArchiveLibraryPicker.vue";
import { formatSessionScope } from "../../utils/chineseDisplay.js";

defineProps({
  selectedArchives: { type: Array, default: () => [] },
  archiveProjectFilter: { type: String, default: "" },
  variablesText: String,
  singleVariable: String,
  sessionId: String,
  sessionScope: String,
  feedback: String,
  error: String,
  busy: Boolean,
});

const emit = defineEmits([
  "update:selectedArchives",
  "update:archiveProjectFilter",
  "update:variablesText",
  "update:singleVariable",
  "create-session",
  "advance-step",
  "inject-variable",
]);

function emitUpdate(field, value) {
  emit(`update:${field}`, value);
}

function createSession() {
  emit("create-session");
}

function stepForward() {
  emit("advance-step");
}

function injectVariable() {
  emit("inject-variable");
}
</script>

<style scoped>
.workbench-card {
  padding: 16px;
}

.description,
.feedback {
  color: var(--text-sub);
}

.field {
  margin-top: 14px;
}

.feedback.error {
  color: #9b4326;
}
</style>
