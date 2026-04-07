<template>
  <div class="outline-view">
    <div class="outline-header">
      <h3 class="outline-title title-ancient">章节大纲</h3>
      <span class="outline-count">{{ displayOutline.length }} 个场景</span>
      <div class="outline-header-actions">
        <n-input
          v-if="!previewOutline"
          v-model:value="labelInput"
          class="outline-label-input"
          placeholder="版本标注（可选）"
          size="small"
        />
        <n-button
          v-if="!previewOutline"
          size="small"
          type="primary"
          :disabled="!dirty"
          @click="handleSave"
        >保存大纲</n-button>
        <n-button
          size="small"
          :type="showHistory ? 'primary' : 'default'"
          :quaternary="!showHistory"
          @click="toggleHistory"
        >历史版本</n-button>
      </div>
    </div>

    <!-- Preview banner -->
    <div v-if="previewOutline" class="outline-preview-banner">
      <span>正在预览历史版本</span>
      <n-button size="small" @click="emit('restore')">回退到此版本</n-button>
      <n-button size="small" @click="emit('cancel-preview')">取消预览</n-button>
    </div>

    <!-- Version history panel -->
    <div v-if="showHistory" class="outline-version-list">
      <div v-if="!versions.length" class="outline-version-empty">暂无历史版本</div>
      <div
        v-for="(ver, idx) in versions"
        :key="ver.version_id"
        class="outline-version-item"
        @click="emit('load-versions', ver.version_id)"
      >
        <span class="outline-version-idx">{{ versions.length - idx }}</span>
        <span class="outline-version-label">{{ ver.label || '自动快照' }}</span>
        <span class="outline-version-time">{{ formatTime(ver.created_at) }}</span>
      </div>
    </div>

    <!-- Scene list (current or preview) -->
    <div class="outline-list">
      <div
        v-for="(scene, idx) in displayOutline"
        :key="idx"
        class="outline-item"
      >
        <div class="outline-item-header">
          <span class="outline-order">{{ scene.scene_order }}</span>
          <n-input
            v-if="!previewOutline"
            v-model:value="scene.title"
            class="outline-item-title-input"
            placeholder="场景标题"
            @input="dirty = true"
          />
          <span v-else class="outline-item-title outline-item-title--readonly">{{ scene.title }}</span>
          <div v-if="!previewOutline" class="outline-item-actions">
            <n-button size="tiny" quaternary :disabled="idx === 0" @click="moveUp(idx)" title="上移"><Icon icon="icon-park-outline:up" width="14" /></n-button>
            <n-button size="tiny" quaternary :disabled="idx === displayOutline.length - 1" @click="moveDown(idx)" title="下移"><Icon icon="icon-park-outline:down" width="14" /></n-button>
            <n-button size="tiny" quaternary @click="removeScene(idx)" title="删除"><Icon icon="icon-park-outline:close-small" width="14" /></n-button>
          </div>
        </div>

        <div class="outline-item-fields">
          <div class="outline-field">
            <label>POV</label>
            <n-input v-if="!previewOutline" v-model:value="scene.pov" placeholder="视角角色" size="small" @input="dirty = true" />
            <span v-else class="outline-field-readonly">{{ scene.pov || '—' }}</span>
          </div>
          <div class="outline-field outline-field--wide">
            <label>概述</label>
            <n-input
              v-if="!previewOutline"
              v-model:value="scene.summary"
              type="textarea"
              :rows="2"
              placeholder="场景概述..."
              size="small"
              @input="dirty = true"
            />
            <p v-else class="outline-field-readonly">{{ scene.summary || '—' }}</p>
          </div>
          <div class="outline-field outline-field--wide">
            <label>关键事件</label>
            <div class="outline-events">
              <template v-if="!previewOutline">
                <div v-for="(ev, ei) in scene.key_events" :key="ei" class="outline-event-row">
                  <n-input
                    :value="ev"
                    placeholder="事件描述"
                    size="small"
                    @update:value="val => updateEvent(idx, ei, val)"
                  />
                  <n-button size="tiny" quaternary @click="removeEvent(idx, ei)"><Icon icon="icon-park-outline:close-small" width="12" /></n-button>
                </div>
                <n-button size="tiny" dashed @click="addEvent(idx)">+ 事件</n-button>
              </template>
              <template v-else>
                <div v-for="(ev, ei) in scene.key_events" :key="ei" class="outline-event-row">
                  <span class="outline-field-readonly">{{ ev }}</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <n-button v-if="!previewOutline" class="outline-add-scene" dashed block @click="addScene">+ 添加场景</n-button>
  </div>
