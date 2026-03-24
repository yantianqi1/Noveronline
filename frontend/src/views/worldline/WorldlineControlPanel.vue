<template>
  <article class="workbench-card panel" :class="sessionId ? 'panel-active' : 'panel-ready'">
    <header class="panel-header">
      <div>
        <p class="panel-kicker mono">WORLDLINE WORKFLOW</p>
        <h2 class="card-title">世界线控制台</h2>
      </div>
      <span class="status-tag" :class="sessionStatus.tone">{{ sessionStatus.label }}</span>
    </header>
    <p class="description">从全局主档案库选取角色与组织，按步骤创建并推进当前世界线。</p>

    <section class="panel-section source-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">01 / 源档案</p>
          <h3 class="section-title">选择进入世界线的角色与组织</h3>
        </div>
        <p class="section-copy">左侧聚焦筛选与挑选，右侧即时核对完整档案内容。</p>
      </div>
      <ArchiveLibraryPicker
        :model-value="selectedArchives"
        layout-variant="worldline"
        :project-filter="archiveProjectFilter"
        @update:model-value="emit('update:selected-archives', $event)"
        @update:project-filter="emit('update:archive-project-filter', $event)"
      />
    </section>

    <section class="panel-section launchpad-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">02 / 创建会话</p>
          <h3 class="section-title">确认初始变量并启动世界线</h3>
        </div>
        <p class="section-copy">启动栏固定保留在底部，便于一边筛档一边发起当前世界线。</p>
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
        <div class="launchpad-main">
          <div class="field">
            <label>初始变量（每行一个）</label>
            <textarea
              :value="variablesText"
              rows="4"
              @input="emitUpdate('variablesText', $event.target.value)"
            ></textarea>
            <p class="field-hint">例如让主要势力提前结盟、某位关键角色提前失踪、或情报被错误释放。</p>
          </div>

          <div class="mode-grid">
            <button
              v-for="item in createModeOptions"
              :key="item.value"
              class="mode-chip"
              type="button"
              :class="{ active: createMode === item.value }"
              @click="emitUpdate('createMode', item.value)"
            >
              <strong>{{ item.label }}</strong>
              <span>{{ item.copy }}</span>
            </button>
          </div>

          <div v-if="showContinuousSettings" class="auto-config-grid">
            <div class="field compact">
              <label>最大自动步数</label>
              <input
                :value="maxSteps"
                min="1"
                type="number"
                @input="emitUpdate('maxSteps', Number($event.target.value))"
              />
            </div>
            <div class="field compact">
              <label>最终条件</label>
              <input
                :value="goalText"
                placeholder="例如：主角公开宗门证据"
                @input="emitUpdate('goalText', $event.target.value)"
              />
            </div>
          </div>
          <p v-else-if="createMode === 'first_round'" class="field-hint mode-note">
            首轮自动固定执行 1 步，步数输入只在“持续自动”模式下生效。
          </p>
          <p v-if="showContinuousSettings" class="field-hint mode-note">
            持续自动会按你填写的步数上限推进；如果提前达成目标或剧情自然收束，会提前停止。
          </p>
        </div>

        <div class="action-box launchpad-action">
          <p class="action-box-title">准备完成后启动世界线</p>
          <p class="section-copy">创建后，右侧当前世界摘要与时空轨迹会自动刷新到当前会话。</p>
          <p class="section-copy">{{ sessionScopeHint }}</p>
          <button class="btn primary create-btn" :disabled="busy || !selectedArchives.length" @click="createSession">
            {{ createActionLabel }}
          </button>
        </div>
      </div>
    </section>

    <WorldlineAutoTaskPanel v-if="task" :task="task" />

    <section v-if="sessionId" class="panel-section runtime-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">{{ runtimeSectionIndex }}</p>
          <h3 class="section-title">在当前世界线中推进与注入</h3>
        </div>
        <p class="section-copy">{{ runtimeHint }}</p>
      </div>

      <div class="runtime-grid">
        <div class="action-box runtime-box">
          <p class="action-box-title">推进剧情</p>
          <p class="section-copy">基于当前世界状态向前演化一步，观察关系与事件如何变化。</p>
          <button class="btn" :disabled="!sessionId || busy" @click="stepForward">推进一步</button>
          <button
            v-if="createMode !== 'manual'"
            class="btn"
            :disabled="!sessionId || busy"
            @click="$emit('start-auto-evolve')"
          >
            按当前模式自动推进
          </button>
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
            <p class="field-hint">适合在会话中途添加新的扰动条件，测试它如何继续改写当前世界。</p>
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
import WorldlineAutoTaskPanel from "./WorldlineAutoTaskPanel.vue";
import {
  buildWorldlineSessionSummary,
  resolveWorldlineSessionStatus,
} from "./worldlineControlPanelViewModel.js";

const createModeOptions = Object.freeze([
  { value: "manual", label: "手动", copy: "创建后由你推进与注入。" },
  { value: "first_round", label: "首轮自动", copy: "创建后固定先跑 1 步，适合先看第一轮反应。" },
  { value: "continuous", label: "持续自动", copy: "按你填写的步数上限持续推进。" },
]);

const props = defineProps({
  selectedArchives: { type: Array, default: () => [] },
  archiveProjectFilter: { type: String, default: "" },
  variablesText: { type: String, default: "" },
  singleVariable: { type: String, default: "" },
  createMode: { type: String, default: "manual" },
  goalText: { type: String, default: "" },
  maxSteps: { type: Number, default: 6 },
  sessionId: { type: String, default: "" },
  sessionScope: { type: String, default: "" },
  task: { type: Object, default: null },
  feedback: { type: String, default: "" },
  error: { type: String, default: "" },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:selected-archives",
  "update:archive-project-filter",
  "update:variables-text",
  "update:single-variable",
  "update:create-mode",
  "update:goal-text",
  "update:max-steps",
  "create-session",
  "start-auto-evolve",
  "advance-step",
  "inject-variable",
]);

const UPDATE_EVENT_MAP = Object.freeze({
  variablesText: "update:variables-text",
  singleVariable: "update:single-variable",
  createMode: "update:create-mode",
  goalText: "update:goal-text",
  maxSteps: "update:max-steps",
});

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

const showContinuousSettings = computed(() => props.createMode === "continuous");
const createActionLabel = computed(() => (
  props.createMode === "manual" ? "创建世界线会话" : "创建会话并启动自动演化"
));
const runtimeSectionIndex = computed(() => (
  props.task || props.createMode !== "manual" ? "04 / 会话控制" : "03 / 会话控制"
));
const runtimeHint = computed(() => (
  props.sessionId ? `当前作用域：${formatSessionScope(props.sessionScope)}` : "创建会话后即可推进剧情或注入新的变量。"
));

function emitUpdate(field, value) {
  emit(UPDATE_EVENT_MAP[field], value);
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
