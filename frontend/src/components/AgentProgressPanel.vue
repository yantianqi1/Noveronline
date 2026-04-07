<template>
  <div class="agent-progress-panel" :class="{ collapsed: isCollapsed }">
    <!-- 折叠态摘要条 -->
    <div v-if="isCollapsed" class="collapsed-summary" @click="isCollapsed = false">
      <span class="collapsed-icon">&#10003;</span>
      <span class="collapsed-text">
        创作流程完成
        <span v-if="revisionCount > 0" class="collapsed-revision">· 修订 {{ revisionCount }} 次</span>
        <span v-if="finalScore !== null" class="collapsed-score" :class="scoreClass">· {{ finalScore }}分</span>
      </span>
      <span class="collapsed-arrow">&#9662;</span>
    </div>

    <!-- 展开态内容 -->
    <template v-if="!isCollapsed">
      <div
        v-for="agent in agents"
        :key="agent.id"
        class="agent-row"
        :class="[agent.status, { 'has-issues': agent.issues?.length }]"
      >
        <div class="agent-indicator">
          <span v-if="agent.status === 'running'" class="agent-spinner"></span>
          <span v-else-if="agent.status === 'done'" class="agent-check">&#10003;</span>
          <span v-else-if="agent.status === 'error'" class="agent-error-icon">&#10007;</span>
          <span v-else class="agent-pending">&#9675;</span>
        </div>
        <div class="agent-info">
          <span class="agent-name">{{ agent.label }}</span>
          <span v-if="agent.message" class="agent-message">{{ agent.message }}</span>
        </div>

        <!-- 通用 detail 展开按钮 -->
        <div v-if="hasDetail(agent)" class="agent-detail-section">
          <n-button text size="tiny" @click="agent.detailExpanded = !agent.detailExpanded">
            {{ agent.detailExpanded ? '收起详情' : '查看详情' }}
          </n-button>
          <div v-if="agent.detailExpanded" class="detail-content">
            <!-- context_agent detail -->
            <template v-if="agent.id === 'context_agent' && agent.detail">
              <div v-if="agent.detail.must_know_items?.length" class="detail-group">
                <div class="detail-group-title">必知条目（{{ agent.detail.must_know_items.length }}）</div>
                <div v-for="(item, i) in agent.detail.must_know_items" :key="'mk' + i" class="detail-item">{{ item }}</div>
              </div>
              <div v-if="agent.detail.warnings?.length" class="detail-group">
                <div class="detail-group-title warning">风险提示（{{ agent.detail.warnings.length }}）</div>
                <div v-for="(item, i) in agent.detail.warnings" :key="'w' + i" class="detail-item warning">{{ item }}</div>
              </div>
              <div v-if="agent.detail.has_continuity" class="detail-item">已注入前章连续性上下文</div>
            </template>
            <!-- memory_agent detail -->
            <template v-if="agent.id === 'memory_agent' && agent.detail?.memories?.length">
              <div class="detail-group">
                <div class="detail-group-title">相关记忆</div>
                <div v-for="(mem, i) in agent.detail.memories" :key="'mem' + i" class="detail-item">{{ mem.summary }}</div>
              </div>
            </template>
            <!-- style_agent detail -->
            <template v-if="agent.id === 'style_agent' && agent.detail">
              <div class="detail-item" v-if="agent.detail.rendered_hints">{{ agent.detail.rendered_hints }}</div>
              <div class="detail-item" v-else>
                视角：{{ agent.detail.pov || '未知' }} · 节奏：{{ agent.detail.pace || '均匀适中' }}
              </div>
            </template>
          </div>
        </div>

        <!-- reviewer issues 折叠列表 -->
        <div v-if="agent.issues?.length" class="agent-issues">
          <n-button text size="tiny" @click="agent.issuesExpanded = !agent.issuesExpanded">
            {{ agent.issuesExpanded ? '收起' : '展开' }} {{ agent.issues.length }} 个问题
          </n-button>
          <div v-if="agent.issuesExpanded" class="issues-list">
            <div v-for="(issue, idx) in agent.issues" :key="idx" class="issue-item">
              <n-tag size="small" :type="issue.severity === 'high' ? 'error' : issue.severity === 'medium' ? 'warning' : 'default'">{{ issue.severity }}</n-tag>
              <span class="issue-dimension">[{{ issue.dimension }}]</span>
              <span class="issue-desc">{{ issue.description }}</span>
              <div v-if="issue.suggestion" class="issue-suggestion">{{ issue.suggestion }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 修订信息 -->
      <div v-if="revisionCount > 0" class="revision-info">
        <n-tag size="small" type="warning">修订 {{ revisionCount }} 次</n-tag>
      </div>

      <!-- 未解决问题 -->
      <div v-if="unresolvedIssues.length" class="unresolved-section">
        <div class="unresolved-header">未解决问题（{{ unresolvedIssues.length }}）</div>
        <div v-for="(issue, idx) in unresolvedIssues" :key="'u' + idx" class="issue-item">
          <n-tag size="small" :type="issue.severity === 'high' ? 'error' : issue.severity === 'medium' ? 'warning' : 'default'">{{ issue.severity }}</n-tag>
          <span class="issue-dimension">[{{ issue.dimension }}]</span>
          <span class="issue-desc">{{ issue.description }}</span>
        </div>
      </div>

      <!-- 最终评分 -->
      <div v-if="finalScore !== null" class="final-score">
        <span class="score-label">审校评分</span>
        <span class="score-value" :class="scoreClass">{{ finalScore }}</span>
      </div>

      <!-- 折叠按钮（所有步骤完成后显示） -->
      <div v-if="allDone" class="collapse-trigger" @click="isCollapsed = true">
        <span class="collapse-trigger-text">收起流程面板</span>
        <span class="collapse-trigger-arrow">&#9652;</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { NButton, NTag } from "naive-ui";

const props = defineProps({
  agents: { type: Array, default: () => [] },
  revisionCount: { type: Number, default: 0 },
  unresolvedIssues: { type: Array, default: () => [] },
  finalScore: { type: Number, default: null },
});

const isCollapsed = ref(false);

const allDone = computed(() => {
  if (!props.agents.length) return false;
  return props.agents.every((a) => a.status === "done" || a.status === "error");
});

const scoreClass = computed(() => {
  if (props.finalScore === null) return "";
  if (props.finalScore >= 80) return "score-high";
  if (props.finalScore >= 60) return "score-medium";
  return "score-low";
});

function hasDetail(agent) {
  if (!agent.detail) return false;
  if (agent.id === "context_agent") {
    return agent.detail.must_know_items?.length || agent.detail.warnings?.length || agent.detail.has_continuity;
  }
  if (agent.id === "memory_agent") {
    return agent.detail.memories?.length > 0;
  }
  if (agent.id === "style_agent") {
    return !!(agent.detail.rendered_hints || agent.detail.pov);
  }
  return false;
}

// 完成后自动折叠
let collapseTimer = null;
watch(allDone, (isDone) => {
  if (isDone) {
    collapseTimer = setTimeout(() => {
      isCollapsed.value = true;
    }, 2000);
  } else {
    isCollapsed.value = false;
    if (collapseTimer) {
      clearTimeout(collapseTimer);
      collapseTimer = null;
    }
  }
});

onBeforeUnmount(() => {
  if (collapseTimer) {
    clearTimeout(collapseTimer);
    collapseTimer = null;
  }
});

// agents 重新初始化时展开
watch(
  () => props.agents.length,
  () => {
    if (props.agents.some((a) => a.status === "pending" || a.status === "running")) {
      isCollapsed.value = false;
    }
  },
);
</script>

<style scoped>
.agent-progress-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 0;
}

