<template>
  <aside class="detail">
    <template v-if="selectedNode">
      <div class="inspector-header">
        <h3>{{ selectedNode.name }}</h3>
        <div class="badge-row">
          <n-tag size="small" :bordered="false" type="info">{{ typeLabel }}</n-tag>
          <n-tag v-if="tierLabel" size="small" :bordered="false" type="warning">{{ tierLabel }}</n-tag>
        </div>
      </div>

      <div v-if="archiveLoading" class="archive-loading">
        <n-spin size="small" />
        <span>档案加载中...</span>
      </div>

      <template v-if="archiveData">
        <InspectorSection v-if="identityItems.length" title="身份特征" :items="identityItems" />
        <InspectorSection v-if="motivationItems.length" title="动机驱力" :items="motivationItems" />
        <InspectorSection v-if="tensionItems.length" title="内在张力" :items="tensionItems" />
        <InspectorSection v-if="relationshipItems.length" title="关系网络" :items="relationshipItems" />
        <InspectorSection v-if="behaviorItems.length" title="行为模式" :items="behaviorItems" />
        <InspectorSection v-if="stateItems.length" title="当前状态" :items="stateItems" />
        <InspectorSection v-if="riskItems.length" title="风险标记" :items="riskItems" />
        <InspectorSection v-if="privateItems.length" title="隐秘档案" :items="privateItems" />
      </template>

      <div v-else-if="!archiveLoading" class="fallback-summary">
        <p v-if="selectedNode.summary">{{ selectedNode.summary }}</p>
        <p v-if="aliasesList.length" class="aliases">别名: {{ aliasesList.join("、") }}</p>
        <p v-if="!selectedNode.summary" class="no-data">暂无档案数据，可先生成角色档案。</p>
      </div>
    </template>

    <template v-else-if="selectedEdge">
      <h3>关系档案</h3>
      <p><strong>关系:</strong> {{ selectedEdge.name || "关系" }}</p>
      <p><strong>来源:</strong> {{ selectedEdge.source_name || selectedEdge.source_id }}</p>
      <p><strong>目标:</strong> {{ selectedEdge.target_name || selectedEdge.target_id }}</p>
      <p v-if="selectedEdge.fact"><strong>说明:</strong> {{ selectedEdge.fact }}</p>
      <p v-if="selectedEdge.weight > 1"><strong>关联强度:</strong> {{ selectedEdge.weight }} 次</p>
    </template>

    <template v-else>
      <n-empty description="点击图中的节点或关系线，查看详细信息。" />
    </template>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { NTag, NSpin, NEmpty } from "naive-ui";
import InspectorSection from "./InspectorSection.vue";
import { listArchiveLibrary, getArchiveLibraryDetail } from "../api/archive.js";

const TYPE_LABELS = {
  character: "角色",
  organization: "组织",
  faction: "势力",
  group: "群体",
  artifact: "物件",
  knowledgeitem: "知识",
  plotevent: "事件",
  location: "地点",
  rulesystem: "规则",
};

const TIER_LABELS = {
  protagonist: "主角",
  major: "主要",
  supporting: "辅助",
  minor: "次要",
};

const props = defineProps({
  selectedNode: { type: Object, default: null },
  selectedEdge: { type: Object, default: null },
  projectId: { type: String, default: "" },
});

const archiveData = ref(null);
const archiveLoading = ref(false);
let loadGeneration = 0;

const typeLabel = computed(() => {
  const t = (props.selectedNode?.entity_type || "").toLowerCase();
  return TYPE_LABELS[t] || props.selectedNode?.entity_type || "未分类";
});

const tierLabel = computed(() => {
  const tier = archiveData.value?.importance_tier
    || archiveData.value?.selected_importance_tier
    || props.selectedNode?.attributes?.importance_tier;
  return TIER_LABELS[tier] || "";
});

const aliasesList = computed(() => {
  return props.selectedNode?.attributes?.aliases || [];
});

const payload = computed(() => archiveData.value?.template_payload || {});

function toItems(obj, fieldMap) {
  if (!obj) return [];
  const items = [];
  for (const [key, label] of Object.entries(fieldMap)) {
    const val = obj[key];
    if (val === undefined || val === null || val === "") continue;
    if (Array.isArray(val) && val.length === 0) continue;
    items.push({ label, value: val });
  }
  return items;
}

