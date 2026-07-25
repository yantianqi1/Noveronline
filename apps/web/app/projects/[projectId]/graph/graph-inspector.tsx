"use client";

import { motion } from "motion/react";
import { X, Fingerprint, Tags, Users, FileText, Waypoints, Globe2 } from "lucide-react";

import type { GraphEdge, GraphEvidence, GraphNode, GraphNodeDetail } from "@/lib/api/graph-types";
import { resolveConcept } from "./graph-concept";
import { edgeTypeLabel, layerVisual, lifecycleLabel, nodeVisual } from "./graph-visual";

/**
 * Right-hand dossier for the focused node — light "paper & ink" edition.
 *
 * Reads the real node detail (aliases + labels), live neighbours, and public
 * evidence. The header carries a soft vermilion aura keyed to the node's layer
 * (concept subtypes resolve to their own palette + label); a concept shows its
 * cleaned Chinese-first display title and flags machine-placeholder titles as
 * 待命名, plus its 所属世界 / 类型 / 时间线 provenance. The raw title + full
 * summary stay intact below. Every section is honest about empty states.
 * Clicking a neighbour re-focuses the constellation on it.
 */

export type GraphInspectorProps = {
  node: GraphNode;
  detail: GraphNodeDetail | null;
  evidence: GraphEvidence | null;
  neighbours: Array<{ node: GraphNode; edge: GraphEdge }>;
  loading: boolean;
  onClose: () => void;
  onFocusNode: (nodeId: string) => void;
};

