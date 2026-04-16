import * as React from "react";
import { Copy, ExternalLink } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

import type { GraphNodeVM, GraphEdgeVM } from "./graph-view-model";
import {
  buildWorldOverview,
  type WorldOverview,
  type HighlightEdge,
} from "./world-overview-model";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface WorldOverviewDashboardProps {
  nodes: GraphNodeVM[];
  edges: GraphEdgeVM[];
  projectName: string;
  onFocusNode?: (nodeId: string) => void;
  onFocusEdge?: (edge: HighlightEdge) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function WorldOverviewDashboard({
  nodes,
  edges,
  projectName,
  onFocusNode,
  onFocusEdge,
}: WorldOverviewDashboardProps) {
  const overview: WorldOverview = React.useMemo(
    () => buildWorldOverview({ nodes, edges, projectName }),
    [nodes, edges, projectName],
  );

  function focusNode(nodeId: string) {
    if (nodeId) onFocusNode?.(nodeId);
  }

  function focusEdge(edge: HighlightEdge) {
    if (edge?.id) onFocusEdge?.(edge);
  }

  function focusFirst(ids: string[] = []) {
    if (ids.length) focusNode(ids[0]!);
  }

  function copyHook(hook: { title: string; body: string; involvedNames: string[] }) {
    const text = `${hook.title}\n\n${hook.body}\n\n涉及：${hook.involvedNames.join(" · ")}`;
    navigator.clipboard?.writeText(text).catch(() => {});
  }

  return (
    <div className="min-h-0 w-full space-y-3.5 overflow-y-auto overflow-x-hidden pr-1 pb-6">
      {/* Hero */}
      <Card className="border-l-4 border-l-primary bg-card p-4">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="min-w-0 break-words text-xl font-bold">{overview.hero.projectName}</h2>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
            世界速览
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-4">
          {[
            { num: overview.hero.totalNodes, lbl: "实体" },
            { num: overview.hero.totalEdges, lbl: "关联" },
            { num: overview.hero.typeCount, lbl: "设定类" },
            { num: overview.hero.eventCount, lbl: "事件" },
          ].map((s) => (
            <div key={s.lbl} className="flex flex-col">
              <span className="font-mono text-2xl font-semibold text-primary">{s.num}</span>
              <span className="text-[11px] text-muted-foreground">{s.lbl}</span>
            </div>
          ))}
        </div>
        <p className="mt-2 break-words text-sm">{overview.hero.headline}</p>
        {(overview.hero.protagonistNames.length > 0 || overview.hero.majorOrgNames.length > 0) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {overview.hero.protagonistNames.map((n) => (
              <span key={`p-${n}`} className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs text-primary">
                ⭐ {n}
              </span>
            ))}
            {overview.hero.majorOrgNames.map((n) => (
              <span key={`o-${n}`} className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-emerald-800 text-xs">
                ⚑ {n}
              </span>
            ))}
          </div>
        )}
      </Card>

      {/* Story Hooks */}
      {overview.hooks.length > 0 && (
        <Card className="bg-card p-3.5">
          <div className="mb-2.5 flex flex-wrap items-baseline gap-3">
            <h3 className="text-[15px] font-semibold">💡 创作锚点</h3>
            <span className="text-xs text-muted-foreground">
              基于图谱派生的可写场景种子 · 共 {overview.hooks.length} 个
            </span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-2.5">
            {overview.hooks.map((hook, idx) => (
              <div
                key={idx}
                className="min-w-0 break-words rounded-lg border border-border bg-muted/20 p-2.5"
              >
                <div className="text-[13.5px] font-semibold">{hook.title}</div>
                <p className="text-[12.5px] leading-relaxed text-muted-foreground">{hook.body}</p>
                <div className="text-[11px] text-muted-foreground">
                  涉及：{hook.involvedNames.join(" · ")}
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-xs"
                    onClick={() => focusFirst(hook.involvedIds)}
                  >
                    <ExternalLink className="mr-1 h-3 w-3" />
                    在图谱中查看
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-xs"
                    onClick={() => copyHook(hook)}
                  >
                    <Copy className="mr-1 h-3 w-3" />
                    复制锚点
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Cast Radar */}
      <Card className="p-3.5">
        <div className="mb-2.5 flex flex-wrap items-baseline gap-3">
          <h3 className="text-[15px] font-semibold">🎭 阵容雷达</h3>
          <span className="text-xs text-muted-foreground">共 {overview.cast.totalCharacters} 个角色</span>
        </div>

        {overview.cast.protagonist.length > 0 && (
          <div className="mb-3">
            <div className="mb-1.5 text-xs font-semibold text-muted-foreground">主角</div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-2">
              {overview.cast.protagonist.map((c) => (
                <div
                  key={c.id}
                  className="min-w-0 cursor-pointer rounded-lg border bg-primary/5 p-2 transition-colors hover:border-primary"
                  onClick={() => focusNode(c.id)}
                >
                  <div className="break-words text-[13px] font-semibold">⭐ {c.name}</div>
                  {c.summary && <p className="mt-0.5 line-clamp-2 text-[11.5px] text-muted-foreground">{c.summary}</p>}
                  <div className="mt-1 font-mono text-[10.5px] text-muted-foreground">关联 {c.degree}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {overview.cast.major.length > 0 && (
          <div className="mb-3">
            <div className="mb-1.5 text-xs font-semibold text-muted-foreground">主要角色</div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-2">
              {overview.cast.major.map((c) => (
                <div
                  key={c.id}
                  className="min-w-0 cursor-pointer rounded-lg border bg-card p-2 transition-colors hover:border-primary"
                  onClick={() => focusNode(c.id)}
                >
                  <div className="break-words text-[13px] font-semibold">{c.name}</div>
                  {c.summary && <p className="mt-0.5 line-clamp-2 text-[11.5px] text-muted-foreground">{c.summary}</p>}
                  <div className="mt-1 font-mono text-[10.5px] text-muted-foreground">关联 {c.degree}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {(overview.cast.supporting.length > 0 || overview.cast.minor.length > 0) && (
          <details className="mb-3">
            <summary className="cursor-pointer text-xs font-semibold text-muted-foreground">
              辅助 / 次要角色（{overview.cast.supporting.length + overview.cast.minor.length}）
            </summary>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {[...overview.cast.supporting, ...overview.cast.minor].map((c) => (
                <span
                  key={c.id}
                  className="cursor-pointer rounded-full bg-muted px-2 py-0.5 text-[11.5px] hover:bg-muted/80"
                  onClick={() => focusNode(c.id)}
                >
                  {c.name}<small className="text-muted-foreground"> · {c.degree}</small>
                </span>
              ))}
            </div>
          </details>
        )}

        {overview.cast.organizations.length > 0 && (
          <div>
            <div className="mb-1.5 text-xs font-semibold text-muted-foreground">组织 / 势力</div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-2">
              {overview.cast.organizations.map((o) => (
                <div
                  key={o.id}
                  className="min-w-0 cursor-pointer rounded-lg border bg-emerald-50/70 p-2 transition-colors hover:border-emerald-500"
                  onClick={() => focusNode(o.id)}
                >
                  <div className="break-words text-[13px] font-semibold">⚑ {o.name}</div>
                  {o.summary && <p className="mt-0.5 line-clamp-2 text-[11.5px] text-muted-foreground">{o.summary}</p>}
                  <div className="mt-1 font-mono text-[10.5px] text-muted-foreground">关联 {o.degree}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Relationship Highlights */}
      <Card className="p-3.5">
        <h3 className="mb-2.5 text-[15px] font-semibold">💞 关系亮点</h3>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          <div>
            <div className="mb-1 text-xs font-semibold text-muted-foreground">核心羁绊 Top 5</div>
            <ol className="m-0 flex list-none flex-col gap-1 p-0">
              {overview.highlights.topBonds.length > 0 ? overview.highlights.topBonds.map((r) => (
                <li
                  key={r.id}
                  className="flex min-w-0 flex-wrap items-baseline gap-1 rounded px-1 py-0.5 text-xs hover:bg-muted/40"
                  onClick={() => focusEdge(r)}
                >
                  <span className="font-medium">{r.sourceName}</span>
                  <span className="text-muted-foreground">— {r.label} →</span>
                  <span className="font-medium">{r.targetName}</span>
                  <span className="ml-auto font-mono text-muted-foreground">×{r.weight}</span>
                </li>
              )) : (
                <li className="text-xs italic text-muted-foreground">暂无</li>
              )}
            </ol>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-muted-foreground">冲突线</div>
            <ol className="m-0 flex list-none flex-col gap-1 p-0">
              {overview.highlights.conflicts.length > 0 ? overview.highlights.conflicts.map((r) => (
                <li
                  key={r.id}
                  className="flex min-w-0 flex-wrap items-baseline gap-1 rounded px-1 py-0.5 text-xs hover:bg-muted/40"
                  onClick={() => focusEdge(r)}
                >
                  <span className="font-medium">{r.sourceName}</span>
                  <span className="text-red-600">⚔</span>
                  <span className="font-medium">{r.targetName}</span>
                  <span className="ml-auto font-mono text-muted-foreground">×{r.weight}</span>
                </li>
              )) : (
                <li className="text-xs italic text-muted-foreground">暂未发现明显冲突</li>
              )}
            </ol>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-muted-foreground">三角关系</div>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {overview.highlights.triangles.length > 0 ? overview.highlights.triangles.map((t, idx) => (
                <li key={idx} className="text-xs">
                  {t.members.map((m) => m.name).join(" — ")}
                </li>
              )) : (
                <li className="text-xs italic text-muted-foreground">暂未发现</li>
              )}
            </ul>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-muted-foreground">孤儿警示</div>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {overview.highlights.orphans.length > 0 ? overview.highlights.orphans.map((o) => (
                <li
                  key={o.id}
                  className="cursor-pointer text-xs text-amber-700 hover:underline"
                  onClick={() => focusNode(o.id)}
                >
                  {o.name}<small className="text-muted-foreground"> · 关联 {o.degree}</small>
                </li>
              )) : (
                <li className="text-xs italic text-muted-foreground">所有角色都有戏份</li>
              )}
            </ul>
          </div>
        </div>
      </Card>

      {/* Event Timeline */}
      {overview.timeline.length > 0 && (
        <Card className="p-3.5">
          <div className="mb-2.5 flex flex-wrap items-baseline gap-3">
            <h3 className="text-[15px] font-semibold">⚡ 事件时间线</h3>
            <span className="text-xs text-muted-foreground">{overview.timeline.length} 个事件</span>
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-2">
            {overview.timeline.map((ev) => (
              <div
                key={ev.id}
                className="flex min-w-[130px] shrink-0 cursor-pointer flex-col items-center rounded-lg p-1.5 hover:bg-muted/30"
                onClick={() => focusNode(ev.id)}
              >
                <div className="font-mono text-[11px] text-muted-foreground">{ev.chapterId || "?"}</div>
                <div className="my-1 h-2.5 w-2.5 rounded-full bg-amber-500" />
                <div className="break-words text-center text-xs font-semibold">{ev.name}</div>
                {ev.participants.length > 0 && (
                  <div className="mt-0.5 text-center text-[11px] text-muted-foreground">
                    {ev.participants.slice(0, 3).map((p) => p.name).join("、")}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* World Rules */}
      {overview.rules.length > 0 && (
        <Card className="p-3.5">
          <h3 className="mb-2.5 text-[15px] font-semibold">📜 世界规则</h3>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-2">
            {overview.rules.map((r) => (
              <div
                key={r.id}
                className="min-w-0 cursor-pointer rounded-lg border p-2 hover:border-primary"
                onClick={() => focusNode(r.id)}
              >
                <div className="break-words text-[12.5px] font-semibold">{r.name}</div>
                {r.summary && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{r.summary}</p>}
                {r.linked.length > 0 ? (
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    关联：
                    {r.linked.map((l) => (
                      <span
                        key={l.id}
                        className="mr-1 inline-block rounded-full bg-green-100 px-1.5 py-0.5 text-green-800"
                      >
                        {l.name}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="mt-1 text-[11px] text-muted-foreground">尚未触发</div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Health Check */}
      {overview.health.length > 0 && (
        <Card className="p-3.5">
          <h3 className="mb-2.5 text-[15px] font-semibold">🩺 异常与缺口</h3>
          {overview.health.map((issue) => (
            <div
              key={issue.kind}
              className={cn(
                "flex items-baseline gap-2.5 border-t border-dashed border-border/60 py-1.5 first:border-t-0",
                issue.severity === "warn" && "text-red-700",
              )}
            >
              <div className="min-w-[110px] text-xs font-semibold">
                {issue.label} · {issue.total}
              </div>
              <div className="flex flex-wrap gap-1">
                {issue.items.map((it) => (
                  <span
                    key={it.id}
                    className="cursor-pointer rounded-full bg-muted px-2 py-0.5 text-[11px] hover:bg-muted/70"
                    onClick={() => focusNode(it.id)}
                  >
                    {it.name}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
