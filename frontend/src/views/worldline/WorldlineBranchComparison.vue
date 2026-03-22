<template>
  <article class="workbench-card panel full">
    <div class="header-row">
      <div>
        <h2 class="card-title">平行世界分支对比</h2>
        <p class="hint-text">并列查看不同世界线的核心偏移、最新事件、关键状态与待处理事项。</p>
      </div>
      <div class="meta-chip mono" v-if="comparisonAxes.selected_branch_ids?.length">
        {{ comparisonAxes.selected_branch_ids.length }} 条分支
      </div>
    </div>

    <div v-if="!sessionId" class="empty">先创建世界线会话，对比面板会自动展示各条平行世界的演化差异。</div>
    <div v-else-if="!cards.length" class="empty">当前没有可对比的分支数据。</div>
    <div v-else class="comparison-grid">
      <article
        v-for="item in cards"
        :key="item.branch_id"
        class="branch-card"
        :class="{ active: selectedBranchId === item.branch_id }"
      >
        <div class="branch-head">
          <div>
            <div class="branch-title">{{ item.title || item.branch_id }}</div>
            <div class="branch-meta mono">{{ buildStepLabel(item.current_step ?? 0) }} · {{ formatBranchStatus(item.status) }}</div>
          </div>
          <span class="status-pill">{{ item.branch_id }}</span>
        </div>

        <section class="section-block">
          <div class="section-title">核心偏移</div>
          <p>{{ item.core_change || "暂无描述" }}</p>
        </section>

        <section class="section-block">
          <div class="section-title">最新事件</div>
          <div v-if="item.latest_event" class="event-card">
            <strong>{{ item.latest_event.title || "最新事件" }}</strong>
            <p>{{ item.latest_event.summary || "暂无事件摘要" }}</p>
          </div>
          <div v-else class="mini-empty">尚未生成事件。</div>
        </section>

        <section class="section-block">
          <div class="section-title">关键角色状态</div>
          <div v-if="item.key_actor_states?.length" class="mini-list">
            <div v-for="actor in item.key_actor_states" :key="actor.name" class="mini-card">
              <strong>{{ actor.name }}</strong>
              <span>{{ formatAgentStatus(actor.status) }}</span>
              <p>{{ actor.drive || "暂无动机" }}</p>
            </div>
          </div>
          <div v-else class="mini-empty">暂无角色状态。</div>
        </section>

        <section class="section-block">
          <div class="section-title">组织与关系</div>
          <div v-if="item.key_organization_states?.length" class="mini-list">
            <div v-for="org in item.key_organization_states" :key="org.name" class="mini-card soft">
              <strong>{{ org.name }}</strong>
              <span>{{ formatAgentStatus(org.status) }}</span>
              <p>{{ formatRoleText(org.role) }}</p>
            </div>
          </div>
          <div v-if="item.relation_highlights?.length" class="relation-list">
            <div
              v-for="relation in item.relation_highlights"
              :key="`${relation.source}_${relation.target}_${relation.change}`"
              class="relation-row"
            >
              <strong>{{ relation.source }} → {{ relation.target }}</strong>
              <span>{{ formatRelationChange(relation.change) }}</span>
            </div>
          </div>
          <div v-else class="mini-empty">暂无关系变化高亮。</div>
        </section>

        <section class="section-block">
          <div class="section-title">待处理事项</div>
          <div class="pending-grid">
            <div class="pending-box">
              <strong>{{ item.pending?.variable_count ?? 0 }}</strong>
              <span>待处理变量</span>
              <p>{{ joinText(item.pending?.variable_names) }}</p>
            </div>
            <div class="pending-box">
              <strong>{{ item.pending?.action_count ?? 0 }}</strong>
              <span>待处理动作</span>
              <p>{{ joinText(item.pending?.action_labels) }}</p>
            </div>
          </div>
        </section>
      </article>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";
import {
  buildStepLabel,
  formatAgentStatus,
  formatBranchStatus,
  formatRelationChange,
  formatRoleText,
} from "../../utils/chineseDisplay";

const props = defineProps({
  comparison: {
    type: Object,
    default: null,
  },
  selectedBranchId: {
    type: String,
    default: "",
  },
  sessionId: {
    type: String,
    default: "",
  },
});

const cards = computed(() => props.comparison?.branches || []);
const comparisonAxes = computed(() => props.comparison?.comparison_axes || {});

function joinText(items) {
  return items?.length ? items.join(" / ") : "暂无";
}
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.meta-chip {
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  padding: 6px 10px;
  background: #fff8ea;
}

.comparison-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.branch-card {
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: linear-gradient(180deg, #fffdf7 0%, #fff8ea 100%);
  padding: 14px;
}

.branch-card.active {
  border-color: var(--line-strong);
  box-shadow: 0 12px 28px rgba(94, 58, 12, 0.08);
}

.branch-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.branch-title {
  font-size: 1.05rem;
  font-weight: 700;
}

.branch-meta {
  color: var(--text-sub);
  margin-top: 4px;
}

.status-pill {
  border-radius: 999px;
  background: #f7ead3;
  padding: 6px 10px;
  font-size: 0.75rem;
}

.section-block {
  margin-top: 14px;
}

.section-title {
  font-weight: 700;
  margin-bottom: 6px;
}

.event-card,
.mini-card,
.pending-box {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.7);
  padding: 10px;
}

.mini-list,
.pending-grid {
  display: grid;
  gap: 8px;
}

.pending-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mini-card.soft {
  background: #fffaf1;
}

.mini-card span,
.pending-box span,
.relation-row span {
  color: var(--text-sub);
  display: block;
  margin-top: 4px;
}

.mini-card p,
.pending-box p,
.event-card p {
  margin: 6px 0 0;
  color: #5a4d38;
}

.relation-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.relation-row {
  border-top: 1px dashed var(--line-soft);
  padding-top: 8px;
}

.relation-row:first-child {
  border-top: none;
  padding-top: 0;
}

.empty,
.mini-empty {
  color: var(--text-sub);
}

@media (max-width: 900px) {
  .pending-grid {
    grid-template-columns: 1fr;
  }
}
</style>