export function GraphInspector({
  node,
  detail,
  evidence,
  neighbours,
  loading,
  onClose,
  onFocusNode,
}: GraphInspectorProps) {
  const concept = resolveConcept(node);
  const visual = concept ? layerVisual(`concept:${concept.subtype}`) : nodeVisual(node.node_type);
  const Icon = visual.icon;
  const importance = Math.max(0, Math.min(1, node.importance || 0));
  const displayTitle = concept ? concept.displayTitle : node.title;

  return (
    <motion.aside
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="flex h-full w-[336px] shrink-0 flex-col overflow-hidden border-l border-line bg-panel"
    >
      {/* Header */}
      <div className="relative shrink-0 overflow-hidden border-b border-line-soft px-5 pb-5 pt-5">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-24"
          style={{ background: `radial-gradient(120% 100% at 50% 0%, ${visual.soft}, transparent 70%)` }}
        />
        <div className="relative flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span
              className="grid size-11 shrink-0 place-items-center rounded-full"
              style={{
                background: `radial-gradient(circle at 32% 28%, ${visual.color}, ${visual.color}dd 72%)`,
                color: "#fdf3e3",
                boxShadow: `0 6px 16px -6px ${visual.color}88`,
              }}
            >
              <Icon className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-[10.5px] font-medium tracking-[0.22em]" style={{ color: visual.color }}>
                {visual.label}
              </p>
              <h2 className="mt-0.5 truncate font-serif text-[20px] font-semibold leading-tight text-ink">
                {displayTitle}
              </h2>
              {concept?.isUntitled ? (
                <p className="mt-1 text-[11px] italic text-muted">原始记录缺少标题，此为系统整理的临时名。</p>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="grid size-8 shrink-0 place-items-center rounded-[9px] text-muted transition-colors hover:bg-paper-deep hover:text-ink"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>

        {/* Importance + lifecycle */}
        <div className="relative mt-4 flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center justify-between text-[10.5px] text-muted">
              <span>重要度</span>
              <span className="tabular-nums text-ink-soft">{Math.round(importance * 100)}</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-paper-deep">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${importance * 100}%` }}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                className="h-full rounded-full"
                style={{ background: `linear-gradient(90deg, ${visual.color}, #b5854a)` }}
              />
            </div>
          </div>
          <span className="shrink-0 rounded-full border border-line bg-paper px-2.5 py-1 text-[10.5px] font-medium text-ink-soft">
            {lifecycleLabel(node.lifecycle)}
          </span>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {loading ? (
          <InspectorSkeleton />
        ) : (
          <div className="space-y-6">
            {/* Concept provenance — 所属世界 / 类型 / 时间线 */}
            {concept ? (
              <section>
                <SectionTitle icon={Globe2} label="归 属" />
                <dl className="grid grid-cols-3 gap-2">
                  <div className="rounded-[10px] border border-line bg-paper px-3 py-2">
                    <dt className="text-[10px] tracking-[0.14em] text-muted">所属世界</dt>
                    <dd className="mt-0.5 text-[12.5px] font-medium text-ink">{concept.world}</dd>
                  </div>
                  <div className="rounded-[10px] border border-line bg-paper px-3 py-2">
                    <dt className="text-[10px] tracking-[0.14em] text-muted">类型</dt>
                    <dd className="mt-0.5 text-[12.5px] font-medium text-ink">{concept.subtypeLabel}</dd>
                  </div>
                  <div className="rounded-[10px] border border-line bg-paper px-3 py-2">
                    <dt className="text-[10px] tracking-[0.14em] text-muted">时间线</dt>
                    <dd className="mt-0.5 truncate text-[12.5px] font-medium text-ink" title={concept.timeframe}>
                      {concept.timeframe || "—"}
                    </dd>
                  </div>
                </dl>
              </section>
            ) : null}

            {/* Summary */}
            <section>
              <SectionTitle icon={FileText} label="梗概" />
              <p className="text-[13px] leading-relaxed text-ink-soft">
                {node.summary ? node.summary : <span className="text-muted">暂无梗概。</span>}
              </p>
            </section>

            {/* Aliases */}
            <section>
              <SectionTitle icon={Fingerprint} label="别名" />
              {detail && detail.aliases.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {detail.aliases.map((alias) => (
                    <span
                      key={alias}
                      className="rounded-full border border-line bg-paper px-2.5 py-1 text-[11.5px] text-ink-soft"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-[12px] text-muted">暂无别名。</p>
              )}
            </section>

            {/* Labels */}
            {detail && detail.labels.length > 0 ? (
              <section>
                <SectionTitle icon={Tags} label="标签" />
                <div className="flex flex-wrap gap-1.5">
                  {detail.labels.map((label) => (
                    <span
                      key={label}
                      className="rounded-full px-2.5 py-1 text-[11.5px]"
                      style={{ backgroundColor: visual.soft, color: visual.ink }}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </section>
            ) : null}

            {/* Neighbours */}
            <section>
              <SectionTitle icon={Users} label={`关系 · ${neighbours.length}`} />
              {neighbours.length > 0 ? (
                <ul className="space-y-1.5">
                  {neighbours.map(({ node: neighbour, edge }) => {
                    const nConcept = resolveConcept(neighbour);
                    const nVisual = nConcept ? layerVisual(`concept:${nConcept.subtype}`) : nodeVisual(neighbour.node_type);
                    const NIcon = nVisual.icon;
                    return (
                      <li key={edge.edge_id}>
                        <button
                          type="button"
                          onClick={() => onFocusNode(neighbour.node_id)}
                          className="group flex w-full items-center gap-2.5 rounded-[10px] border border-transparent px-2 py-2 text-left transition-all duration-200 hover:border-line hover:bg-accent-wash"
                        >
                          <span
                            className="grid size-7 shrink-0 place-items-center rounded-[8px]"
                            style={{ backgroundColor: nVisual.soft, color: nVisual.color }}
                          >
                            <NIcon className="size-3.5" aria-hidden />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium text-ink">
                              {nConcept ? nConcept.displayTitle : neighbour.title}
                            </span>
                            <span className="block truncate text-[11px] text-muted">
                              {edge.label || edgeTypeLabel(edge.edge_type)}
                            </span>
                          </span>
                          <Waypoints
                            className="size-3.5 shrink-0 text-muted/50 transition-colors group-hover:text-accent"
                            aria-hidden
                          />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-[12px] text-muted">这片星区还没有连出关系。</p>
              )}
            </section>

            {/* Evidence */}
            <section>
              <SectionTitle icon={FileText} label={`佐证 · ${evidence?.items.length ?? node.evidence_count}`} />
              {evidence && evidence.items.length > 0 ? (
                <ul className="space-y-2">
                  {evidence.items.map((item) => (
                    <li key={item.evidence_id} className="rounded-[10px] border border-line bg-paper px-3 py-2.5">
                      <div className="flex items-center justify-between gap-2 text-[10.5px] text-muted">
                        <span className="truncate">{item.source_type}</span>
                        <span className="shrink-0 tabular-nums text-ink-soft">
                          {Math.round((item.confidence || 0) * 100)}%
                        </span>
                      </div>
                      <div className="mt-1 h-0.5 overflow-hidden rounded-full bg-paper-deep">
                        <div
                          className="h-full rounded-full bg-gold"
                          style={{ width: `${Math.round((item.confidence || 0) * 100)}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12px] text-muted">公开读侧未提供佐证片段。</p>
              )}
            </section>
          </div>
        )}
      </div>
    </motion.aside>
  );
}

function SectionTitle({ icon: Icon, label }: { icon: typeof FileText; label: string }) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-[10.5px] font-medium tracking-[0.2em] text-muted">
      <Icon className="size-3" aria-hidden />
      {label}
    </h3>
  );
}

function InspectorSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-4 w-full animate-pulse rounded bg-paper-deep" />
      <div className="h-4 w-5/6 animate-pulse rounded bg-paper-deep" />
      <div className="h-4 w-2/3 animate-pulse rounded bg-paper-deep" />
      <div className="h-20 w-full animate-pulse rounded-[10px] bg-paper-deep" />
    </div>
  );
}