/* ─── 折叠态摘要条 ─── */
.collapsed-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.08), rgba(59, 130, 246, 0.06));
  border: 1px solid rgba(34, 197, 94, 0.2);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}
.collapsed-summary:hover {
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.12), rgba(59, 130, 246, 0.1));
  border-color: rgba(34, 197, 94, 0.35);
}
.collapsed-icon {
  color: #22c55e;
  font-weight: bold;
  font-size: 14px;
}
.collapsed-text {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1f2937);
}
.collapsed-revision {
  color: #92400e;
}
.collapsed-score {
  font-weight: 600;
}
.collapsed-score.score-high { color: #22c55e; }
.collapsed-score.score-medium { color: #f59e0b; }
.collapsed-score.score-low { color: #ef4444; }
.collapsed-arrow {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
}

/* ─── agent 行 ─── */
.agent-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--card-bg, rgba(0,0,0,0.02));
  transition: background 0.2s;
  flex-wrap: wrap;
}
.agent-row.running {
  background: var(--accent-bg, rgba(59, 130, 246, 0.08));
}
.agent-row.done {
  opacity: 0.85;
}
.agent-row.error {
  background: rgba(239, 68, 68, 0.08);
}
.agent-indicator {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.agent-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(59, 130, 246, 0.3);
  border-top-color: rgb(59, 130, 246);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.agent-check { color: #22c55e; font-weight: bold; font-size: 14px; }
.agent-error-icon { color: #ef4444; font-weight: bold; font-size: 14px; }
.agent-pending { color: #9ca3af; font-size: 14px; }
.agent-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}
.agent-message {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
}

/* ─── 通用 detail 展开 ─── */
.agent-detail-section {
  width: 100%;
  margin-top: 2px;
}
.detail-toggle {
  font-size: 11px;
  color: var(--accent-color, #3b82f6);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 0;
  text-decoration: underline;
}
.detail-content {
  margin-top: 4px;
  padding: 8px 10px;
  background: rgba(0,0,0,0.03);
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-group {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.detail-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}
.detail-group-title.warning {
  color: #92400e;
}
.detail-item {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary, #6b7280);
  padding-left: 8px;
  border-left: 2px solid rgba(0,0,0,0.06);
}
.detail-item.warning {
  border-left-color: rgba(245, 158, 11, 0.4);
}

/* ─── issues ─── */
.agent-issues {
  width: 100%;
  margin-top: 4px;
}
.issues-toggle {
  font-size: 11px;
  color: var(--accent-color, #3b82f6);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 0;
  text-decoration: underline;
}
.issues-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  padding: 6px 8px;
  background: rgba(0,0,0,0.03);
  border-radius: 4px;
}
.issue-item {
  font-size: 12px;
  line-height: 1.5;
}
.issue-severity {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  margin-right: 4px;
  text-transform: uppercase;
}
.issue-severity.high { background: #fecaca; color: #991b1b; }
.issue-severity.medium { background: #fef3c7; color: #92400e; }
.issue-severity.low { background: #e5e7eb; color: #374151; }
.issue-dimension { color: var(--text-secondary, #6b7280); margin-right: 4px; }
.issue-suggestion {
  margin-top: 2px;
  padding-left: 12px;
  font-style: italic;
  color: var(--text-secondary, #6b7280);
}

/* ─── 修订和评分 ─── */
.revision-info {
  padding: 4px 10px;
}
.revision-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(245, 158, 11, 0.15);
  color: #92400e;
}
.unresolved-section {
  padding: 8px 10px;
  background: rgba(239, 68, 68, 0.06);
  border-radius: 6px;
  margin-top: 4px;
}
.unresolved-header {
  font-size: 12px;
  font-weight: 600;
  color: #991b1b;
  margin-bottom: 4px;
}
.final-score {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
}
.score-label { font-size: 12px; color: var(--text-secondary, #6b7280); }
.score-value {
  font-size: 18px;
  font-weight: 700;
}
.score-high { color: #22c55e; }
.score-medium { color: #f59e0b; }
.score-low { color: #ef4444; }

/* ─── 折叠触发器 ─── */
.collapse-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 4px 0;
  cursor: pointer;
  user-select: none;
  opacity: 0.6;
  transition: opacity 0.2s;
}
.collapse-trigger:hover {
  opacity: 1;
}
.collapse-trigger-text {
  font-size: 11px;
  color: var(--text-secondary, #6b7280);
}
.collapse-trigger-arrow {
  font-size: 10px;
  color: var(--text-secondary, #6b7280);
}
</style>
