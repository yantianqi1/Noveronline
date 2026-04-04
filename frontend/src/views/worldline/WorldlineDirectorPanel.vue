<template>
  <article class="workbench-card panel director-panel">
    <header class="director-header">
      <div>
        <p class="director-kicker mono">DIRECTOR CONSOLE</p>
        <h2 class="card-title">世界线导演台</h2>
      </div>
      <div class="focus-pill">
        <span class="mono">{{ headerStepLabel }}</span>
        <strong>{{ headerTitle }}</strong>
      </div>
    </header>

    <DirectorSpotlight
      :current-world="currentWorld"
      :task-snapshot="taskSnapshot"
      :timeline="timeline"
      :stream-phase="streamPhase"
      :thinking-info="thinkingInfo"
    />

    <DirectorCandidateReview
      v-if="showCandidates"
      :candidate-events="candidateEvents"
      :stream-phase="streamPhase"
      @adopt-event="emit('adopt-event', $event)"
      @reject-event="emit('reject-event', $event)"
      @edit-event="emit('edit-event', $event)"
      @adopt-all="emit('adopt-all')"
      @reject-all="emit('reject-all')"
    />

    <DirectorTimeline :timeline="timeline" />
  </article>
</template>

<script setup>
import { computed } from "vue";

import { buildStepLabel } from "../../utils/chineseDisplay.js";
import DirectorSpotlight from "./director/DirectorSpotlight.vue";
import DirectorCandidateReview from "./director/DirectorCandidateReview.vue";
import DirectorTimeline from "./director/DirectorTimeline.vue";

const props = defineProps({
  sessionId: { type: String, default: "" },
  currentWorld: { type: Object, default: null },
  timeline: { type: Array, default: () => [] },
  taskSnapshot: { type: Object, default: null },
  candidateEvents: { type: Array, default: () => [] },
  streamPhase: { type: String, default: "idle" },
  thinkingInfo: { type: Object, default: null },
});

const emit = defineEmits([
  "adopt-event",
  "reject-event",
  "edit-event",
  "adopt-all",
  "reject-all",
]);

const headerStepLabel = computed(() => buildStepLabel(props.currentWorld?.current_step ?? 0));
const headerTitle = computed(() => props.currentWorld?.title || "当前世界");

const showCandidates = computed(() =>
  props.candidateEvents.length > 0 ||
  props.streamPhase === "thinking" ||
  props.streamPhase === "streaming",
);
</script>

<style scoped src="./WorldlineDirectorPanel.css"></style>
