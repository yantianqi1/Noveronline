<template>
  <div class="overview-dashboard">
    <!-- 卡片 1: Hero -->
    <section class="hero-card workbench-card">
      <div class="hero-main">
        <div class="hero-title-row">
          <h2 class="hero-title">{{ overview.hero.projectName }}</h2>
          <span class="hero-badge">世界速览</span>
        </div>
        <div class="hero-stats">
          <div class="stat"><span class="num">{{ overview.hero.totalNodes }}</span><span class="lbl">实体</span></div>
          <div class="stat"><span class="num">{{ overview.hero.totalEdges }}</span><span class="lbl">关联</span></div>
          <div class="stat"><span class="num">{{ overview.hero.typeCount }}</span><span class="lbl">设定类</span></div>
          <div class="stat"><span class="num">{{ overview.hero.eventCount }}</span><span class="lbl">事件</span></div>
        </div>
        <p class="hero-headline">{{ overview.hero.headline }}</p>
        <div v-if="overview.hero.protagonistNames.length || overview.hero.majorOrgNames.length" class="hero-tags">
          <span v-for="n in overview.hero.protagonistNames" :key="'p' + n" class="tag protagonist">⭐ {{ n }}</span>
          <span v-for="n in overview.hero.majorOrgNames" :key="'o' + n" class="tag org">⚑ {{ n }}</span>
        </div>
      </div>
    </section>

    <!-- 卡片 6: Story Hooks（最高价值，前置）-->
    <section v-if="overview.hooks.length" class="hooks-card workbench-card">
      <header class="card-header">
        <h3>💡 创作锚点</h3>
        <span class="muted">基于图谱派生的可写场景种子 · 共 {{ overview.hooks.length }} 个</span>
      </header>
      <div class="hooks-grid">
        <article v-for="(hook, idx) in overview.hooks" :key="idx" class="hook-item">
          <div class="hook-title">{{ hook.title }}</div>
          <p class="hook-body">{{ hook.body }}</p>
          <div class="hook-meta">
            <span class="involved">涉及：{{ hook.involvedNames.join(" · ") }}</span>
          </div>
          <div class="hook-actions">
            <n-button size="tiny" quaternary @click="focusFirst(hook.involvedIds)">在图谱中查看</n-button>
            <n-button size="tiny" quaternary @click="copyHook(hook)">复制锚点</n-button>
          </div>
        </article>
      </div>
    </section>

    <!-- 卡片 2: Cast Radar -->
    <section class="cast-card workbench-card">
      <header class="card-header">
        <h3>🎭 阵容雷达</h3>
        <span class="muted">共 {{ overview.cast.totalCharacters }} 个角色</span>
      </header>

      <div v-if="overview.cast.protagonist.length" class="cast-row">
        <div class="row-title">主角</div>
        <div class="cast-grid protagonist">
          <article v-for="c in overview.cast.protagonist" :key="c.id" class="cast-card-item major" @click="focusNode(c.id)">
            <div class="name">⭐ {{ c.name }}</div>
            <p v-if="c.summary" class="summary">{{ c.summary }}</p>
            <div class="meta mono">关联 {{ c.degree }}</div>
          </article>
        </div>
      </div>

      <div v-if="overview.cast.major.length" class="cast-row">
        <div class="row-title">主要角色</div>
        <div class="cast-grid">
          <article v-for="c in overview.cast.major" :key="c.id" class="cast-card-item" @click="focusNode(c.id)">
            <div class="name">{{ c.name }}</div>
            <p v-if="c.summary" class="summary">{{ c.summary }}</p>
            <div class="meta mono">关联 {{ c.degree }}</div>
          </article>
        </div>
      </div>

      <details v-if="overview.cast.supporting.length || overview.cast.minor.length" class="cast-row">
        <summary class="row-title">辅助 / 次要角色（{{ overview.cast.supporting.length + overview.cast.minor.length }}）</summary>
        <div class="cast-grid mini">
          <span v-for="c in [...overview.cast.supporting, ...overview.cast.minor]" :key="c.id" class="mini-chip" @click="focusNode(c.id)">
            {{ c.name }}<small> · {{ c.degree }}</small>
          </span>
        </div>
      </details>

      <div v-if="overview.cast.organizations.length" class="cast-row">
        <div class="row-title">组织 / 势力</div>
        <div class="cast-grid">
          <article v-for="o in overview.cast.organizations" :key="o.id" class="cast-card-item org" @click="focusNode(o.id)">
            <div class="name">⚑ {{ o.name }}</div>
            <p v-if="o.summary" class="summary">{{ o.summary }}</p>
            <div class="meta mono">关联 {{ o.degree }}</div>
          </article>
        </div>
      </div>
    </section>

    <!-- 卡片 3: Relationship Highlights -->
    <section class="rel-card workbench-card">
      <header class="card-header">
        <h3>💞 关系亮点</h3>
      </header>
      <div class="rel-grid">
        <div class="rel-col">
          <div class="col-title">核心羁绊 Top 5</div>
          <ol class="rel-list">
            <li v-for="r in overview.highlights.topBonds" :key="r.id" @click="focusEdge(r)">
              <span class="from">{{ r.sourceName }}</span>
              <span class="rel">— {{ r.label }} →</span>
              <span class="to">{{ r.targetName }}</span>
              <span class="weight mono">×{{ r.weight }}</span>
            </li>
            <li v-if="!overview.highlights.topBonds.length" class="empty">暂无</li>
          </ol>
        </div>
        <div class="rel-col">
          <div class="col-title">冲突线</div>
          <ol class="rel-list">
            <li v-for="r in overview.highlights.conflicts" :key="r.id" class="conflict" @click="focusEdge(r)">
              <span class="from">{{ r.sourceName }}</span>
              <span class="rel">⚔</span>
              <span class="to">{{ r.targetName }}</span>
              <span class="weight mono">×{{ r.weight }}</span>
            </li>
            <li v-if="!overview.highlights.conflicts.length" class="empty">暂未发现明显冲突</li>
          </ol>
        </div>
        <div class="rel-col">
          <div class="col-title">三角关系</div>
          <ul class="rel-list">
            <li v-for="(t, idx) in overview.highlights.triangles" :key="idx">
              {{ t.members.map(m => m.name).join(" — ") }}
            </li>
            <li v-if="!overview.highlights.triangles.length" class="empty">暂未发现</li>
          </ul>
        </div>
        <div class="rel-col">
          <div class="col-title">孤儿警示</div>
          <ul class="rel-list">
            <li v-for="o in overview.highlights.orphans" :key="o.id" class="orphan" @click="focusNode(o.id)">
              {{ o.name }}<small> · 关联 {{ o.degree }}</small>
            </li>
            <li v-if="!overview.highlights.orphans.length" class="empty">所有角色都有戏份</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- 卡片 4: Event Timeline -->
    <section v-if="overview.timeline.length" class="timeline-card workbench-card">
      <header class="card-header">
        <h3>⚡ 事件时间线</h3>
        <span class="muted">{{ overview.timeline.length }} 个事件</span>
      </header>
      <div class="timeline-rail">
        <div v-for="ev in overview.timeline" :key="ev.id" class="timeline-node" @click="focusNode(ev.id)">
          <div class="chapter mono">{{ ev.chapterId || "?" }}</div>
          <div class="dot"></div>
          <div class="ev-name">{{ ev.name }}</div>
          <div v-if="ev.participants.length" class="ev-people">{{ ev.participants.slice(0,3).map(p => p.name).join("、") }}</div>
        </div>
      </div>
    </section>

    <!-- 卡片 5: World Rules -->
    <section v-if="overview.rules.length" class="rules-card workbench-card">
      <header class="card-header">
        <h3>📜 世界规则</h3>
      </header>
      <div class="rules-grid">
        <article v-for="r in overview.rules" :key="r.id" class="rule-item" @click="focusNode(r.id)">
          <div class="rule-name">{{ r.name }}</div>
          <p v-if="r.summary" class="rule-desc">{{ r.summary }}</p>
          <div v-if="r.linked.length" class="rule-linked">
            关联：<span v-for="l in r.linked" :key="l.id" class="linked-chip">{{ l.name }}</span>
          </div>
          <div v-else class="rule-linked muted">尚未触发</div>
        </article>
      </div>
    </section>

    <!-- 卡片 7: Health Check -->
    <section v-if="overview.health.length" class="health-card workbench-card">
      <header class="card-header">
        <h3>🩺 异常与缺口</h3>
      </header>
      <div v-for="issue in overview.health" :key="issue.kind" class="health-row" :class="issue.severity">
        <div class="health-label">{{ issue.label }} · {{ issue.total }}</div>
        <div class="health-items">
          <span v-for="it in issue.items" :key="it.id" class="health-chip" @click="focusNode(it.id)">{{ it.name }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { NButton } from "naive-ui";
import { buildWorldOverview } from "./worldOverviewModel.js";

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  projectName: { type: String, default: "" },
});

