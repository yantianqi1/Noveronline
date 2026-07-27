"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { AssetRecord } from "@/lib/api/asset-types";
import type { ProjectOverview, ReadinessSnapshot } from "@/lib/api/overview-types";

/**
 * Readiness rail ("就绪度") — what the analysis has produced so far, shown as
 * three horizontal "mahjong tile" drawers: 人物 / 关系 / 世界规则.
 *
 * Tiles are REAL assets from the project's asset catalog. As the run lands new
 * ready assets, the workspace re-polls `fetchAssets` and passes the growing
 * list down; this rail diffs by `asset_id`, drops each genuinely-new tile into
 * its category drawer with a slam-in animation, and ticks the row's count. It
 * replays nothing on re-render — a tile only animates the moment it first
 * appears.
 */

type DrawerKind = "char" | "rel" | "rule";

type Tile = {
  id: string;
  kind: DrawerKind;
  /** 1–2 char face engraved on the tile. */
  face: string;
  /** Full asset title (tooltip / a11y). */
  title: string;
};

const DRAWERS: {
  kind: DrawerKind;
  glyph: string;
  name: string;
  desc: string;
  /** asset → this drawer. */
  match: (asset: AssetRecord) => boolean;
}[] = [
  {
    kind: "char",
    glyph: "人",
    name: "人物",
    desc: "可推演的角色",
    match: (a) => a.asset_type === "character" || a.category === "characters",
  },
  {
    kind: "rel",
    glyph: "关",
    name: "关系",
    desc: "人物间的牵连",
    match: (a) => a.asset_type === "relationship" || a.category === "relationships",
  },
  {
    kind: "rule",
    glyph: "规",
    name: "世界规则",
    desc: "设定与约束",
    match: (a) =>
      a.asset_type === "world_rule" ||
      a.asset_type === "plot_thread" ||
      a.asset_type === "plot_event" ||
      a.category === "world" ||
      a.category === "plot",
  },
];

/** The tile face: first 1–2 meaningful characters of the asset title. */
function tileFace(title: string): string {
  const clean = title.trim().replace(/[·\s《》「」"'"()].*$/, "");
  const chars = Array.from(clean);
  return chars.slice(0, 2).join("") || title.trim().slice(0, 2) || "·";
}

/** Deterministic pseudo-random from a string seed, so a tile always slams from
 * the same edge across re-renders but different tiles differ. */
function seededUnit(seed: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 1000;
}

/** Per-tile slam direction, derived deterministically from its id. */
function slamVectors(id: string): { rx: string; ry: string; rr: string } {
  const side = Math.floor(seededUnit(id, 1) * 4);
  const dist = 110 + seededUnit(id, 2) * 110;
  const rx = side === 0 ? -dist : side === 1 ? dist : (seededUnit(id, 3) - 0.5) * 70;
  const ry = side === 2 ? -dist : side === 3 ? dist : (seededUnit(id, 4) - 0.5) * 70;
  const rr = (seededUnit(id, 5) - 0.5) * 40;
  return { rx: `${rx.toFixed(0)}px`, ry: `${ry.toFixed(0)}px`, rr: `${rr.toFixed(0)}deg` };
}

