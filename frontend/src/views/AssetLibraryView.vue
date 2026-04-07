<template>
  <div class="asset-lib">
    <header class="asset-lib__header">
      <div>
        <h1>资产库</h1>
        <p class="muted">
          统一存放写作风格、世界观、角色原型、提示词模板、稿件块等可被任意 agent 调用的文本资产。
          通过启停开关控制 agent 是否能搜索到。
        </p>
      </div>
      <div class="asset-lib__actions">
        <button class="btn" @click="openCreate()">新建资产</button>
        <button class="btn primary" @click="openExtract()">提取文风…</button>
      </div>
    </header>

    <section class="asset-lib__filters">
      <select v-model="filters.scope" @change="reload()">
        <option value="all">全部范围</option>
        <option value="global">全局</option>
        <option value="project">项目</option>
      </select>
      <input
        v-model="filters.projectId"
        placeholder="project_id（项目层时必填）"
        @change="reload()"
      />
      <select v-model="filters.assetType" @change="reload()">
        <option value="">全部类型</option>
        <option v-for="t in ASSET_TYPES" :key="t" :value="t">{{ t }}</option>
      </select>
      <input v-model="filters.category" placeholder="分类过滤" @change="reload()" />
      <input
        v-model="searchQuery"
        placeholder="关键词搜索（≥3 字符走 FTS）"
        @keyup.enter="runSearch()"
      />
      <button class="btn" @click="runSearch()">搜索</button>
      <label class="check">
        <input type="checkbox" v-model="filters.enabledOnly" @change="reload()" />
        仅已启用
      </label>
    </section>

    <section class="asset-lib__bulk" v-if="selectedIds.length">
      已选 {{ selectedIds.length }} 条
      <button class="btn" @click="bulkToggle(true)">批量启用</button>
      <button class="btn" @click="bulkToggle(false)">批量停用</button>
      <input v-model="bulkCategory" placeholder="批量分类" />
      <button class="btn" @click="bulkCategorize()">应用分类</button>
    </section>

    <section class="asset-lib__list">
      <div v-if="loading" class="muted">加载中…</div>
      <div v-else-if="!rows.length" class="muted">没有匹配的资产</div>
      <table v-else>
        <thead>
          <tr>
            <th><input type="checkbox" @change="toggleAll($event)" /></th>
            <th>标题</th>
            <th>类型</th>
            <th>分类</th>
            <th>scope</th>
            <th>字数</th>
            <th>启用</th>
            <th>更新时间</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.asset_id" :class="{ disabled: !r.enabled }">
            <td>
              <input
                type="checkbox"
                :value="r.asset_id"
                v-model="selectedIds"
              />
            </td>
            <td>
              <a href="#" @click.prevent="openDetail(r)">{{ r.title }}</a>
              <div v-if="r.snippet" class="snippet" v-html="r.snippet" />
              <div v-else-if="r.summary" class="snippet">{{ r.summary }}</div>
            </td>
            <td>{{ r.asset_type }}</td>
            <td>{{ r.category || "—" }}</td>
            <td>{{ r.scope }}</td>
            <td>{{ r.word_count }}</td>
            <td>
              <input
                type="checkbox"
                :checked="r.enabled"
                @change="toggleOne(r, $event.target.checked)"
              />
            </td>
            <td class="muted small">{{ r.updated_at }}</td>
            <td>
              <button class="btn small" @click="removeOne(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Detail / Edit drawer -->
    <div v-if="detail" class="drawer">
      <div class="drawer__header">
        <h2>{{ detail.title }}</h2>
        <button class="btn" @click="detail = null">关闭</button>
      </div>
      <div class="drawer__body">
        <label>标题 <input v-model="detail.title" /></label>
        <label>分类 <input v-model="detail.category" /></label>
        <label>摘要 <textarea v-model="detail.summary" rows="2" /></label>
        <label>正文 <textarea v-model="detail.content" rows="14" /></label>
        <label>
          payload (JSON)
          <textarea v-model="detail.payloadText" rows="6" />
        </label>
        <div class="row">
          <label class="check">
            <input type="checkbox" v-model="detail.enabled" /> 启用
          </label>
          <button class="btn primary" @click="saveDetail()">保存</button>
        </div>
      </div>
    </div>

    <!-- Style extract dialog -->
    <div v-if="extractOpen" class="drawer">
      <div class="drawer__header">
        <h2>提取文风</h2>
        <button class="btn" @click="extractOpen = false">关闭</button>
      </div>
      <div class="drawer__body">
        <label>名称 <input v-model="extractForm.title" placeholder="例如：余华·活着风格" /></label>
        <label>分类 <input v-model="extractForm.category" /></label>
        <label>
          原文（粘贴整本/部分小说，越长越好）
          <textarea v-model="extractForm.text" rows="14" />
        </label>
        <div class="row">
          <span v-if="extractTask" class="muted">
            任务 {{ extractTask.task_id?.slice(0, 8) }} · {{ extractTask.status }} ·
            {{ extractTask.progress || 0 }}% · {{ extractTask.message || "" }}
          </span>
          <button class="btn primary" :disabled="extractRunning" @click="submitExtract()">
            {{ extractRunning ? "进行中…" : "开始提取" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import {
  listAssets,
  searchAssets,
  createAsset,
  updateAsset,
  deleteAsset,
  batchToggleAssets,
  batchCategorizeAssets,
  startStyleExtraction,
  getStyleExtractionStatus,
} from "../api/assets.js";

const ASSET_TYPES = [
  "writing_style",
  "author_style",
  "worldview",
  "character_archetype",
  "prompt_template",
  "manuscript_block",
  "note",
];

const filters = reactive({
  scope: "all",
  projectId: "",
  assetType: "",
  category: "",
  enabledOnly: false,
});
const searchQuery = ref("");
const rows = ref([]);
const loading = ref(false);
const selectedIds = ref([]);
const bulkCategory = ref("");

const detail = ref(null);

const extractOpen = ref(false);
const extractForm = reactive({ title: "", category: "", text: "" });
const extractTask = ref(null);
const extractRunning = ref(false);
let extractTimer = null;

async function reload() {
  loading.value = true;
  selectedIds.value = [];
  try {
    const res = await listAssets({
      scope: filters.scope,
      projectId: filters.projectId,
      assetType: filters.assetType,
      category: filters.category || undefined,
      enabledOnly: filters.enabledOnly,
    });
    rows.value = res.data || [];
  } catch (e) {
    console.error(e);
    alert(`加载失败：${e.message}`);
  } finally {
    loading.value = false;
  }
}

async function runSearch() {
  if (!searchQuery.value.trim()) {
    return reload();
  }
  loading.value = true;
  try {
    const res = await searchAssets({
      query: searchQuery.value,
      scope: filters.scope,
      project_id: filters.projectId || undefined,
      asset_type: filters.assetType || undefined,
      category: filters.category || undefined,
      enabled_only: filters.enabledOnly,
      limit: 50,
    });
    rows.value = res.data || [];
  } catch (e) {
    alert(`搜索失败：${e.message}`);
  } finally {
    loading.value = false;
  }
}

function toggleAll(e) {
  selectedIds.value = e.target.checked ? rows.value.map((r) => r.asset_id) : [];
}

async function toggleOne(row, enabled) {
  await updateAsset(row.asset_id, {
    scope: row.scope,
    project_id: row.project_id,
    enabled,
  });
  row.enabled = enabled;
}

async function removeOne(row) {
  if (!confirm(`删除资产 “${row.title}”？`)) return;
  await deleteAsset(row.asset_id, { scope: row.scope, projectId: row.project_id });
  await reload();
}

async function bulkToggle(enabled) {
  if (!selectedIds.value.length) return;
  // 必须按 scope 分组
  const groups = {};
  for (const id of selectedIds.value) {
    const row = rows.value.find((r) => r.asset_id === id);
    if (!row) continue;
    const key = `${row.scope}|${row.project_id || ""}`;
    if (!groups[key]) groups[key] = { scope: row.scope, project_id: row.project_id, ids: [] };
    groups[key].ids.push(id);
  }
  for (const g of Object.values(groups)) {
    await batchToggleAssets({
      scope: g.scope,
      project_id: g.project_id,
      asset_ids: g.ids,
      enabled,
    });
  }
  await reload();
}

async function bulkCategorize() {
  if (!selectedIds.value.length) return;
  const groups = {};
  for (const id of selectedIds.value) {
    const row = rows.value.find((r) => r.asset_id === id);
    if (!row) continue;
    const key = `${row.scope}|${row.project_id || ""}`;
    if (!groups[key]) groups[key] = { scope: row.scope, project_id: row.project_id, ids: [] };
    groups[key].ids.push(id);
  }
  for (const g of Object.values(groups)) {
    await batchCategorizeAssets({
      scope: g.scope,
      project_id: g.project_id,
      asset_ids: g.ids,
      category: bulkCategory.value,
    });
  }
  await reload();
}

function openDetail(row) {
  detail.value = {
    ...row,
    payloadText: JSON.stringify(row.payload || {}, null, 2),
  };
}

async function saveDetail() {
  let payload;
  try {
    payload = JSON.parse(detail.value.payloadText || "{}");
  } catch (e) {
    return alert("payload 不是合法 JSON");
  }
  await updateAsset(detail.value.asset_id, {
    scope: detail.value.scope,
    project_id: detail.value.project_id,
    title: detail.value.title,
    category: detail.value.category,
    summary: detail.value.summary,
    content: detail.value.content,
    payload,
    enabled: detail.value.enabled,
  });
  detail.value = null;
  await reload();
}

function openCreate() {
  detail.value = {
    asset_id: undefined,
    scope: "global",
    project_id: "",
    title: "新资产",
    asset_type: "writing_style",
    category: "",
    summary: "",
    content: "",
    enabled: true,
    payloadText: "{}",
  };
  // hijack save: creating
  detail.value._isNew = true;
}

async function openExtract() {
  extractOpen.value = true;
}

async function submitExtract() {
  if (!extractForm.title.trim() || !extractForm.text.trim()) {
    return alert("名称和原文必填");
  }
  extractRunning.value = true;
  try {
    const res = await startStyleExtraction({
      title: extractForm.title,
      category: extractForm.category,
      text: extractForm.text,
    });
    extractTask.value = { task_id: res.data.task_id, status: "RUNNING" };
    pollExtractTask(res.data.task_id);
  } catch (e) {
    alert(`提取失败：${e.message}`);
    extractRunning.value = false;
  }
}

function pollExtractTask(taskId) {
  if (extractTimer) clearInterval(extractTimer);
  extractTimer = setInterval(async () => {
    try {
      const res = await getStyleExtractionStatus(taskId);
      extractTask.value = res.data;
      if (["COMPLETED", "FAILED", "completed", "failed"].includes(res.data.status)) {
        clearInterval(extractTimer);
        extractTimer = null;
        extractRunning.value = false;
        if (String(res.data.status).toLowerCase() === "completed") {
          await reload();
          alert(`提取完成：已写入 asset ${res.data.result?.asset_id || ""}`);
          extractOpen.value = false;
        } else {
          alert(`提取失败：${res.data.error || ""}`);
        }
      }
    } catch (e) {
      console.error(e);
    }
  }, 1500);
}

onBeforeUnmount(() => {
  if (extractTimer) clearInterval(extractTimer);
});
onMounted(reload);
</script>

<style scoped>
.asset-lib { padding: 24px; max-width: 1280px; margin: 0 auto; }
.asset-lib__header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.asset-lib__header h1 { margin: 0; font-size: 22px; }
.asset-lib__actions { display: flex; gap: 8px; }
.asset-lib__filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; align-items: center; }
.asset-lib__filters input, .asset-lib__filters select { padding: 6px 10px; }
.asset-lib__bulk { display: flex; gap: 8px; align-items: center; padding: 8px; background: #f4f4f5; border-radius: 6px; margin-bottom: 8px; }
.asset-lib__list table { width: 100%; border-collapse: collapse; }
.asset-lib__list th, .asset-lib__list td { padding: 8px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
.asset-lib__list tr.disabled { opacity: 0.5; }
.snippet { color: #666; font-size: 12px; margin-top: 2px; }
.muted { color: #888; }
.small { font-size: 12px; }
.btn { padding: 6px 12px; border: 1px solid #d4d4d8; background: #fff; border-radius: 4px; cursor: pointer; }
.btn.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.btn.small { padding: 4px 8px; font-size: 12px; }
.check { display: inline-flex; gap: 4px; align-items: center; }
.drawer { position: fixed; top: 0; right: 0; width: 520px; height: 100vh; background: #fff; box-shadow: -2px 0 8px rgba(0,0,0,0.1); display: flex; flex-direction: column; z-index: 1000; }
.drawer__header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid #eee; }
.drawer__body { padding: 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px; }
.drawer__body label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.drawer__body input, .drawer__body textarea { padding: 6px; border: 1px solid #d4d4d8; border-radius: 4px; font-family: inherit; }
.row { display: flex; justify-content: space-between; align-items: center; }
</style>