const emit = defineEmits(["focus-node", "focus-edge"]);

const overview = computed(() =>
  buildWorldOverview({
    nodes: props.nodes,
    edges: props.edges,
    projectName: props.projectName,
  })
);

function focusNode(nodeId) {
  if (nodeId) emit("focus-node", nodeId);
}

function focusEdge(edge) {
  if (edge?.id) emit("focus-edge", edge);
}

function focusFirst(ids = []) {
  if (ids.length) focusNode(ids[0]);
}

function copyHook(hook) {
  const text = `${hook.title}\n\n${hook.body}\n\n涉及：${hook.involvedNames.join(" · ")}`;
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {});
  }
}
</script>

<style scoped>
.overview-dashboard {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 2px 24px;
  overflow-y: auto;
}

.workbench-card {
  padding: 14px 18px;
  border: 1px solid var(--line-soft, #e6dcc4);
  border-radius: 10px;
  background: #fffdf7;
}

.card-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}

.card-header h3 {
  margin: 0;
  font-size: 15px;
  color: #4a3a22;
  font-family: "ZCOOL XiaoWei", serif;
}

.muted {
  font-size: 12px;
  color: #9a8b6f;
}

.mono {
  font-family: "Courier New", monospace;
  font-size: 11px;
}

/* Hero */
.hero-card {
  background: linear-gradient(180deg, #fffaf0 0%, #fdf3df 100%);
}
.hero-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hero-title {
  margin: 0;
  font-size: 22px;
  font-family: "ZCOOL XiaoWei", serif;
  color: #4a3a22;
}
.hero-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(201, 138, 59, 0.18);
  color: #8a5a1e;
  border-radius: 10px;
}
.hero-stats {
  display: flex;
  gap: 22px;
  margin: 12px 0 8px;
}
.stat {
  display: flex;
  flex-direction: column;
}
.stat .num {
  font-size: 24px;
  font-weight: 600;
  color: #c98a3b;
  font-family: "Courier New", monospace;
}
.stat .lbl {
  font-size: 11px;
  color: #8a785a;
}
.hero-headline {
  margin: 6px 0;
  color: #5a4a30;
  font-size: 14px;
}
.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.tag {
  font-size: 12px;
  padding: 2px 9px;
  border-radius: 12px;
  background: #f5ead0;
  color: #6b5a3c;
}
.tag.protagonist {
  background: rgba(201, 138, 59, 0.2);
  color: #8a5a1e;
}
.tag.org {
  background: rgba(74, 107, 58, 0.15);
  color: #4a6b3a;
}

