<template>
  <article
    class="step-card"
    :class="{ expanded, latest: isLatest }"
    @click="emit('toggle-expand')"
  >
    <div class="step-head">
      <div class="step-head-left">
        <span class="mono step-label">{{ stepLabel }}</span>
        <h4 class="step-title">{{ title }}</h4>
      </div>
      <div class="step-head-right">
        <DirectorStatusRibbon v-if="status" :status="status" />
        <span v-if="isLatest" class="latest-badge mono">最新</span>
        <span class="expand-icon" :class="{ open: expanded }">&#9662;</span>
      </div>
    </div>

    <!-- Collapsed: actor avatar chips + summary -->
    <div v-if="actorSummaries.length && !expanded" class="actor-chip-row">
      <span
        v-for="actor in actorSummaries"
        :key="actor.name"
        class="actor-avatar-mini"
        :title="actor.name"
      >{{ actor.initial }}</span>
      <span class="step-summary-inline">{{ summary }}</span>
    </div>
    <p v-else-if="!expanded" class="step-summary">{{ summary }}</p>

    <!-- Expanded: actor-centric detail -->
    <Transition name="timeline-expand">
      <div v-if="expanded" class="step-detail">
        <!-- Per-actor rows -->
        <div v-if="actionEffects.length || drivers.length" class="detail-actors">
          <div
            v-for="actor in expandedActors"
            :key="actor.name"
            class="detail-actor-row"
          >
            <span class="detail-actor-avatar">{{ actor.initial }}</span>
            <strong class="detail-actor-name">{{ actor.name }}</strong>
            <span v-if="actor.action" class="detail-actor-action">{{ actor.action }}</span>
            <template v-if="actor.target">
              <span class="detail-actor-arrow">&rarr;</span>
              <span>{{ actor.target }}</span>
            </template>
          </div>
        </div>

        <!-- Relation changes -->
        <div v-if="relationChanges.length" class="detail-relations">
          <div
            v-for="r in relationChanges"
            :key="`${r.source}_${r.target}`"
            class="detail-relation-item"
          >
            <span class="detail-relation-arrow">&#10239;</span>
            {{ r.source }} &rarr; {{ r.target }} &middot; {{ r.label }}
          </div>
        </div>

        <!-- Variable footnote -->
        <div v-if="variableEffects.length" class="detail-var-footnote">
          <span class="detail-var-label">变量</span>
          <span v-for="v in variableEffects" :key="v.name" class="detail-var-chip">{{ v.name }}</span>
        </div>
      </div>
    </Transition>
  </article>
</template>

<script setup>
import { computed } from "vue";

import DirectorStatusRibbon from "./DirectorStatusRibbon.vue";

const props = defineProps({
  step: { type: Number, default: 0 },
  stepLabel: { type: String, default: "" },
  title: { type: String, default: "" },
  summary: { type: String, default: "" },
  drivers: { type: Array, default: () => [] },
  variableEffects: { type: Array, default: () => [] },
  actionEffects: { type: Array, default: () => [] },
  relationChanges: { type: Array, default: () => [] },
  stateChanges: { type: Array, default: () => [] },
  actorSummaries: { type: Array, default: () => [] },
  status: { type: String, default: "" },
  expanded: { type: Boolean, default: false },
  isLatest: { type: Boolean, default: false },
});

const emit = defineEmits(["toggle-expand"]);

// Build expanded actor rows from actionEffects + drivers
const expandedActors = computed(() => {
  const map = new Map();
  for (const a of props.actionEffects) {
    if (!map.has(a.actor)) {
      map.set(a.actor, { name: a.actor, initial: a.actor.charAt(0), action: a.action, target: a.target || "" });
    }
  }
  for (const d of props.drivers) {
    if (!map.has(d)) {
      map.set(d, { name: d, initial: d.charAt(0), action: "", target: "" });
    }
  }
  return [...map.values()];
});
</script>

<style scoped src="./DirectorStepCard.css"></style>