export function ReadinessRail({
  readiness,
  overview,
  assets,
}: {
  readiness: ReadinessSnapshot | null;
  overview: ProjectOverview | null;
  assets: AssetRecord[];
}) {
  // Convert the live asset list into tiles, oldest-first so drawers read in
  // arrival order and each new asset appends to the right.
  const tiles = useMemo<Tile[]>(() => {
    const sorted = [...assets].sort((a, b) => a.created_at.localeCompare(b.created_at));
    const out: Tile[] = [];
    for (const asset of sorted) {
      const drawer = DRAWERS.find((d) => d.match(asset));
      if (!drawer) continue;
      out.push({
        id: asset.asset_id,
        kind: drawer.kind,
        face: tileFace(asset.title),
        title: asset.title,
      });
    }
    return out;
  }, [assets]);

  // Which tile ids have already been displayed. On first mount everything is
  // "seen" (no slam storm when the page loads a populated project); afterwards
  // each genuinely-new id animates exactly once.
  const seenRef = useRef<Set<string> | null>(null);
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (seenRef.current === null) {
      seenRef.current = new Set(tiles.map((t) => t.id));
      return;
    }
    const fresh = tiles.filter((t) => !seenRef.current!.has(t.id)).map((t) => t.id);
    if (fresh.length > 0) {
      fresh.forEach((id) => seenRef.current!.add(id));
      setNewIds(new Set(fresh));
    }
  }, [tiles]);

  const byKind = useMemo(() => {
    const map: Record<DrawerKind, Tile[]> = { char: [], rel: [], rule: [] };
    for (const tile of tiles) map[tile.kind].push(tile);
    return map;
  }, [tiles]);

  const total = tiles.length;

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-modal border border-line bg-panel shadow-hairline">
      <div className="border-b border-line-soft px-5 py-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-serif text-md font-semibold text-ink">就绪度</h2>
          <span className="text-caption tracking-wide text-muted">
            {total > 0 ? `${total} 件资产已入库` : "顺序精读产出 · 经分析逐个入库"}
          </span>
        </div>
        <p className="mt-0.5 text-caption text-muted">分析已经读出的故事素材。</p>
      </div>

      {total === 0 ? (
        <EmptyLedger overview={overview} readiness={readiness} />
      ) : (
        <ul className="flex flex-1 flex-col divide-y divide-line-soft">
          {DRAWERS.map((drawer) => (
            <DrawerRow
              key={drawer.kind}
              drawer={drawer}
              tiles={byKind[drawer.kind]}
              newIds={newIds}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function DrawerRow({
  drawer,
  tiles,
  newIds,
}: {
  drawer: (typeof DRAWERS)[number];
  tiles: Tile[];
  newIds: Set<string>;
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const lastCountRef = useRef(tiles.length);

  // Auto-scroll the drawer to follow the newest tile.
  useEffect(() => {
    if (tiles.length > lastCountRef.current && trackRef.current) {
      trackRef.current.scrollTo({ left: trackRef.current.scrollWidth, behavior: "smooth" });
    }
    lastCountRef.current = tiles.length;
  }, [tiles.length]);

  return (
    <li className="flex flex-1 items-center gap-3.5 py-2.5 pl-5">
      <span className="grid size-7 shrink-0 place-items-center rounded-control border border-line-soft bg-panel-2 font-serif text-caption text-ink-soft">
        {drawer.glyph}
      </span>
      <div className="w-[74px] shrink-0">
        <div className="text-caption font-semibold text-ink">{drawer.name}</div>
        <div className="mt-px text-caption text-muted">{drawer.desc}</div>
      </div>
      <span
        className={`w-7 shrink-0 text-right font-serif text-md font-semibold tabular-nums ${
 tiles.length === 0 ? "text-line" : "text-ink"
        }`}
      >
        {tiles.length}
      </span>

      <div className="asset-drawer relative min-w-0 flex-1 overflow-hidden">
        <div
          ref={trackRef}
          className="asset-drawer-track flex gap-2 overflow-x-auto overflow-y-hidden py-1.5 pl-0.5 pr-7"
        >
          {tiles.length === 0 ? (
            <span className="self-center whitespace-nowrap px-1 py-1.5 text-caption text-muted">
              等待入库……
            </span>
          ) : (
            tiles.map((tile, i) => (
              <TileChip key={tile.id} tile={tile} isNew={newIds.has(tile.id)} index={i} />
            ))
          )}
        </div>
        {tiles.length > 0 && (
          <span
            aria-hidden
            className="pointer-events-none absolute right-0.5 top-1/2 -translate-y-1/2 text-micro tracking-label text-muted-soft [writing-mode:vertical-rl]"
          >
            滑动
          </span>
        )}
      </div>
    </li>
  );
}

function TileChip({ tile, isNew, index }: { tile: Tile; isNew: boolean; index: number }) {
  const vec = slamVectors(tile.id);
  const kindClass =
    tile.kind === "char"
      ? "border-accent/50 text-accent-strong"
      : tile.kind === "rel"
        ? "border-line text-candidate"
        : "border-line text-muted";
  return (
    <div
      title={tile.title}
      className={`asset-tile relative flex h-[54px] w-[44px] shrink-0 select-none flex-col items-center justify-center rounded-panel border ${kindClass} ${
 isNew ? "" : "[animation:none]"
      }`}
      style={
        isNew
          ? ({
              "--rx": vec.rx,
              "--ry": vec.ry,
              "--rr": vec.rr,
              animationDelay: `${Math.min(index * 70, 500)}ms`,
            } as React.CSSProperties)
          : undefined
      }
    >
      <span className="px-0.5 text-center font-serif text-md font-semibold">
        {tile.face}
      </span>
    </div>
  );
}

/** Honest pre-data ledger: counts straight from the snapshot, no tiles yet. */
function EmptyLedger({
  overview,
  readiness,
}: {
  overview: ProjectOverview | null;
  readiness: ReadinessSnapshot | null;
}) {
  const rows = [
    { glyph: "人", name: "人物", value: readiness?.ready_entity_count ?? overview?.ready_entity_count ?? 0 },
    { glyph: "关", name: "关系", value: readiness?.ready_relationship_count ?? overview?.ready_relationship_count ?? 0 },
    { glyph: "规", name: "世界规则", value: readiness?.ready_world_rule_count ?? overview?.ready_world_rule_count ?? 0 },
  ];
  return (
    <div className="flex flex-1 flex-col">
      <ul className="divide-y divide-line-soft">
        {rows.map((row) => (
          <li key={row.name} className="flex items-center gap-3.5 px-5 py-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-control border border-line-soft bg-panel-2 font-serif text-caption text-ink-soft">
              {row.glyph}
            </span>
            <span className="flex-1 text-caption font-semibold text-ink">{row.name}</span>
            <span className={`font-serif text-md font-semibold tabular-nums ${row.value === 0 ? "text-line" : "text-ink"}`}>
              {row.value}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-auto border-t border-dashed border-line-soft bg-paper/40 px-5 py-3.5 text-caption leading-relaxed text-muted">
        还没有就绪的素材。完成一次分析后，人物、关系与世界规则会在这里逐块入库。
      </p>
    </div>
  );
}
