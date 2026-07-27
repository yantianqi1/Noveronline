"use client";

import { motion } from "motion/react";
import { Globe2, Sparkles } from "lucide-react";

import type { GraphSnapshot } from "@/lib/api/graph-types";
import { layerVisual } from "./graph-visual";

/**
 * Left rail for the Story Graph — snapshot provenance plus a refined layer
 * filter. Concepts fan out into 分析·事件 / 世界观·设定 / 概念 so the rail can
 * actually discriminate, and background concepts start hidden so the canvas
 * opens on a clean人物关系图. A 世界 scope filter (现代/古代) further narrows
 * the timeline-event band. Counts are live from the loaded viewport.
 */

export type LayerSpec = {
  /** Stable key — node_type for entities, "concept:<subtype>" for concepts. */
  key: string;
  label: string;
  count: number;
  /** Background concepts render below the divider and start hidden. */
  isConcept: boolean;
};

export type GraphFilterRailProps = {
  snapshot: GraphSnapshot | null;
  layers: LayerSpec[];
  hidden: Set<string>;
  onToggle: (layerKey: string) => void;
  onShowAll: () => void;
  /** 世界 scope: "all" | "modern" | "ancient" (applies to timeline events). */
  worldScope: string;
  onWorldScope: (scope: string) => void;
  /** Whether any timeline-event layer is present (controls 世界 filter visibility). */
  hasEvents: boolean;
};

export function GraphFilterRail({
  snapshot,
  layers,
  hidden,
  onToggle,
  onShowAll,
  worldScope,
  onWorldScope,
  hasEvents,
}: GraphFilterRailProps) {
  const entityLayers = layers.filter((l) => !l.isConcept);
  const conceptLayers = layers.filter((l) => l.isConcept);
  const hiddenCount = hidden.size;

  return (
    <aside className="hidden h-full w-rail-filter shrink-0 flex-col gap-5 overflow-y-auto border-r border-line-soft bg-panel px-4 py-5 stack:flex">
      {/* Snapshot provenance */}
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="rounded-modal border border-line bg-paper p-4"
      >
        <div className="flex items-center gap-2 text-caption font-medium tracking-label text-gold">
          <Sparkles className="size-3.5" aria-hidden />
          图谱快照
        </div>
        {snapshot ? (
          <dl className="mt-3 space-y-2 text-caption">
            <div className="flex items-baseline justify-between">
              <dt className="text-muted">版本</dt>
              <dd className="font-medium tabular-nums text-ink">v{snapshot.version}</dd>
            </div>
            <div className="flex items-baseline justify-between">
              <dt className="text-muted">节点</dt>
              <dd className="font-medium tabular-nums text-ink">{snapshot.node_count}</dd>
            </div>
            <div className="flex items-baseline justify-between">
              <dt className="text-muted">关系</dt>
              <dd className="font-medium tabular-nums text-ink">{snapshot.edge_count}</dd>
            </div>
            <div className="flex items-baseline justify-between">
              <dt className="text-muted">状态</dt>
              <dd className="font-medium text-ink">{statusLabel(snapshot.status)}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-3 text-caption leading-relaxed text-muted">尚无快照</p>
        )}
      </motion.section>

      {/* Layer filter / legend */}
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="mb-2.5 flex items-center justify-between px-1">
          <h2 className="text-caption font-medium tracking-label text-muted">图层</h2>
          {hiddenCount > 0 ? (
            <button
              type="button"
              onClick={onShowAll}
              className="text-caption font-medium text-accent transition-colors hover:text-accent-strong"
            >
              全部显示
            </button>
          ) : null}
        </div>

        <ul className="space-y-1 overflow-y-auto">
          {entityLayers.map((layer, index) => (
            <LayerRow key={layer.key} layer={layer} hidden={hidden} onToggle={onToggle} index={index} />
          ))}
        </ul>

        {conceptLayers.length > 0 ? (
          <>
            <div className="my-3 flex items-center gap-2 px-1">
              <span className="h-px flex-1 bg-line-soft" />
              <span className="text-caption tracking-label text-muted-soft">背景概念</span>
              <span className="h-px flex-1 bg-line-soft" />
            </div>
            <ul className="space-y-1 overflow-y-auto">
              {conceptLayers.map((layer, index) => (
                <LayerRow key={layer.key} layer={layer} hidden={hidden} onToggle={onToggle} index={index} />
              ))}
            </ul>
          </>
        ) : null}

        {/* 世界 scope — narrows the timeline-event band */}
        {hasEvents ? (
          <div className="mt-4 rounded-modal border border-line bg-paper p-3">
            <div className="mb-2 flex items-center gap-1.5 text-caption font-medium tracking-label text-muted">
              <Globe2 className="size-3" aria-hidden />
              世界
            </div>
            <div className="grid grid-cols-3 gap-1 rounded-panel bg-paper-deep p-1">
              {[
                { value: "all", label: "全部" },
                { value: "modern", label: "现代" },
                { value: "ancient", label: "古代" },
              ].map((opt) => {
                const active = worldScope === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onWorldScope(opt.value)}
                    aria-pressed={active}
                    className={`rounded-control px-1 py-1.5 text-caption font-medium transition-all ${
 active ? "bg-panel text-accent shadow-hairline" : "text-muted hover:text-ink"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-caption leading-relaxed text-muted-soft">只影响「分析·事件」星点的归属。</p>
          </div>
        ) : null}

        <p className="mt-auto px-1 pt-4 text-caption leading-relaxed text-muted-soft">
          点按图层可隐藏或显示对应星点；背景概念默认收起，点亮后按世界成带收纳。
        </p>
      </motion.section>
    </aside>
  );
}

function LayerRow({
  layer,
  hidden,
  onToggle,
  index,
}: {
  layer: LayerSpec;
  hidden: Set<string>;
  onToggle: (key: string) => void;
  index: number;
}) {
  const visual = layerVisual(layer.key);
  const Icon = visual.icon;
  const isHidden = hidden.has(layer.key);
  return (
    <motion.li
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.1 + index * 0.04, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <button
        type="button"
        onClick={() => onToggle(layer.key)}
        aria-pressed={!isHidden}
        className={`group flex w-full items-center gap-3 rounded-panel px-2.5 py-2 text-left transition-all duration-200 ${
 isHidden ? "opacity-45 hover:opacity-75" : "hover:bg-accent-wash"
        }`}
      >
        <span
          className="grid size-7 shrink-0 place-items-center rounded-panel transition-transform duration-200 group-hover:scale-110"
          style={{
            backgroundColor: isHidden ? "rgba(86,69,45,0.06)" : visual.soft,
            color: isHidden ? "#a89f88" : visual.color,
          }}
        >
          <Icon className="size-3.5" aria-hidden />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{layer.label}</span>
        <span className="shrink-0 text-caption tabular-nums text-muted">{layer.count}</span>
      </button>
    </motion.li>
  );
}

function statusLabel(status: string): string {
  switch (status) {
    case "ready":
      return "就绪";
    case "building":
      return "构建中";
    case "failed":
      return "失败";
    default:
      return status || "—";
  }
}
