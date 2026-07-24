"use client";

import { Pin } from "lucide-react";
import { motion } from "motion/react";

import { cn } from "@/lib/utils";
import type { AssetRecord } from "@/lib/api/asset-types";

import { DUR, EASE, useFadeUp } from "./asset-motion";
import { formatAssetTime, lifecycleChip, presentSource, presentType } from "./asset-present";

/**
 * The asset list: dense, scannable row-cards (pinned first) with a type tile,
 * title, one-line summary, meta row, and a lifecycle chip. Selecting a row
 * opens it in the inspector. Rows are restrained cards — a hairline border and
 * a 1px hover lift, not nested hero panels — and enter with a short stagger.
 */
export function AssetList({
  assets,
  selectedId,
  onSelect,
}: {
  assets: AssetRecord[];
  selectedId: string | null;
  onSelect: (assetId: string) => void;
}) {
  const fadeUp = useFadeUp();
  return (
    <ul role="list" className="flex flex-col gap-1.5 p-3">
      {assets.map((asset, index) => {
        const type = presentType(asset.asset_type);
        const chip = lifecycleChip(asset.lifecycle);
        const active = asset.asset_id === selectedId;
        return (
          <motion.li
            key={asset.asset_id}
            initial={fadeUp.initial}
            animate={fadeUp.animate}
            transition={{ delay: Math.min(index, 12) * 0.03, duration: DUR.med, ease: EASE }}
          >
            <button
              type="button"
              onClick={() => onSelect(asset.asset_id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex w-full items-start gap-3 rounded-[10px] border px-4 py-3 text-left",
                "transition-[transform,box-shadow,background-color,border-color] duration-200",
                "motion-safe:hover:-translate-y-px",
                active
                  ? "border-accent/35 bg-accent-wash/60"
                  : "border-transparent hover:border-line hover:bg-panel hover:shadow-(--shadow-lift)",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 grid size-9 shrink-0 place-items-center rounded-[9px] border",
                  active ? "border-accent/35 bg-panel text-accent" : "border-line bg-panel text-muted",
                )}
              >
                <type.icon className="size-[17px]" aria-hidden />
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  {asset.pinned ? (
                    <Pin className="size-[13px] shrink-0 fill-accent/70 text-accent" aria-label="已置顶" />
                  ) : null}
                  <span className="truncate font-serif text-[15.5px] font-semibold text-ink">
                    {asset.title || "未命名资产"}
                  </span>
                </span>
                {asset.summary ? (
                  <span className="mt-1 line-clamp-1 block text-[13px] leading-relaxed text-muted">
                    {asset.summary}
                  </span>
                ) : null}
                <span className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11.5px] text-muted/80">
                  <span>{type.label}</span>
                  <Dot />
                  <span>{presentSource(asset.source_kind)}</span>
                  {asset.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="rounded-full bg-paper-deep/70 px-2 py-px text-[11px] text-muted">
                      {tag}
                    </span>
                  ))}
                  <span className="ml-auto shrink-0 tabular-nums">{formatAssetTime(asset.updated_at)}</span>
                </span>
              </span>

              <span
                className={cn(
                  "mt-0.5 shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                  chip.className,
                )}
              >
                {chip.label}
              </span>
            </button>
          </motion.li>
        );
      })}
    </ul>
  );
}

function Dot() {
  return (
    <span aria-hidden className="text-muted/40">
      ·
    </span>
  );
}