const identityItems = computed(() => toItems(payload.value.identity, {
  role: "叙事定位",
  identity_hint: "身份线索",
  entity_name: "名称",
}));

const motivationItems = computed(() => toItems(payload.value.motivation, {
  core_drive: "核心驱力",
}));

const tensionItems = computed(() => toItems(payload.value.tension, {
  hidden_tension: "隐藏张力",
}));

const relationshipItems = computed(() => {
  const rel = payload.value.relationship;
  if (!rel) return [];
  const entityType = (props.selectedNode?.entity_type || "").toLowerCase();
  if (entityType === "relationship") {
    return toItems(rel, {
      source: "来源",
      target: "目标",
      change: "关系变化",
      history: "关系史",
      power_dynamic: "权力关系",
      trust_level: "信任度",
      conflict_trigger: "冲突触发",
      stability_forecast: "稳定性",
      last_action: "最近行为",
    });
  }
  return toItems(rel, {
    summary: "关系概览",
  });
});

const behaviorItems = computed(() => {
  const b = payload.value.behavior;
  if (!b) return [];
  const entityType = (props.selectedNode?.entity_type || "").toLowerCase();
  if (entityType === "organization") {
    return toItems(b, {
      resources: "资源",
      internal_factions: "内部派系",
      territorial_control: "控制范围",
      public_stance: "公开立场",
      strategic_goal: "战略目标",
      conflict_targets: "冲突对象",
    });
  }
  return toItems(b, {
    agent_behavior_hint: "行为倾向",
    personality: "性格特征",
    skills: "技能",
    loyalty: "忠诚",
    long_term_goal: "长期目标",
    short_term_goal: "短期目标",
  });
});

const stateItems = computed(() => toItems(payload.value.state, {
  status: "状态",
  surface_mask: "表面形象",
  can_act_as_agent: "可作为Agent",
}));

const riskItems = computed(() => {
  const r = payload.value.risk;
  if (!r) return [];
  const risks = r.notable_risks;
  if (Array.isArray(risks) && risks.length) {
    return [{ label: "风险项", value: risks }];
  }
  return [];
});

const privateItems = computed(() => toItems(payload.value.private, {
  surface_mask: "表面身份",
  secrets: "秘密",
  human_ai_relation_tag: "人机关系",
}));

watch(
  () => props.selectedNode,
  async (node) => {
    archiveData.value = null;
    archiveLoading.value = false;
    if (!node || !props.projectId) return;

    const gen = ++loadGeneration;
    archiveLoading.value = true;
    try {
      const listRes = await listArchiveLibrary({
        q: node.name,
        projectId: props.projectId,
        limit: 10,
      });
      if (gen !== loadGeneration) return;

      const archives = listRes.data?.archives || listRes.data?.items || [];
      const match = archives.find((a) => a.entity_uuid === node.id)
        || archives.find((a) => a.entity_name === node.name);
      if (!match) {
        archiveLoading.value = false;
        return;
      }

      const detailRes = await getArchiveLibraryDetail(match.archive_id);
      if (gen !== loadGeneration) return;

      archiveData.value = detailRes.data;
    } catch {
      // Archive not available — fallback to basic display
    } finally {
      if (gen === loadGeneration) {
        archiveLoading.value = false;
      }
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.detail {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #fffcf4;
  padding: 10px;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.detail h3 {
  margin: 0 0 8px;
  font-family: "ZCOOL XiaoWei", serif;
}

.detail p {
  margin: 6px 0;
  line-height: 1.45;
  color: #564a36;
}

.inspector-header {
  margin-bottom: 6px;
}

.inspector-header h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.badge-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.type-badge,
.tier-badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.type-badge {
  background: rgba(0, 78, 137, 0.1);
  color: #004e89;
}

.tier-badge {
  background: rgba(233, 30, 99, 0.1);
  color: #c2185b;
}

.archive-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 0;
  color: #9a8b6f;
  font-size: 12.5px;
}

.loading-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9a8b6f;
  animation: pulse-dot 1s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.fallback-summary {
  padding: 4px 0;
}

.fallback-summary .aliases {
  font-size: 12px;
  color: #9a8b6f;
}

.no-data {
  color: #b3a68e;
  font-style: italic;
}

.mono {
  font-family: "Courier New", monospace;
  font-size: 11px;
  word-break: break-all;
}
</style>
