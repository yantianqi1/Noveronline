<template>
  <section class="candidate-zone">
    <div class="candidate-bar">
      <div class="candidate-bar-left">
        <span class="candidate-indicator"></span>
        <span class="candidate-count mono">{{ candidateEvents.length }} 个候选事件等待审核</span>
      </div>
      <div v-if="candidateEvents.length > 1" class="candidate-bar-actions">
        <button class="btn btn-adopt" @click="emit('adopt-all')">全部采纳</button>
        <button class="btn btn-reject" @click="emit('reject-all')">全部拒绝</button>
      </div>
    </div>

    <div class="candidate-scroll">
      <TransitionGroup name="candidate-slide" tag="div" class="candidate-row">
        <article
          v-for="event in candidateEvents"
          :key="event.event_id"
          class="candidate-card"
          :class="[event.confidence]"
        >
          <div class="candidate-head">
            <div class="candidate-head-left">
              <p class="mono candidate-step">STEP {{ event.step }}</p>
              <h4 class="candidate-title">{{ event.title || "未命名事件" }}</h4>
            </div>
            <div class="candidate-badges">
              <DirectorStatusRibbon
                v-if="event.confidence"
                status="candidate"
                :confidence="event.confidence"
              />
              <span class="source-badge">{{ sourceLabel(event.event_source) }}</span>
            </div>
          </div>

          <p
            class="candidate-summary"
            :class="{ clamped: !expandedIds.has(event.event_id) }"
          >{{ event.summary }}</p>
          <button
            v-if="event.summary?.length > 80"
            class="btn-expand"
            @click="toggleExpand(event.event_id)"
          >{{ expandedIds.has(event.event_id) ? "收起" : "展开全文" }}</button>
          <p v-if="event.confidence_reason" class="candidate-reason">{{ event.confidence_reason }}</p>

          <div v-if="event.driving_entities?.length" class="actor-chip-row">
            <span
              v-for="driver in event.driving_entities"
              :key="driver"
              class="actor-avatar-mini"
              :title="driver"
            >{{ driver.charAt(0) }}</span>
            <span class="actor-names-inline">{{ event.driving_entities.join("、") }}</span>
          </div>

          <!-- Normal actions -->
          <div v-if="editingEventId !== event.event_id" class="candidate-actions">
            <button class="btn btn-adopt" @click="emit('adopt-event', { eventId: event.event_id })">采纳</button>
            <button class="btn btn-edit" @click="startEdit(event)">编辑</button>
            <button class="btn btn-reject" @click="emit('reject-event', { eventId: event.event_id })">拒绝</button>
          </div>

          <!-- Inline edit -->
          <div v-else class="candidate-edit">
            <textarea
              v-model="editText"
              rows="3"
              class="candidate-textarea"
              placeholder="修改事件描述后采纳…"
              @click.stop
            ></textarea>
            <div class="candidate-edit-actions">
              <button class="btn btn-adopt" @click.stop="submitEdit(event.event_id)">确认并采纳</button>
              <button class="btn" @click.stop="cancelEdit">取消</button>
            </div>
          </div>
        </article>
      </TransitionGroup>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";

import DirectorStatusRibbon from "./DirectorStatusRibbon.vue";

defineProps({
  candidateEvents: { type: Array, default: () => [] },
  streamPhase: { type: String, default: "idle" },
});

const emit = defineEmits([
  "adopt-event",
  "reject-event",
  "edit-event",
  "adopt-all",
  "reject-all",
]);

const SOURCE_LABELS = {
  archive_based: "档案驱动",
  goal_driven: "目标驱动",
  variable_reaction: "变量触发",
  agent_initiative: "角色主动",
  system: "系统生成",
};

function sourceLabel(value) {
  return SOURCE_LABELS[value] || value || "未知来源";
}

/* ── expand / collapse ─────────────────────────────────────── */
const expandedIds = ref(new Set());

function toggleExpand(eventId) {
  const next = new Set(expandedIds.value);
  if (next.has(eventId)) {
    next.delete(eventId);
  } else {
    next.add(eventId);
  }
  expandedIds.value = next;
}

/* ── inline editing ────────────────────────────────────────── */
const editingEventId = ref("");
const editText = ref("");

function startEdit(event) {
  editingEventId.value = event.event_id;
  editText.value = event.summary || "";
}

function cancelEdit() {
  editingEventId.value = "";
  editText.value = "";
}

function submitEdit(eventId) {
  if (editText.value.trim()) {
    emit("edit-event", { eventId, consequence: editText.value.trim() });
  }
  editingEventId.value = "";
  editText.value = "";
}
</script>

<style scoped src="./DirectorCandidateReview.css"></style>
