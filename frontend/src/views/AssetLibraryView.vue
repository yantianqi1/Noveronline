<template>
  <div class="asset-hub">
    <header class="hub__header">
      <div>
        <h1>资产库</h1>
        <p class="muted">
          统一查看本项目所有数据：种子档案、故事图谱、写作工坊、世界线、独立资产 ——
          一个入口、一个搜索框、一份可视化。
        </p>
      </div>
      <div class="hub__actions">
        <button class="btn" @click="openIngest()">📥 入库新资产</button>
        <button class="btn" @click="reindex()" :disabled="reindexing">
          {{ reindexing ? "重建中…" : "🔄 重建索引" }}
        </button>
      </div>
    </header>

    <div class="hub__searchbar">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="🔎 全局搜索：跨所有数据源（≥2 字符即触发）"
        @input="onSearchInput"
      />
      <span v-if="searchActive" class="search-badge">
        全局搜索 {{ items.length }} 条结果
        <button class="btn small" @click="clearSearch()">清除</button>
      </span>
    </div>

    <div class="hub__layout">
      <!-- ============ Left facets ============ -->
      <aside class="facets">
        <section>
          <h3>项目范围</h3>
          <select v-model="projectId" @change="reload()">
            <option value="">（全局范围 / 不选项目）</option>
            <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
              {{ p.name || p.project_id }}
            </option>
          </select>
        </section>

        <section>
          <h3>数据源</h3>
          <label v-for="s in SOURCES" :key="s.key" class="check">
            <input
              type="checkbox"
              :value="s.key"
              v-model="selectedSources"
              @change="reload()"
            />
            <span class="badge" :style="{ background: s.color }">{{ s.icon }}</span>
            {{ s.label }}
            <span v-if="facetSources[s.key]" class="count">{{ facetSources[s.key] }}</span>
          </label>
        </section>

        <section v-if="facetTypes.length">
          <h3>实体类型</h3>
          <label v-for="t in facetTypes" :key="t.key" class="check">
            <input
              type="checkbox"
              :value="t.key"
              v-model="selectedTypes"
              @change="reload()"
            />
            {{ ENTITY_TYPE_LABELS[t.key] || t.key }}
            <span class="count">{{ t.count }}</span>
          </label>
        </section>
      </aside>

      <!-- ============ Right list ============ -->
      <main class="hub__main">
        <div v-if="loading" class="muted center">加载中…</div>
        <div v-else-if="errors.length" class="errbox">
          <strong>部分数据源加载失败：</strong>
          <ul>
            <li v-for="e in errors" :key="e.source">{{ e.source }}: {{ e.error }}</li>
          </ul>
        </div>
        <div v-if="!loading && !items.length" class="muted center">没有匹配的资产</div>
        <div v-else class="cards">
          <article
            v-for="it in items"
            :key="`${it.source}:${it.source_ref}`"
            class="card"
            @click="openDetail(it)"
          >
            <header class="card__head">
              <span
                class="badge"
                :style="{ background: sourceMeta(it.source).color }"
                :title="sourceMeta(it.source).label"
              >
                {{ sourceMeta(it.source).icon }}
              </span>
              <span class="card__type">{{ ENTITY_TYPE_LABELS[it.entity_type] || it.entity_type || "—" }}</span>
              <span v-if="it.importance" class="tier">{{ IMPORTANCE_LABELS[it.importance] || it.importance }}</span>
            </header>
            <h4 class="card__title">{{ it.title || "(无标题)" }}</h4>
            <p class="card__summary" v-html="it.snippet || it.summary || ''"></p>
            <footer class="card__foot muted small">
              <span>{{ it.updated_at || "" }}</span>
              <span v-if="it.scope === 'global'">· 全局</span>
            </footer>
          </article>
        </div>
      </main>
    </div>

    <!-- ============ Detail drawer ============ -->
    <div v-if="detail" class="drawer" @click.self="detail = null">
      <div class="drawer__panel">
        <header>
          <h2>{{ detail.title }}</h2>
          <button class="btn" @click="detail = null">关闭</button>
        </header>
        <div class="drawer__body">
          <div class="kv">
            <strong>来源：</strong>{{ sourceMeta(detail.source).label }} ({{ detail.source }})
          </div>
          <div class="kv"><strong>实体类型：</strong>{{ ENTITY_TYPE_LABELS[detail.entity_type] || detail.entity_type }}</div>
          <div class="kv" v-if="detail.project_id"><strong>项目：</strong>{{ detail.project_id }}</div>
          <div class="kv" v-if="detail.summary"><strong>摘要：</strong>{{ detail.summary }}</div>
          <div class="kv"><strong>更新时间：</strong>{{ detail.updated_at || "—" }}</div>
          <div class="kv" v-if="detail.origin_link">
            <strong>跳转：</strong><a :href="`#${detail.origin_link}`">{{ detail.origin_link }}</a>
          </div>
          <h4>完整数据 (payload)</h4>
          <pre>{{ JSON.stringify(detail.payload || {}, null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- ============ Ingestion drawer ============ -->
    <div v-if="ingestOpen" class="drawer" @click.self="ingestOpen = false">
      <div class="drawer__panel">
        <header>
          <h2>📥 入库新资产</h2>
          <button class="btn" @click="ingestOpen = false">关闭</button>
        </header>
        <div class="drawer__body">
          <p class="muted small">
            把原始素材粘贴进来，「入库 Agent」会自动识别类型、抽取结构化字段、生成摘要与标签后写入资产库。
          </p>
          <label>
            范围
            <select v-model="ingestForm.scope">
              <option value="global">全局</option>
              <option value="project">当前项目</option>
            </select>
          </label>
          <label>
            类型提示（可选，留空让 Agent 自动判定）
            <select v-model="ingestForm.hint_type">
              <option value="">自动判定</option>
              <option value="writing_style">文风</option>
              <option value="worldview">世界观</option>
              <option value="character_archetype">角色原型</option>
              <option value="world_rule">创作规则 / 世界规则</option>
              <option value="plot_template">桥段 / 情节模板</option>
              <option value="prompt_template">提示词模板</option>
              <option value="note">普通笔记</option>
            </select>
          </label>
          <label>
            原始素材
            <textarea
              v-model="ingestForm.raw_text"
              rows="14"
              placeholder="贴入角色设定 / 世界观片段 / 文风范文 / 创作守则…"
            />
          </label>
          <div class="row">
            <span v-if="ingestTask" class="muted small">
              任务 {{ (ingestTask.task_id || "").slice(0, 8) }} ·
              {{ ingestTask.status }} · {{ ingestTask.progress || 0 }}% ·
              {{ ingestTask.message || "" }}
              <span v-if="ingestTask.error" class="err">— {{ ingestTask.error }}</span>
            </span>
            <button class="btn primary" :disabled="ingestRunning" @click="submitIngest()">
              {{ ingestRunning ? "Agent 工作中…" : "开始入库" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import {
  listUnifiedAssets,
  getUnifiedFacets,
  searchGlobalAssets,
  reindexUnifiedAssets,
  startAssetIngestion,
  getAssetIngestionStatus,
} from "../api/assets.js";
import { listProjects } from "../api/project.js";

const SOURCES = [
  { key: "assets", label: "资产库", icon: "📦", color: "#6366f1" },
  { key: "archive", label: "档案库", icon: "📚", color: "#10b981" },
  { key: "story_graph", label: "故事图谱", icon: "🕸️", color: "#f59e0b" },
  { key: "novel_db", label: "写作工坊", icon: "✍️", color: "#ec4899" },
  { key: "worldline", label: "世界线", icon: "🌐", color: "#3b82f6" },
  { key: "seed", label: "总览种子", icon: "🌱", color: "#84cc16" },
];

const ENTITY_TYPE_LABELS = {
  // assets
  writing_style: "文风",
  author_style: "作家风格",
  worldview: "世界观",
  character_archetype: "角色原型",
  prompt_template: "提示词模板",
  manuscript_block: "稿件块",
  note: "笔记",
  world_rule: "世界规则",
  plot_template: "情节模板",
  // archive / novel_db / seed
  character: "角色",
  organization: "组织",
  faction: "势力",
  relationship: "关系",
  entity: "实体",
  plot_thread: "情节线索",
  scene: "场景",
  seed_character: "种子角色",
  seed_world_rule: "种子世界规则",
  seed_plot_thread: "种子线索",
  seed_agent_profile: "Agent 档案",
  // worldline
  worldline_session: "世界线会话",
};

const IMPORTANCE_LABELS = {
  protagonist: "主角",
  major: "重要",
  supporting: "次要",
  minor: "群像",
};

function sourceMeta(key) {
  return SOURCES.find((s) => s.key === key) || { label: key, icon: "·", color: "#999" };
}

const projects = ref([]);
const projectId = ref("");
const selectedSources = ref(SOURCES.map((s) => s.key));
const selectedTypes = ref([]);
const facetSources = ref({});
const facetTypes = ref([]);

const items = ref([]);
const errors = ref([]);
const loading = ref(false);

const detail = ref(null);

const searchQuery = ref("");
const searchActive = ref(false);
let searchTimer = null;

const ingestOpen = ref(false);
const ingestForm = reactive({ scope: "global", hint_type: "", raw_text: "" });
const ingestRunning = ref(false);
const ingestTask = ref(null);
let ingestTimer = null;

const reindexing = ref(false);

async function loadProjects() {
  try {
    const res = await listProjects(50);
    projects.value = res.data || [];
  } catch (e) {
    console.error(e);
  }
}

async function loadFacets() {
  try {
    const res = await getUnifiedFacets(projectId.value);
    const data = res.data || {};
    facetSources.value = Object.fromEntries(
      (data.sources || []).map((s) => [s.key, s.count])
    );
    facetTypes.value = data.entity_types || [];
  } catch (e) {
    console.error(e);
  }
}

async function reload() {
  if (searchActive.value) return; // search mode owns the list
  loading.value = true;
  errors.value = [];
  try {
    const res = await listUnifiedAssets({
      projectId: projectId.value,
      sources: selectedSources.value,
      entityTypes: selectedTypes.value,
      pageSize: 200,
    });
    const data = res.data || {};
    items.value = data.items || [];
    errors.value = data.errors || [];
    await loadFacets();
  } catch (e) {
    alert(`加载失败：${e.message}`);
  } finally {
    loading.value = false;
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  const q = searchQuery.value.trim();
  if (q.length < 2) {
    if (searchActive.value) clearSearch();
    return;
  }
  searchTimer = setTimeout(() => runSearch(q), 250);
}

async function runSearch(q) {
  loading.value = true;
  searchActive.value = true;
  errors.value = [];
  try {
    const res = await searchGlobalAssets({
      q,
      projectId: projectId.value,
      sources: selectedSources.value,
      entityTypes: selectedTypes.value,
      limit: 100,
    });
    items.value = res.data || [];
  } catch (e) {
    alert(`搜索失败：${e.message}`);
  } finally {
    loading.value = false;
  }
}

function clearSearch() {
  searchQuery.value = "";
  searchActive.value = false;
  reload();
}

function openDetail(it) {
  detail.value = it;
}

function openIngest() {
  ingestOpen.value = true;
  ingestForm.raw_text = "";
  ingestForm.hint_type = "";
  ingestForm.scope = projectId.value ? "project" : "global";
  ingestTask.value = null;
}

async function submitIngest() {
  if (!ingestForm.raw_text.trim()) return alert("请粘贴原始素材");
  if (ingestForm.scope === "project" && !projectId.value)
    return alert("项目范围必须先选择项目");
  ingestRunning.value = true;
  try {
    const res = await startAssetIngestion({
      raw_text: ingestForm.raw_text,
      hint_type: ingestForm.hint_type || undefined,
      scope: ingestForm.scope,
      project_id: ingestForm.scope === "project" ? projectId.value : undefined,
    });
    const taskId = res.data.task_id;
    ingestTask.value = { task_id: taskId, status: "RUNNING", progress: 0 };
    pollIngest(taskId);
  } catch (e) {
    alert(`入库失败：${e.message}`);
    ingestRunning.value = false;
  }
}

function pollIngest(taskId) {
  if (ingestTimer) clearInterval(ingestTimer);
  ingestTimer = setInterval(async () => {
    try {
      const res = await getAssetIngestionStatus(taskId);
      ingestTask.value = res.data;
      const status = String(res.data.status || "").toLowerCase();
      if (["completed", "failed"].includes(status)) {
        clearInterval(ingestTimer);
        ingestTimer = null;
        ingestRunning.value = false;
        if (status === "completed") {
          await reload();
          alert(`入库完成：${res.data.result?.title || ""}`);
          ingestOpen.value = false;
        } else {
          alert(`入库失败：${res.data.error || "(未知错误)"}`);
        }
      }
    } catch (e) {
      console.error(e);
    }
  }, 1500);
}

async function reindex() {
  if (!projectId.value) return alert("请先选择项目");
  reindexing.value = true;
  try {
    const res = await reindexUnifiedAssets(projectId.value);
    alert(`已索引 ${res.data.indexed} 条记录`);
  } catch (e) {
    alert(`重建失败：${e.message}`);
  } finally {
    reindexing.value = false;
  }
}

onBeforeUnmount(() => {
  if (ingestTimer) clearInterval(ingestTimer);
  if (searchTimer) clearTimeout(searchTimer);
});

onMounted(async () => {
  await loadProjects();
  await reload();
});
</script>

<style scoped>
.asset-hub { padding: 20px 28px; max-width: 1480px; margin: 0 auto; }
.hub__header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.hub__header h1 { margin: 0 0 4px; font-size: 22px; }
.hub__actions { display: flex; gap: 8px; }
.muted { color: #888; }
.small { font-size: 12px; }
.center { text-align: center; padding: 32px; }
.btn { padding: 6px 12px; border: 1px solid #d4d4d8; background: #fff; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.btn.small { padding: 2px 8px; font-size: 11px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.hub__searchbar { margin: 16px 0 12px; display: flex; gap: 12px; align-items: center; }
.search-input { flex: 1; padding: 10px 14px; font-size: 14px; border: 1px solid #d4d4d8; border-radius: 6px; }
.search-badge { background: #fef3c7; padding: 4px 10px; border-radius: 4px; font-size: 12px; display: flex; gap: 8px; align-items: center; }

.hub__layout { display: grid; grid-template-columns: 240px 1fr; gap: 20px; }

.facets { background: #fafafa; padding: 16px; border-radius: 8px; max-height: calc(100vh - 200px); overflow-y: auto; }
.facets h3 { font-size: 12px; text-transform: uppercase; color: #666; margin: 12px 0 8px; }
.facets section:first-child h3 { margin-top: 0; }
.facets select { width: 100%; padding: 6px; }
.facets .check { display: flex; align-items: center; gap: 6px; padding: 4px 0; font-size: 13px; cursor: pointer; }
.facets .count { margin-left: auto; color: #999; font-size: 11px; }

.badge { display: inline-block; width: 22px; height: 22px; line-height: 22px; text-align: center; border-radius: 4px; color: #fff; font-size: 12px; }

.errbox { background: #fee; border: 1px solid #fcc; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 12px; }
.errbox ul { margin: 6px 0 0 16px; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; cursor: pointer; transition: box-shadow 0.15s; }
.card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-color: #c7d2fe; }
.card__head { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.card__type { color: #666; }
.tier { margin-left: auto; background: #ede9fe; color: #6d28d9; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
.card__title { font-size: 14px; margin: 8px 0 4px; }
.card__summary { font-size: 12px; color: #555; line-height: 1.5; margin: 4px 0; max-height: 4.5em; overflow: hidden; }
.card__foot { display: flex; gap: 6px; margin-top: 6px; }

.drawer { position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 1000; display: flex; justify-content: flex-end; }
.drawer__panel { width: 560px; max-width: 90vw; background: #fff; height: 100vh; display: flex; flex-direction: column; }
.drawer__panel header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid #eee; }
.drawer__panel header h2 { margin: 0; font-size: 16px; }
.drawer__body { padding: 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px; }
.drawer__body label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #555; }
.drawer__body input, .drawer__body select, .drawer__body textarea {
  padding: 6px 8px; border: 1px solid #d4d4d8; border-radius: 4px; font-family: inherit; font-size: 13px;
}
.drawer__body pre { background: #f4f4f5; padding: 10px; border-radius: 4px; font-size: 11px; max-height: 320px; overflow: auto; white-space: pre-wrap; }
.kv { font-size: 13px; }
.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.err { color: #dc2626; }
</style>
