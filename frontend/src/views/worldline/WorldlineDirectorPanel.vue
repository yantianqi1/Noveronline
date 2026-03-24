<template>
  <article class="workbench-card panel director-panel">
    <header class="director-header">
      <div>
        <p class="director-kicker mono">DIRECTOR CONSOLE</p>
        <h2 class="card-title">世界线导演台</h2>
        <p class="director-copy">先看当前世界推进到了哪里，再看这一步是谁在推动剧情、局势如何被改写。</p>
      </div>
      <div class="focus-pill">
        <span class="mono">{{ worldSummary.stepLabel }}</span>
        <strong>{{ worldSummary.title }}</strong>
      </div>
    </header>

    <section class="director-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">01 / 当前世界</p>
          <h3 class="section-title">世界状态总览</h3>
        </div>
        <p class="section-copy">自动演化进度、待处理项和最新事件会在这里同步浮出水面。</p>
      </div>

      <article class="lane-card active">
        <div class="lane-head">
          <strong>{{ worldSummary.title }}</strong>
          <span class="lane-status">{{ worldSummary.statusLabel }}</span>
        </div>
        <div class="lane-meta">
          <span class="mono">{{ worldSummary.stepLabel }}</span>
          <span class="mono">待处理 {{ worldSummary.pendingCount }}</span>
        </div>
        <div class="lane-progress" aria-hidden="true">
          <div class="lane-progress-fill" :style="{ width: `${worldSummary.progress}%` }"></div>
        </div>
        <div class="lane-event">{{ worldSummary.latestEventTitle }}</div>
        <p class="spotlight-copy">{{ worldSummary.latestEventSummary }}</p>
        <div class="chip-row">
          <span v-for="driver in worldSummary.drivers" :key="driver" class="driver-chip">
            {{ driver }}
          </span>
          <span v-if="!worldSummary.drivers.length" class="driver-chip muted">等待新驱动者</span>
        </div>
      </article>
    </section>

    <section class="director-section narrative-shell">
      <div class="section-head">
        <div>
          <p class="section-index mono">02 / 当前主叙事</p>
          <h3 class="section-title">谁在推动剧情</h3>
        </div>
        <p class="section-copy">驱动者、最新事件、关系变动和待处理项按同一条观看路径组织。</p>
      </div>

      <div class="narrative-grid">
        <article class="narrative-card spotlight">
          <div class="spotlight-head">
            <div>
              <p class="mono spotlight-step">{{ focusNarrative.stepLabel }}</p>
              <h3>{{ focusNarrative.latestEvent.title }}</h3>
            </div>
            <span class="spotlight-status">{{ focusNarrative.statusLabel }}</span>
          </div>
          <p class="spotlight-copy">{{ focusNarrative.latestEvent.digest }}</p>
          <div class="story-block">
            <span class="story-label">核心偏移</span>
            <p>{{ focusNarrative.coreChange }}</p>
          </div>
          <div class="story-block">
            <span class="story-label">本步变量触发</span>
            <div class="chip-row">
              <span
                v-for="variable in focusNarrative.latestEvent.variableEffects"
                :key="`${focusNarrative.worldId}_${variable.name}`"
                class="driver-chip"
              >
                {{ variable.name }}
              </span>
              <span v-if="!focusNarrative.latestEvent.variableEffects.length" class="driver-chip muted">本步没有新增变量</span>
            </div>
          </div>
          <div class="story-block">
            <span class="story-label">当前驱动者</span>
            <div class="chip-row">
              <span v-for="driver in focusNarrative.latestEvent.drivers" :key="driver" class="driver-chip active">
                {{ driver }}
              </span>
              <span v-if="!focusNarrative.latestEvent.drivers.length" class="driver-chip muted">暂无明确驱动者</span>
            </div>
          </div>
        </article>

        <article class="narrative-card">
          <div class="block-head">
            <h4>本步执行动作</h4>
            <span class="mono">
              {{ focusNarrative.latestEvent.actionEffects.length || focusNarrative.dispatchActors.length }}
              {{ focusNarrative.latestEvent.actionEffects.length ? "条" : "位" }}
            </span>
          </div>
          <div v-if="focusNarrative.latestEvent.actionEffects.length" class="dispatch-list">
            <article
              v-for="action in focusNarrative.latestEvent.actionEffects"
              :key="`${action.actor}_${action.action}`"
              class="dispatch-card"
              :class="{ driver: focusNarrative.latestEvent.drivers.includes(action.actor) }"
            >
              <div class="dispatch-head">
                <strong>{{ action.actor }}</strong>
                <span>执行中</span>
              </div>
              <p class="dispatch-meta">{{ action.target || "当前世界" }}</p>
              <p class="dispatch-drive">{{ action.action }}</p>
              <p v-if="action.intent" class="dispatch-meta">动机：{{ action.intent }}</p>
            </article>
          </div>
          <div v-else-if="focusNarrative.dispatchActors.length" class="dispatch-list">
            <article
              v-for="actor in focusNarrative.dispatchActors"
              :key="actor.name"
              class="dispatch-card"
              :class="{ driver: actor.isDriver }"
            >
              <div class="dispatch-head">
                <strong>{{ actor.name }}</strong>
                <span>{{ actor.status }}</span>
              </div>
              <p class="dispatch-meta">{{ actor.role }}</p>
              <p class="dispatch-drive">{{ actor.drive }}</p>
            </article>
          </div>
          <p v-else class="mini-empty">{{ focusNarrative.emptyMessage }}</p>
        </article>

        <article class="narrative-card">
          <div class="block-head">
            <h4>关系与待处理</h4>
            <span class="mono">持续演化</span>
          </div>
          <div class="pending-grid">
            <div class="pending-box">
              <strong>{{ focusNarrative.pending.variableCount }}</strong>
              <span>待处理变量</span>
              <p>{{ joinText(focusNarrative.pending.variableNames, "暂无待处理变量") }}</p>
            </div>
            <div class="pending-box">
              <strong>{{ focusNarrative.pending.actionCount }}</strong>
              <span>待处理动作</span>
              <p>{{ joinText(focusNarrative.pending.actionLabels, "暂无待处理动作") }}</p>
            </div>
          </div>
          <div class="relation-list">
            <div
              v-for="relation in focusNarrative.relationChanges"
              :key="`${relation.source}_${relation.target}_${relation.label}`"
              class="relation-card"
            >
              <strong>{{ relation.source }} → {{ relation.target }}</strong>
              <span>{{ relation.label }}</span>
              <p>{{ relation.note }}</p>
            </div>
            <p v-if="!focusNarrative.relationChanges.length" class="mini-empty">当前回合还没有显式关系改写。</p>
          </div>
        </article>

        <article class="narrative-card">
          <div class="block-head">
            <h4>局势中的组织</h4>
            <span class="mono">{{ focusNarrative.worldForces.length }} 个焦点</span>
          </div>
          <div v-if="focusNarrative.worldForces.length" class="force-list">
            <article v-for="item in focusNarrative.worldForces" :key="item.name" class="force-card">
              <div class="dispatch-head">
                <strong>{{ item.name }}</strong>
                <span>{{ item.status }}</span>
              </div>
              <p class="dispatch-meta">{{ item.role }}</p>
              <p class="dispatch-drive">{{ item.summary }}</p>
            </article>
          </div>
          <p v-else class="mini-empty">暂无组织级局势摘要。</p>
        </article>
      </div>
    </section>

    <section class="director-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">03 / 世界状态变更流</p>
          <h3 class="section-title">局势如何被改写</h3>
        </div>
        <p class="section-copy">每一步都记录变量影响、关系张力和状态变化，不再只是大段摘要文案。</p>
      </div>

      <div v-if="worldShiftFeed.items.length" class="shift-feed">
        <article v-for="item in worldShiftFeed.items" :key="item.eventId || item.step" class="shift-card">
          <div class="shift-head">
            <div>
              <p class="mono spotlight-step">{{ item.stepLabel }}</p>
              <h4>{{ item.title }}</h4>
            </div>
            <div class="chip-row">
              <span v-for="driver in item.drivers" :key="`${item.eventId}_${driver}`" class="driver-chip active">
                {{ driver }}
              </span>
            </div>
          </div>
          <p class="spotlight-copy">{{ item.summary }}</p>
          <div class="shift-grid">
            <div class="shift-box">
              <span class="story-label">变量影响</span>
              <p v-for="variable in item.variableEffects" :key="`${item.eventId}_${variable.name}`">
                {{ variable.name }}：{{ variable.description }}
              </p>
              <p v-if="!item.variableEffects.length" class="mini-empty">本步没有新增变量扰动。</p>
            </div>
            <div class="shift-box">
              <span class="story-label">执行动作</span>
              <p v-for="action in item.actionEffects" :key="`${item.eventId}_${action.actor}_${action.action}`">
                {{ action.actor }}：{{ action.action }}
              </p>
              <p v-if="!item.actionEffects.length" class="mini-empty">本步没有新增动作落地。</p>
            </div>
            <div class="shift-box">
              <span class="story-label">关系变化</span>
              <p v-for="relation in item.relationChanges" :key="`${item.eventId}_${relation.source}_${relation.target}`">
                {{ relation.source }} → {{ relation.target }} · {{ relation.label }}
              </p>
              <p v-if="!item.relationChanges.length" class="mini-empty">本步没有显式关系波动。</p>
            </div>
            <div class="shift-box">
              <span class="story-label">状态变化</span>
              <p v-for="state in item.stateChanges" :key="`${item.eventId}_${state.entityName}`">
                {{ state.entityName }} · {{ state.status }} · {{ state.reason }}
              </p>
              <p v-if="!item.stateChanges.length" class="mini-empty">本步没有新增状态变更。</p>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="empty-shift">{{ worldShiftFeed.emptyMessage }}</div>
    </section>
  </article>
</template>

<script setup>
import { computed } from "vue";

import {
  buildWorldlineCurrentWorldSummary,
  buildWorldlineFocusNarrative,
  buildWorldlineWorldShiftFeed,
} from "./worldlineDirectorPanelViewModel.js";

const props = defineProps({
  sessionId: { type: String, default: "" },
  currentWorld: { type: Object, default: null },
  timeline: { type: Array, default: () => [] },
  taskSnapshot: { type: Object, default: null },
});

const worldSummary = computed(() => buildWorldlineCurrentWorldSummary({
  currentWorld: props.currentWorld,
  taskSnapshot: props.taskSnapshot,
  timeline: props.timeline,
}));

const focusNarrative = computed(() => buildWorldlineFocusNarrative({
  currentWorld: props.currentWorld,
  taskSnapshot: props.taskSnapshot,
  timeline: props.timeline,
}));

const worldShiftFeed = computed(() => buildWorldlineWorldShiftFeed(props.timeline));

function joinText(items = [], emptyText) {
  return items.length ? items.join(" / ") : emptyText;
}
</script>

<style scoped src="./WorldlineDirectorPanel.css"></style>
