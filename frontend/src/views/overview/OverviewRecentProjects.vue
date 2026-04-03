<template>
  <section v-if="projects.length" class="recent-projects-card">
    <div class="section-header">
      <h3 class="section-title">最近卷宗</h3>
      <RouterLink to="/archive-library" class="btn subtle small">查看全部</RouterLink>
    </div>

    <div class="project-strip">
      <article v-for="item in projects" :key="item.project_id" class="project-mini-card workbench-card">
        <div class="project-top">
          <span class="status-tag" :class="statusClass(item.status)">{{ formatProjectStatus(item.status) }}</span>
          <button class="delete-icon" @click.stop="$emit('delete-project', item)">×</button>
        </div>
        <div class="project-info">
          <div class="project-name">{{ item.name }}</div>
          <div class="project-goal">{{ item.analysis_goal || "无明确分析目标" }}</div>
        </div>
        <div class="project-footer">
          <span class="mono">{{ item.project_id.slice(0, 8) }}</span>
          <RouterLink :to="`/archive-library?project_id=${item.project_id}`" class="btn subtle small">详情</RouterLink>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { formatProjectStatus } from "../../utils/chineseDisplay";

defineProps({
  projects: { type: Array, default: () => [] },
});

defineEmits(["delete-project"]);

function statusClass(status) {
  if (status === "failed") {
    return "danger";
  }
  return status && status.includes("completed") ? "ok" : "warn";
}
</script>

<style scoped>
.recent-projects-card {
  width: 100%;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.section-title {
  font-size: 16px;
  font-family: "ZCOOL XiaoWei", serif;
  margin: 0;
}

.project-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.project-mini-card {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(249, 246, 238, 0.96)),
    radial-gradient(circle at 100% 0%, rgba(61, 90, 128, 0.05), transparent 28%);
}

.project-top,
.project-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.project-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.delete-icon {
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 16px;
  padding: 2px;
  line-height: 1;
}

.delete-icon:hover {
  color: var(--accent-seal);
}

.project-name {
  font-weight: 700;
  font-size: 14px;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-goal {
  font-size: 12px;
  color: var(--text-sub);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}

.project-footer {
  margin-top: auto;
  padding-top: 6px;
  border-top: 1px solid var(--line-soft);
  font-size: 11px;
}

@media (max-width: 1100px) {
  .project-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .project-strip {
    grid-template-columns: 1fr;
  }
}
</style>
