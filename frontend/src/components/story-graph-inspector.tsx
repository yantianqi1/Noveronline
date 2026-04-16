import * as React from "react";
import { ChevronDown, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { GraphNodeVM, GraphEdgeVM } from "@/pages/story-graph/graph-view-model";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { listArchiveLibrary, getArchiveLibraryDetail } from "@/api/archive";
import type { ApiResponse } from "@/api/http";
import { sanitizeDisplayText, sanitizeDisplayValue } from "@/pages/story-graph/display-text";

/* ---------- constants ---------- */

const TYPE_LABELS: Record<string, string> = {
  character: "角色",
  organization: "组织",
  faction: "势力",
  group: "群体",
  artifact: "物件",
  knowledgeitem: "知识",
  plotevent: "事件",
  location: "地点",
  rulesystem: "规则",
  relationship: "关系",
};

const TIER_LABELS: Record<string, string> = {
  protagonist: "主角",
  major: "主要",
  supporting: "辅助",
  minor: "次要",
};

/* ---------- types ---------- */

interface InspectorItem {
  label: string;
  value: string | string[];
}

export interface StoryGraphInspectorProps {
  selectedNode?: GraphNodeVM | null;
  selectedEdge?: GraphEdgeVM | null;
  projectId?: string;
  className?: string;
}

/* ---------- helpers ---------- */

function getTypeLabel(type: string | undefined): string {
  const t = (type || "").toLowerCase();
  return TYPE_LABELS[t] || type || "未分类";
}

function getTierLabel(tier: string | undefined): string {
  if (!tier) return "";
  return TIER_LABELS[tier] || "";
}

function isEventNode(type: string | undefined): boolean {
  const t = (type || "").toLowerCase();
  return t === "plotevent" || t === "conflict" || t === "event";
}

function toItems(
  obj: Record<string, unknown> | undefined,
  fieldMap: Record<string, string>,
): InspectorItem[] {
  if (!obj) return [];
  const items: InspectorItem[] = [];
  for (const [key, label] of Object.entries(fieldMap)) {
    const val = obj[key];
    if (val === undefined || val === null || val === "") continue;
    if (Array.isArray(val) && val.length === 0) continue;
    items.push({
      label,
      value: Array.isArray(val)
        ? val.map((item) => sanitizeDisplayText(item, { emptyLabel: "" })).filter(Boolean)
        : sanitizeDisplayText(val, { emptyLabel: "" }),
    });
  }
  return items;
}

/* ---------- sub-components ---------- */

function InspectorSection({
  title,
  items,
  defaultOpen = true,
}: {
  title: string;
  items: InspectorItem[];
  defaultOpen?: boolean;
}) {
  const [expanded, setExpanded] = React.useState(defaultOpen);

  if (!items.length) return null;

  return (
    <div className="overflow-hidden rounded-lg border border-border/60 bg-card/60">
      <button
        type="button"
        className="flex w-full items-center justify-between px-2.5 py-2 text-left text-[13px] font-medium transition-colors hover:bg-muted/40"
        onClick={() => setExpanded(!expanded)}
      >
        <span>{title}</span>
        <ChevronDown
          className={cn(
            "h-3 w-3 text-muted-foreground transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>
      {expanded && (
        <div className="px-2.5 pb-2">
          {items.map((item, idx) => (
            <div
              key={idx}
              className={cn(
                "flex flex-col gap-0.5 py-1",
                idx < items.length - 1 && "border-b border-border/20",
              )}
            >
              <span className="text-[11px] font-medium text-muted-foreground">
                {item.label}
              </span>
              {Array.isArray(item.value) ? (
                <div className="flex flex-wrap gap-1">
                  {item.value.map((tag, ti) => (
                    <span
                      key={ti}
                      className="rounded bg-muted px-1.5 py-0.5 text-[11.5px]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="break-words text-[12.5px] leading-relaxed">
                  {item.value}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EventCard({ node }: { node: GraphNodeVM }) {
  const attrs = node.attributes || {};
  const chapterId = sanitizeDisplayText(attrs.chapter_id, { emptyLabel: "" });
  const summary = sanitizeDisplayText(node.summary || "", { emptyLabel: "" });
  const participants = ((attrs.participants as string[]) || [])
    .map((item) => sanitizeDisplayText(item, { emptyLabel: "" }))
    .filter(Boolean);
  const consequence = sanitizeDisplayText(attrs.consequence, { emptyLabel: "" });
  const evidenceRefs = (attrs.evidence_refs as Array<string | { snippet?: string }>) || [];
  const evidence = evidenceRefs
    .map((r) => sanitizeDisplayText(typeof r === "string" ? r : r.snippet || "", { emptyLabel: "" }))
    .filter(Boolean)
    .slice(0, 3);

  return (
    <div className="py-1">
      {chapterId && (
        <div className="mb-1 font-mono text-[11px] text-muted-foreground">
          {chapterId}
        </div>
      )}
      {summary && summary !== node.name ? (
        <p className="whitespace-pre-wrap text-[13px] leading-relaxed">
          {summary}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground italic">
          {"暂无事件描述（流水线未产出 key_events）。"}
        </p>
      )}
      {participants.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">{"参与者："}</span>
          {participants.map((p) => (
            <Badge key={p} variant="secondary" className="text-[11px]">
              {p}
            </Badge>
          ))}
        </div>
      )}
      {consequence && (
        <div className="mt-2 text-xs">
          <span className="text-muted-foreground">{"影响："}</span>
          {consequence}
        </div>
      )}
      {evidence.length > 0 && (
        <div className="mt-2">
          <div className="text-xs text-muted-foreground">
            {"原文佐证"}
          </div>
          {evidence.map((ev, idx) => (
            <p key={idx} className="mt-0.5 text-xs leading-snug text-foreground/70">
              &mdash; {ev}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- main component ---------- */

export function StoryGraphInspector({
  selectedNode,
  selectedEdge,
  projectId,
  className,
}: StoryGraphInspectorProps) {
  const [archiveData, setArchiveData] = React.useState<Record<string, unknown> | null>(null);
  const [archiveLoading, setArchiveLoading] = React.useState(false);
  const loadGenerationRef = React.useRef(0);

  // Load archive data when a node is selected
  React.useEffect(() => {
    setArchiveData(null);
    setArchiveLoading(false);

    if (!selectedNode || !projectId) return;

    // Event nodes don't have archives
    if (isEventNode(selectedNode.entity_type)) return;

    const gen = ++loadGenerationRef.current;
    setArchiveLoading(true);

    (async () => {
      try {
        const listRes = await listArchiveLibrary({
          q: selectedNode.name,
          projectId,
          limit: 10,
        });
        if (gen !== loadGenerationRef.current) return;

        const data = (listRes as ApiResponse).data as Record<string, unknown>;
        const archives = (data?.archives || data?.items || []) as Array<Record<string, unknown>>;
        const match = archives.find((a) => a.entity_uuid === selectedNode.id)
          || archives.find((a) => a.entity_name === selectedNode.name);

        if (!match) {
          setArchiveLoading(false);
          return;
        }

        const detailRes = await getArchiveLibraryDetail(String(match.archive_id));
        if (gen !== loadGenerationRef.current) return;

        setArchiveData(
          sanitizeDisplayValue((detailRes as ApiResponse).data) as Record<string, unknown>,
        );
      } catch {
        // Archive not available — fallback to basic display
      } finally {
        if (gen === loadGenerationRef.current) {
          setArchiveLoading(false);
        }
      }
    })();
  }, [selectedNode, projectId]);

  const typeLabel = selectedNode ? getTypeLabel(selectedNode.entity_type) : "";
  const tierLabel = selectedNode
    ? getTierLabel(
        (archiveData?.importance_tier as string)
        || (archiveData?.selected_importance_tier as string)
        || (selectedNode.attributes?.importance_tier as string),
      )
    : "";
  const isEvent = selectedNode ? isEventNode(selectedNode.entity_type) : false;
  const aliasesList = ((selectedNode?.attributes?.aliases as string[]) || [])
    .map((item) => sanitizeDisplayText(item, { emptyLabel: "" }))
    .filter(Boolean);

  // Build inspector sections from archive template_payload
  const payload = (archiveData?.template_payload as Record<string, Record<string, unknown>>) || {};

  const entityType = (selectedNode?.entity_type || "").toLowerCase();

  const identityItems = toItems(payload.identity, {
    role: "叙事定位",
    identity_hint: "身份线索",
    entity_name: "名称",
  });

  const motivationItems = toItems(payload.motivation, {
    core_drive: "核心驱力",
  });

  const tensionItems = toItems(payload.tension, {
    hidden_tension: "隐藏张力",
  });

  const relationshipItems = (() => {
    const rel = payload.relationship;
    if (!rel) return [];
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
  })();

  const behaviorItems = (() => {
    const b = payload.behavior;
    if (!b) return [];
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
  })();

  const stateItems = toItems(payload.state, {
    status: "状态",
    surface_mask: "表面形象",
    can_act_as_agent: "可作为Agent",
  });

  const riskItems = (() => {
    const r = payload.risk;
    if (!r) return [];
    const risks = r.notable_risks;
    if (Array.isArray(risks) && risks.length) {
      return [{ label: "风险项", value: risks.map(String) }];
    }
    return [];
  })();

  const privateItems = toItems(payload.private, {
    surface_mask: "表面身份",
    secrets: "秘密",
    human_ai_relation_tag: "人机关系",
  });

  const hasSections =
    identityItems.length > 0 ||
    motivationItems.length > 0 ||
    tensionItems.length > 0 ||
    relationshipItems.length > 0 ||
    behaviorItems.length > 0 ||
    stateItems.length > 0 ||
    riskItems.length > 0 ||
    privateItems.length > 0;

  /* ---- Node selected ---- */
  if (selectedNode) {
    return (
      <ScrollArea
        className={cn(
          "h-full min-h-0 overflow-y-auto rounded-lg border border-border bg-[#fffcf4] p-2.5",
          className,
        )}
      >
        {/* Header */}
        <div className="mb-1.5">
          <h3 className="text-base font-semibold">{selectedNode.name}</h3>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge variant="secondary" className="text-[11px]">
              {typeLabel}
            </Badge>
            {tierLabel && (
              <Badge variant="outline" className="text-[11px]">
                {tierLabel}
              </Badge>
            )}
          </div>
        </div>

        <Separator className="my-2" />

        {/* Event node */}
        {isEvent && <EventCard node={selectedNode} />}

        {/* Archive loading */}
        {!isEvent && archiveLoading && (
          <div className="flex items-center gap-1.5 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {"档案加载中..."}
          </div>
        )}

        {/* Archive sections */}
        {!isEvent && !archiveLoading && hasSections && (
          <div className="flex flex-col gap-2">
            <InspectorSection title={"身份特征"} items={identityItems} />
            <InspectorSection title={"动机驱力"} items={motivationItems} />
            <InspectorSection title={"内在张力"} items={tensionItems} />
            <InspectorSection title={"关系网络"} items={relationshipItems} />
            <InspectorSection title={"行为模式"} items={behaviorItems} />
            <InspectorSection title={"当前状态"} items={stateItems} />
            <InspectorSection title={"风险标记"} items={riskItems} />
            <InspectorSection title={"隐秘档案"} items={privateItems} />
          </div>
        )}

        {/* Fallback: no archive */}
        {!isEvent && !archiveLoading && !hasSections && (
          <div className="py-1">
            {selectedNode.summary && (
              <p className="text-sm">{selectedNode.summary}</p>
            )}
            {aliasesList.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {"别名: "}{aliasesList.join("、")}
              </p>
            )}
            {!selectedNode.summary && (
              <p className="text-sm text-muted-foreground italic">
                {"暂无档案数据，可先生成角色档案。"}
              </p>
            )}
          </div>
        )}
      </ScrollArea>
    );
  }

  /* ---- Edge selected ---- */
  if (selectedEdge) {
    return (
      <ScrollArea
        className={cn(
          "h-full min-h-0 overflow-y-auto rounded-lg border border-border bg-[#fffcf4] p-2.5",
          className,
        )}
      >
        <h3 className="mb-2 text-base font-semibold">{"关系档案"}</h3>
        <Separator className="mb-2" />
        <div className="flex flex-col gap-1.5 text-sm">
          <p>
            <strong className="text-muted-foreground">{"关系: "}</strong>
            {selectedEdge.name || "关系"}
          </p>
          <p>
            <strong className="text-muted-foreground">{"来源: "}</strong>
            {selectedEdge.source_name || selectedEdge.source_id}
          </p>
          <p>
            <strong className="text-muted-foreground">{"目标: "}</strong>
            {selectedEdge.target_name || selectedEdge.target_id}
          </p>
          {selectedEdge.fact && (
            <p>
              <strong className="text-muted-foreground">{"说明: "}</strong>
              {selectedEdge.fact}
            </p>
          )}
          {(selectedEdge.weight ?? 0) > 1 && (
            <p>
              <strong className="text-muted-foreground">{"关联强度: "}</strong>
              {selectedEdge.weight} {"次"}
            </p>
          )}
        </div>
      </ScrollArea>
    );
  }

  /* ---- Nothing selected ---- */
  return (
    <div
      className={cn(
        "grid h-full min-h-0 place-items-center rounded-lg border border-border bg-[#fffcf4] p-2.5 text-sm text-muted-foreground",
        className,
      )}
    >
      {"点击图中的节点或关系线，查看详细信息。"}
    </div>
  );
}
