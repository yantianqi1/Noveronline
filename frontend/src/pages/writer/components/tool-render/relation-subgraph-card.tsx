/**
 * RelationSubgraphCard — read-only view of a graph neighborhood around one or
 * more focus entities. Renders as two sections: a node roster (focus vs
 * peripheral) and a simple edge list grouped by focus node.
 *
 * We deliberately avoid a full D3 force layout here: the card is a summary,
 * not an interactive canvas. Users who need the full graph open the
 * story-graph page (see `onOpenEntity`).
 */

import {
  ArrowUpRight,
  Circle,
  type LucideIcon,
  MapPin,
  Package,
  Sparkles,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import type {
  RelationSubgraphData,
  RelationSubgraphEdge,
  RelationSubgraphNode,
  RenderHostContext,
  ToolRenderAction,
} from "./types";

export interface RelationSubgraphCardProps {
  data: RelationSubgraphData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

const ENTITY_TYPE_ICON: Record<RelationSubgraphNode["entity_type"], LucideIcon> = {
  character: Users,
  organization: Users,
  location: MapPin,
  item: Package,
  skill: Sparkles,
};

const ENTITY_TYPE_LABEL: Record<RelationSubgraphNode["entity_type"], string> = {
  character: "角色",
  organization: "组织",
  location: "地点",
  item: "物品",
  skill: "技能",
};

function pickNodeById(
  nodes: RelationSubgraphNode[],
  id: string,
): RelationSubgraphNode | undefined {
  return nodes.find((n) => n.entity_id === id);
}

export function RelationSubgraphCard({ data, context }: RelationSubgraphCardProps) {
  const focusSet = new Set(data.focus_entity_ids);
  const focusNodes = data.nodes.filter((n) => focusSet.has(n.entity_id) || n.is_focus);
  const peripheralNodes = data.nodes.filter(
    (n) => !focusSet.has(n.entity_id) && !n.is_focus,
  );

  // Group edges by "anchor" focus node for readability.
  const edgesByFocus = new Map<string, RelationSubgraphEdge[]>();
  for (const edge of data.edges) {
    const anchor = focusSet.has(edge.source_id)
      ? edge.source_id
      : focusSet.has(edge.target_id)
        ? edge.target_id
        : (focusNodes[0]?.entity_id ?? edge.source_id);
    const bucket = edgesByFocus.get(anchor) ?? [];
    bucket.push(edge);
    edgesByFocus.set(anchor, bucket);
  }

  return (
    <Card className="w-full border-blue-500/40 bg-blue-500/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-0.5">
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-[10px]">
                关系子图
              </Badge>
              <span className="text-[11px] text-muted-foreground">
                深度 {data.depth} · {data.stats.node_count} 节点 · {data.stats.edge_count} 关系
              </span>
            </div>
            <div className="truncate text-sm font-medium">
              {focusNodes.map((n) => n.name).join(" · ") || "焦点实体"}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3 pt-0 text-[12px]">
        {focusNodes.length > 0 && (
          <NodeGroup
            title="焦点"
            nodes={focusNodes}
            isFocus
            onOpenEntity={context.onOpenEntity}
          />
        )}
        {peripheralNodes.length > 0 && (
          <NodeGroup
            title={`邻接 (${peripheralNodes.length})`}
            nodes={peripheralNodes}
            isFocus={false}
            onOpenEntity={context.onOpenEntity}
          />
        )}

        {data.edges.length > 0 && (
          <div className="space-y-1">
            <div className="text-[11px] text-muted-foreground">
              关系明细 ({data.edges.length})
            </div>
            <ul className="space-y-1">
              {Array.from(edgesByFocus.entries()).map(([anchorId, edges]) => {
                const anchor = pickNodeById(data.nodes, anchorId);
                return (
                  <li key={anchorId} className="space-y-0.5">
                    {anchor && (
                      <div className="text-[10px] font-medium text-muted-foreground">
                        {anchor.name}
                      </div>
                    )}
                    {edges.slice(0, 6).map((e) => {
                      const src = pickNodeById(data.nodes, e.source_id);
                      const dst = pickNodeById(data.nodes, e.target_id);
                      return (
                        <div
                          key={e.edge_id}
                          className={cn(
                            "flex items-center gap-1.5 rounded border px-2 py-1 text-[11px]",
                            e.is_candidate
                              ? "border-amber-500/40 bg-amber-500/5"
                              : "border-border/40 bg-background/60",
                          )}
                        >
                          <span className="truncate">{src?.name ?? e.source_id}</span>
                          <Badge variant="outline" className="shrink-0 text-[9px]">
                            {e.relation_type}
                          </Badge>
                          <span className="truncate">{dst?.name ?? e.target_id}</span>
                          {typeof e.trust_level === "number" && (
                            <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">
                              {e.trust_level.toFixed(2)}
                            </span>
                          )}
                          {e.is_candidate && (
                            <Badge variant="secondary" className="shrink-0 text-[9px]">
                              候选
                            </Badge>
                          )}
                        </div>
                      );
                    })}
                    {edges.length > 6 && (
                      <div className="px-2 text-[10px] text-muted-foreground">
                        ... 另有 {edges.length - 6} 条
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {data.edges.length === 0 && (
          <div className="rounded border border-dashed border-border/40 bg-background/60 px-2 py-3 text-center text-[11px] text-muted-foreground">
            子图内暂无关系
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function NodeGroup({
  title,
  nodes,
  isFocus,
  onOpenEntity,
}: {
  title: string;
  nodes: RelationSubgraphNode[];
  isFocus: boolean;
  onOpenEntity?: (id: string) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] text-muted-foreground">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {nodes.map((n) => {
          const Icon = ENTITY_TYPE_ICON[n.entity_type] ?? Circle;
          return (
            <button
              key={n.entity_id}
              type="button"
              onClick={() => onOpenEntity?.(n.entity_id)}
              disabled={!onOpenEntity}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                isFocus
                  ? "border-blue-500/50 bg-blue-500/10 text-blue-900 dark:text-blue-200"
                  : "border-border/40 bg-background/60",
                onOpenEntity && "cursor-pointer hover:bg-accent",
                !onOpenEntity && "cursor-default",
              )}
              title={`${ENTITY_TYPE_LABEL[n.entity_type]} · ${n.name}`}
            >
              <Icon className="size-3" />
              <span className="truncate max-w-[8rem]">{n.name}</span>
              {onOpenEntity && <ArrowUpRight className="size-3 opacity-60" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
