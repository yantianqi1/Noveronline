<template>
  <article class="workbench-card panel" :class="sessionId ? 'panel-active' : 'panel-ready'">
    <header class="panel-header">
      <p class="panel-kicker mono">WORLDLINE</p>
      <span class="status-tag" :class="sessionStatus.tone">{{ sessionStatus.label }}</span>
    </header>

    <!-- Source section: only rendered in two-col / stacked fallback -->
    <section v-if="showArchivePicker" class="panel-section source-section">
      <div class="section-head section-head--compact">
        <p class="section-index mono">01 / 源档案</p>
        <h3 class="section-title">选择角色与组织</h3>
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
      <p class="section-index mono">{{ launchpadSectionIndex }}</p>

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
            <label>会话名称 <span class="label-hint">（方便后续识别）</span></label>
            <input
              :value="sessionLabel"
              type="text"
              placeholder="例如：主线剧情推演、第三章分支"
              @input="emitUpdate('sessionLabel', $event.target.value)"
            />
          </div>
          <div class="field">
            <label>初始变量</label>
            <textarea
              :value="variablesText"
              rows="3"
              placeholder="每行一个，如：主要势力提前结盟"
              @input="emitUpdate('variablesText', $event.target.value)"
            ></textarea>
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
            首轮固定 1 步，达成目标或收束时自动停止。
          </p>
        </div>

        <div class="action-box launchpad-action">
          <button class="btn primary create-btn" :disabled="busy || !selectedArchives.length" @click="createSession">
            {{ createActionLabel }}
          </button>
          <p v-if="sessionId" class="scope-hint mono">{{ sessionScopeHint }}</p>
        </div>
      </div>
    </section>

    <WorldlineAutoTaskPanel v-if="task" :task="task" />

    <section v-if="sessionId" class="panel-section runtime-section">
      <p class="section-index mono">{{ runtimeSectionIndex }}</p>

      <div class="runtime-grid">
        <div class="action-box runtime-box">
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
            <p class="field-hint">中途注入新扰动条件</p>
          </div>
        </div>
      </div>

      <WorldlineVariableLockPanel
        v-if="worldVariables.length"
        :section-index="lockSectionIndex"
        :world-variables="worldVariables"
        :locked-variable-ids="lockedVariableIds"
        @toggle-lock="emit('toggle-lock', $event)"
        @lock-all="emit('lock-all')"
        @unlock-all="emit('unlock-all')"
      />

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
import WorldlineVariableLockPanel from "./WorldlineVariableLockPanel.vue";
import {
  buildWorldlineSessionSummary,
  resolveWorldlineSessionStatus,
} from "./worldlineControlPanelViewModel.js";

const createModeOptions = Object.freeze([
  { value: "manual", label: "手动", copy: "逐步推进" },
  { value: "first_round", label: "首轮自动", copy: "先跑 1 步" },
  { value: "continuous", label: "持续自动", copy: "按步数上限推进" },
]);

const props = defineProps({
  selectedArchives: { type: Array, default: () => [] },
  archiveProjectFilter: { type: String, default: "" },
  showArchivePicker: { type: Boolean, default: false },
  sessionLabel: { type: String, default: "" },
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
  worldVariables: { type: Array, default: () => [] },
  lockedVariableIds: { type: Set, default: () => new Set() },
});

const emit = defineEmits([
  "update:selected-archives",
  "update:archive-project-filter",
  "update:session-label",
  "update:variables-text",
  "update:single-variable",
  "update:create-mode",
  "update:goal-text",
  "update:max-steps",
  "create-session",
  "start-auto-evolve",
  "advance-step",
  "inject-variable",
  "toggle-lock",
  "lock-all",
  "unlock-all",
]);

const UPDATE_EVENT_MAP = Object.freeze({
  sessionLabel: "update:session-label",
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
  props.createMode === "manual" ? "启动世界线整备" : "整备完成后进入自动推演"
));

const launchpadSectionIndex = computed(() => (
  props.showArchivePicker ? "02 / 启动整备" : "01 / 启动整备"
));

const runtimeSectionIndex = computed(() => {
  let base = props.showArchivePicker ? 2 : 1;
  if (props.task || props.createMode !== "manual") {
    base += 1;
  }
  const label = String(base + 1).padStart(2, "0");
  return `${label} / 会话控制`;
});

const lockSectionIndex = computed(() => {
  let base = props.showArchivePicker ? 2 : 1;
  if (props.task || props.createMode !== "manual") {
    base += 1;
  }
  base += 1; // after runtime section
  const label = String(base + 1).padStart(2, "0");
  return `${label} / 变量锁定`;
});

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
