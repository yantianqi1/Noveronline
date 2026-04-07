<template>
  <section class="timeline-zone">
    <div class="timeline-head">
      <div>
        <p class="section-index mono">演化时间线</p>
        <h3 class="section-title">局势如何被改写</h3>
      </div>
      <span v-if="timelineData.items.length" class="mono timeline-count">
        {{ timelineData.items.length }} 步
      </span>
    </div>

    <div v-if="timelineData.items.length" class="timeline-track">
      <article
        v-for="entry in timelineData.items"
        :key="entry.eventId || entry.step"
        class="timeline-entry"
        :class="{ latest: entry.isLatest }"
      >
        <div class="timeline-dot" :class="{ latest: entry.isLatest }"></div>
        <DirectorStepCard
          :step="entry.step"
          :step-label="entry.stepLabel"
          :title="entry.title"
          :summary="entry.summary"
          :drivers="entry.drivers"
          :variable-effects="entry.variableEffects"
          :action-effects="entry.actionEffects"
          :relation-changes="entry.relationChanges"
          :state-changes="entry.stateChanges"
          :actor-summaries="entry.actorSummaries || []"
          status="canon"
          :expanded="expandedSteps.has(entry.eventId || entry.step)"
          :is-latest="entry.isLatest"
          @toggle-expand="toggleExpand(entry.eventId || entry.step)"
        />
      </article>
    </div>

    <n-empty v-else :description="timelineData.emptyMessage" size="small" />

    <p v-if="timelineData.items.length" class="timeline-footer">
      所有演化数据已归档，可供写手 Agent 参考
    </p>
  </section>
</template>

<script setup>
import { computed, reactive } from "vue";
import { NEmpty } from "naive-ui";

import { buildTimelineEntries } from "./directorTimelineViewModel.js";
import DirectorStepCard from "./DirectorStepCard.vue";

const props = defineProps({
  timeline: { type: Array, default: () => [] },
});

const timelineData = computed(() => buildTimelineEntries(props.timeline));

const expandedSteps = reactive(new Set());

function toggleExpand(key) {
  if (expandedSteps.has(key)) {
    expandedSteps.delete(key);
  } else {
    expandedSteps.add(key);
  }
}
</script>

<style scoped src="./DirectorTimeline.css"></style>