</template>

<script setup>
import { ref, watch, computed } from "vue";
import { NButton, NInput } from "naive-ui";
import { Icon } from "@iconify/vue";

const props = defineProps({
  outline: { type: Array, default: () => [] },
  chapterId: { type: String, default: "" },
  projectId: { type: String, default: "" },
  versions: { type: Array, default: () => [] },
  previewOutline: { type: Array, default: null },
});

const emit = defineEmits(["save", "load-versions", "restore", "cancel-preview"]);

const localOutline = ref(JSON.parse(JSON.stringify(props.outline)));
const dirty = ref(false);
const showHistory = ref(false);
const labelInput = ref("");

const previewRef = computed(() => props.previewOutline);
const displayOutline = computed(() => {
  return previewRef.value || localOutline.value;
});

watch(() => props.outline, (val) => {
  localOutline.value = JSON.parse(JSON.stringify(val));
  dirty.value = false;
}, { deep: true });

function renumber() {
  localOutline.value.forEach((s, i) => { s.scene_order = i + 1; });
}

function moveUp(idx) {
  if (idx <= 0) return;
  const arr = localOutline.value;
  [arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]];
  renumber();
  dirty.value = true;
}

function moveDown(idx) {
  const arr = localOutline.value;
  if (idx >= arr.length - 1) return;
  [arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]];
  renumber();
  dirty.value = true;
}

function removeScene(idx) {
  localOutline.value.splice(idx, 1);
  renumber();
  dirty.value = true;
}

function addScene() {
  localOutline.value.push({
    scene_order: localOutline.value.length + 1,
    title: "",
    summary: "",
    pov: "",
    key_events: [],
  });
  dirty.value = true;
}

function updateEvent(sceneIdx, eventIdx, value) {
  localOutline.value[sceneIdx].key_events[eventIdx] = value;
  dirty.value = true;
}

function removeEvent(sceneIdx, eventIdx) {
  localOutline.value[sceneIdx].key_events.splice(eventIdx, 1);
  dirty.value = true;
}

function addEvent(sceneIdx) {
  if (!localOutline.value[sceneIdx].key_events) {
    localOutline.value[sceneIdx].key_events = [];
  }
  localOutline.value[sceneIdx].key_events.push("");
  dirty.value = true;
}

function handleSave() {
  emit("save", JSON.parse(JSON.stringify(localOutline.value)), labelInput.value);
  labelInput.value = "";
}

function toggleHistory() {
  showHistory.value = !showHistory.value;
  if (showHistory.value) {
    emit("load-versions");
  }
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
</script>

<style scoped>
.outline-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 14px;
  overflow-y: auto;
}

.outline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.outline-title {
  margin: 0;
  font-size: 16px;
}

.outline-count {
  font-size: 13px;
  color: var(--text-dim, #999);
}

.outline-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.outline-label-input {
  width: 140px;
}

.outline-preview-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: rgba(176, 125, 75, 0.08);
  border: 1px solid var(--accent-copper, #c09060);
  border-radius: 8px;
  font-size: 13px;
  color: var(--accent-copper, #c09060);
}

.outline-version-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 14px;
  padding: 10px;
  background: #faf9f7;
  border: 1px solid var(--line-soft, #e0dcd4);
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.outline-version-empty {
  font-size: 13px;
  color: var(--text-dim, #999);
  text-align: center;
  padding: 8px;
}

.outline-version-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.outline-version-item:hover {
  background: rgba(176, 125, 75, 0.08);
}

.outline-version-idx {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--line-soft, #e0dcd4);
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.outline-version-label {
  flex: 1;
  color: var(--text-main, #1a1a1a);
}

.outline-version-time {
  font-size: 11px;
  color: var(--text-dim, #999);
  flex-shrink: 0;
}

.outline-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.outline-item {
  border: 1px solid var(--line-soft, #e0dcd4);
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff;
}

.outline-item-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.outline-order {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent-copper, #c09060);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.outline-item-title-input {
  flex: 1;
}

.outline-item-title--readonly {
  flex: 1;
  padding: 4px 8px;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-main, #1a1a1a);
}

.outline-item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.outline-item-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.outline-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.outline-field label {
  font-size: 11px;
  color: var(--text-dim, #999);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.outline-field--wide {
  flex: 1 1 100%;
}

.outline-field-readonly {
  font-size: 13px;
  color: var(--text-main, #1a1a1a);
  padding: 4px 0;
}

.outline-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.outline-event-row {
  display: flex;
  gap: 4px;
  align-items: center;
}

.outline-add-scene {
  margin-top: 12px;
}
</style>
