<template>
  <article class="workbench-card panel">
    <header class="panel-header">
      <div>
        <p class="panel-kicker mono">WORLDLINE WORKFLOW</p>
        <h2 class="card-title">世界线控制台</h2>
      </div>
      <span class="status-tag" :class="sessionStatus.tone">{{ sessionStatus.label }}</span>
    </header>
    <p class="description">从全局主档案库选取角色与组织，按步骤创建并推进平行世界会话。</p>

    <section class="panel-section source-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">01 / 源档案</p>
          <h3 class="section-title">选择进入世界线的角色与组织</h3>
        </div>
        <p class="section-copy">先确定参与推演的对象，再进入初始变量配置。</p>
      </div>
      <ArchiveLibraryPicker
        :model-value="selectedArchives"
        :project-filter="archiveProjectFilter"
        title="世界线源档案"
        description="支持跨项目混选；单项目会话会沿用该项目上下文，混合档案会进入全局会话空间。"
        @update:model-value="emit('update:selectedArchives', $event)"
        @update:project-filter="emit('update:archiveProjectFilter', $event)"
      />
    </section>

    <section class="panel-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">02 / 创建会话</p>
          <h3 class="section-title">确认初始变量并启动世界线</h3>
        </div>
        <p class="section-copy">每行输入一条变量，作为本次推演的初始扰动。</p>
      </div>

      <div class="session-summary">
        <div v-for="item in sessionSummary" :key="item.label" class="summary-card">
          <span class="summary-label">{{ item.label }}</span>
          <strong class="summary-value">{{ item.value }}</strong>
        </div>
        <div class="summary-card session-code">
          <span class="summary-label">会话编号</span>
          <strong class="summary-value mono">{{ sessionId || "未创建会话" }}</strong>
        </div>
      </div>

      <div class="setup-grid">
        <div class="field">
          <label>初始变量（每行一个）</label>
          <textarea
            :value="variablesText"
            rows="4"
            @input="emitUpdate('variablesText', $event.target.value)"
          ></textarea>
          <p class="field-hint">例如让主要势力提前结盟、某位关键角色提前失踪、或情报被错误释放。</p>
        </div>

        <div class="action-box">
          <p class="action-box-title">准备完成后启动世界线</p>
          <p class="section-copy">创建后，右侧分支总览与时空轨迹会自动刷新到当前会话。</p>
          <p class="section-copy">{{ sessionScopeHint }}</p>
          <button class="btn primary create-btn" :disabled="busy || !selectedArchives.length" @click="createSession">
            创建世界线会话
          </button>
        </div>
      </div>
    </section>

    <section class="panel-section runtime-section" :class="{ inactive: !sessionId }">
      <div class="section-head">
        <div>
          <p class="section-index mono">03 / 会话控制</p>
          <h3 class="section-title">在当前世界线中推进与注入</h3>
        </div>
        <p class="section-copy">{{ runtimeHint }}</p>
      </div>

      <div class="runtime-grid">
        <div class="action-box runtime-box">
          <p class="action-box-title">推进剧情</p>
          <p class="section-copy">基于当前分支状态向前演化一步，观察关系与事件如何变化。</p>
          <button class="btn" :disabled="!sessionId || busy" @click="stepForward">推进一步</button>
        </div>

        <div class="action-box runtime-box">
          <div class="field">
            <label>临时注入变量</label>
            <div class="inject-row">
              <input
                :value="singleVariable"
                placeholder="例如：二号角色获得预知能力"
                @input="emitUpdate('singleVariable', $event.target.value)"
              />
              <button class="btn" :disabled="!sessionId || busy" @click="injectVariable">注入变量</button>
            </div>
            <p class="field-hint">适合在会话中途添加新的扰动条件，测试剧情分叉。</p>
          </div>
        </div>
      </div>

      <div class="feedback-panel" :class="{ error: !!error }">
        <span class="feedback-label mono">STATUS</span>
        <p class="feedback">{{ error || feedback }}</p>
      </div>
    </section>
  </article>
</template>

<script setup>
import { computed } from "vue";

import ArchiveLibraryPicker from "../../components/ArchiveLibraryPicker.vue";
import { formatSessionScope } from "../../utils/chineseDisplay.js";
import {
  buildWorldlineSessionSummary,
  resolveWorldlineSessionStatus,
} from "./worldlineControlPanelViewModel.js";

const props = defineProps({
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

const sessionStatus = computed(() => resolveWorldlineSessionStatus({
  sessionId: props.sessionId,
  error: props.error,
}));

const sessionSummary = computed(() => buildWorldlineSessionSummary({
  selectedArchives: props.selectedArchives,
  variablesText: props.variablesText,
  sessionId: props.sessionId,
  sessionScope: props.sessionScope,
}));

const sessionScopeHint = computed(() => (
  props.sessionId ? `当前会话范围：${formatSessionScope(props.sessionScope)}` : "创建后会在这里显示会话范围。"
));

const runtimeHint = computed(() => (
  props.sessionId ? `当前作用域：${formatSessionScope(props.sessionScope)}` : "创建会话后即可推进剧情或注入新的变量。"
));

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

<style scoped src="./WorldlineControlPanel.css"></style>