/* Hooks */
.hooks-card {
  background: linear-gradient(180deg, #fffceb 0%, #fff8d8 100%);
}
.hooks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}
.hook-item {
  padding: 10px 12px;
  background: #fffefa;
  border: 1px solid rgba(201, 138, 59, 0.25);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hook-title {
  font-weight: 600;
  font-size: 13.5px;
  color: #4a3a22;
}
.hook-body {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: #5a4a30;
}
.hook-meta .involved {
  font-size: 11px;
  color: #8a785a;
}
.hook-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

/* Cast */
.cast-row {
  margin-bottom: 12px;
}
.row-title {
  font-size: 12px;
  color: #8a785a;
  margin-bottom: 6px;
  font-weight: 600;
}
summary.row-title {
  cursor: pointer;
}
.cast-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px;
}
.cast-grid.protagonist {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}
.cast-grid.mini {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cast-card-item {
  padding: 8px 10px;
  background: #fffaf0;
  border: 1px solid var(--line-soft, #e6dcc4);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.cast-card-item:hover {
  border-color: #c98a3b;
}
.cast-card-item.major {
  background: linear-gradient(180deg, #fff8e6 0%, #fff2c8 100%);
}
.cast-card-item.org {
  background: #f5f8ee;
}
.cast-card-item .name {
  font-weight: 600;
  font-size: 13px;
  color: #4a3a22;
}
.cast-card-item .summary {
  margin: 3px 0;
  font-size: 11.5px;
  color: #6b5a3c;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.cast-card-item .meta {
  font-size: 10.5px;
  color: #9a8b6f;
}
.mini-chip {
  font-size: 11.5px;
  padding: 3px 8px;
  background: #f5ead0;
  border-radius: 10px;
  color: #5a4a30;
  cursor: pointer;
}
.mini-chip small {
  color: #9a8b6f;
}

/* Rel */
.rel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.col-title {
  font-size: 12px;
  font-weight: 600;
  color: #8a785a;
  margin-bottom: 4px;
}
.rel-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rel-list li {
  font-size: 12px;
  color: #5a4a30;
  cursor: pointer;
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 2px 4px;
  border-radius: 4px;
}
.rel-list li:hover {
  background: rgba(201, 138, 59, 0.08);
}
.rel-list li.empty {
  color: #b3a68e;
  font-style: italic;
  cursor: default;
}
.rel-list li.empty:hover {
  background: transparent;
}
.rel-list li.conflict .rel {
  color: var(--accent-seal, #9b4326);
}
.rel-list li.orphan {
  color: #9a6b3a;
}
.rel-list .weight {
  margin-left: auto;
  color: #9a8b6f;
}
.rel-list .from,
.rel-list .to {
  font-weight: 500;
}

/* Timeline */
.timeline-rail {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 8px;
}
.timeline-node {
  flex: 0 0 auto;
  min-width: 130px;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
}
.timeline-node:hover {
  background: rgba(201, 138, 59, 0.08);
}
.timeline-node .chapter {
  color: #9a8b6f;
}
.timeline-node .dot {
  width: 10px;
  height: 10px;
  background: #c98a3b;
  border-radius: 50%;
  margin: 4px 0;
}
.timeline-node .ev-name {
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  color: #4a3a22;
}
.timeline-node .ev-people {
  font-size: 11px;
  color: #8a785a;
  text-align: center;
}

/* Rules */
.rules-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
}
.rule-item {
  padding: 8px 10px;
  background: #fffaf0;
  border: 1px solid var(--line-soft, #e6dcc4);
  border-radius: 6px;
  cursor: pointer;
}
.rule-name {
  font-weight: 600;
  font-size: 12.5px;
  color: #4a3a22;
}
.rule-desc {
  margin: 3px 0;
  font-size: 11.5px;
  color: #6b5a3c;
}
.rule-linked {
  font-size: 11px;
  color: #8a785a;
}
.linked-chip {
  display: inline-block;
  margin: 0 4px 2px 0;
  padding: 1px 6px;
  background: rgba(74, 107, 58, 0.12);
  border-radius: 8px;
  color: #4a6b3a;
}

/* Health */
.health-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 0;
  border-top: 1px dashed var(--line-soft, #e6dcc4);
}
.health-row:first-of-type {
  border-top: none;
}
.health-label {
  font-size: 12px;
  font-weight: 600;
  min-width: 110px;
  color: #5a4a30;
}
.health-row.warn .health-label {
  color: var(--accent-seal, #9b4326);
}
.health-items {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.health-chip {
  font-size: 11px;
  padding: 1px 7px;
  background: #f5ead0;
  border-radius: 8px;
  cursor: pointer;
  color: #5a4a30;
}
.health-chip:hover {
  background: #f0dca8;
}
</style>
