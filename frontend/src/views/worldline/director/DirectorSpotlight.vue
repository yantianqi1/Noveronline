<template>
  <section class="spotlight-zone">
    <!-- Step header bar -->
    <div class="spotlight-header-bar">
      <span class="mono spotlight-step">{{ spotlight.stepLabel }}</span>
      <h3 class="spotlight-title">{{ spotlight.latestEvent.title }}</h3>
      <DirectorStatusRibbon status="canon" />
    </div>

    <p v-if="spotlight.latestEvent.summary" class="spotlight-summary">
      {{ spotlight.latestEvent.summary }}
    </p>

    <!-- Actor action cards (the hero section) -->
    <div v-if="spotlight.actorActionCards.length" class="actor-flow">
      <TransitionGroup name="candidate-slide" tag="div" class="actor-flow-list">
        <article
          v-for="actor in spotlight.actorActionCards"
          :key="actor.name"
          class="actor-action-card"
          :class="{ driver: actor.isDriver }"
        >
          <!-- Actor identity row -->
          <div class="actor-identity">
            <span class="actor-avatar" :class="{ driver: actor.isDriver }">
              {{ actor.initial }}
            </span>
            <div class="actor-name-block">
              <strong class="actor-name">{{ actor.name }}</strong>
              <span v-if="actor.role" class="actor-role-pill">{{ actor.role }}</span>
              <span v-if="actor.isDriver" class="driver-badge">驱动者</span>
            </div>
            <span v-if="actor.stateChange" class="actor-status-tag">
              {{ actor.stateChange.status }}
            </span>
          </div>

          <!-- Actions this actor took -->
          <div v-for="(act, idx) in actor.actions" :key="idx" class="action-row">
            <span class="action-verb">行动</span>
            <span class="action-text">{{ act.action }}</span>
            <template v-if="act.intent">
              <span class="action-intent-label">意图</span>
              <span class="action-intent">{{ act.intent }}</span>
            </template>
            <template v-if="act.target">
              <span class="action-arrow">&rarr;</span>
              <span class="action-target">{{ act.target }}</span>
            </template>
          </div>

          <!-- Relationship changes involving this actor -->
          <div
            v-for="rel in actor.relationChanges"
            :key="`${rel.source}_${rel.target}`"
            class="relation-row"
          >
            <span class="relation-arrow">&#10239;</span>
            <span class="relation-pair">{{ rel.source }} &rarr; {{ rel.target }}</span>
            <span class="relation-label">{{ rel.label }}</span>
            <span v-if="rel.note" class="relation-note">{{ rel.note }}</span>
          </div>

          <!-- State change reason (if no actions shown) -->
          <p v-if="actor.stateChange?.reason && !actor.actions.length" class="state-reason">
            {{ actor.stateChange.reason }}
          </p>

          <!-- Drive text when actor has no actions or relations -->
          <p v-if="!actor.actions.length && !actor.relationChanges.length && actor.drive" class="actor-drive">
            {{ actor.drive }}
          </p>
        </article>
      </TransitionGroup>
    </div>

    <!-- Empty state -->
    <n-empty v-else-if="spotlight.isEmpty" description="等待推演开始，角色行动会在这里以卡片形式展示。" size="small" />

    <!-- Side effects bar -->
    <div class="side-effects-bar">
      <div v-if="spotlight.latestEvent.variableEffects.length" class="side-effect-group">
        <span class="side-effect-label">变量</span>
        <span
          v-for="v in spotlight.latestEvent.variableEffects"
          :key="v.name"
          class="var-chip"
          :title="v.description"
        >{{ v.name }}</span>
      </div>
      <div class="side-effect-group">
        <span class="side-effect-label">待处理</span>
        <span class="pending-pill"><strong>{{ spotlight.pending.variableCount }}</strong> 变量</span>
        <span class="pending-pill"><strong>{{ spotlight.pending.actionCount }}</strong> 动作</span>
      </div>
    </div>

    <!-- Thinking overlay -->
    <DirectorThinkingOverlay
      :visible="streamPhase === 'thinking'"
      :thinking-info="thinkingInfo"
    />
  </section>
</template>

<script setup>
import { computed, shallowRef, watch } from "vue";
import { NEmpty } from "naive-ui";

import { buildSpotlightData } from "./directorSpotlightViewModel.js";
import DirectorStatusRibbon from "./DirectorStatusRibbon.vue";
import DirectorThinkingOverlay from "./DirectorThinkingOverlay.vue";

const props = defineProps({
  currentWorld: { type: Object, default: null },
  taskSnapshot: { type: Object, default: null },
  timeline: { type: Array, default: () => [] },
  streamPhase: { type: String, default: "idle" },
  thinkingInfo: { type: Object, default: null },
});

const rawSpotlight = computed(() => buildSpotlightData({
  currentWorld: props.currentWorld,
  taskSnapshot: props.taskSnapshot,
  timeline: props.timeline,
}));

// Debounce during streaming to avoid jank from rapid SSE events.
const spotlight = shallowRef(rawSpotlight.value);
let debounceTimer = null;

watch(rawSpotlight, (next) => {
  if (props.streamPhase === "thinking" || props.streamPhase === "streaming") {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { spotlight.value = next; }, 300);
  } else {
    spotlight.value = next;
  }
}, { deep: false });
</script>

<style scoped src="./DirectorSpotlight.css"></style>
