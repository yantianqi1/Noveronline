"use client";

import { Check, ChevronDown, Search, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import type { Collection, Facets, SearchCapabilities } from "@/lib/api/asset-types";
import { Input } from "@/components/ui/input";

import { DUR, EASE } from "./asset-motion";
import { lifecycleChip, presentSource, presentType } from "./asset-present";

export type AssetFilterState = {
  query: string;
  assetType: string | null;
  source: string | null;
  lifecycle: string | null;
  collectionId: string | null;
};

export const EMPTY_FILTERS: AssetFilterState = {
  query: "",
  assetType: null,
  source: null,
  lifecycle: null,
  collectionId: null,
};

/**
 * The compact filter bar: a search field plus facet-driven popover pickers for
 * type / source (and collection on small screens), lifecycle status chips, and
 * removable chips for whatever is currently applied. Every option comes from
 * the live facets endpoint, so the bar only ever offers values that actually
 * exist in the project — no fabricated taxonomy.
 */
export function AssetFilterBar({
  value,
  facets,
  capabilities,
  collections,
  lifecycles,
  onChange,
}: {
  value: AssetFilterState;
  facets: Facets | null;
  capabilities: SearchCapabilities | null;
  collections?: Collection[];
  /** Lifecycle facet buckets; falls back to facets.lifecycles when omitted. */
  lifecycles?: { value: string; count: number }[];
  onChange: (next: AssetFilterState) => void;
}) {
  const types = facets?.asset_types ?? [];
  const sources = facets?.sources ?? [];
  const lifecycleBuckets = lifecycles ?? facets?.lifecycles ?? [];

  function set(patch: Partial<AssetFilterState>) {
    onChange({ ...value, ...patch });
  }

  const activeCollection = collections?.find((c) => c.collection_id === value.collectionId) ?? null;

  // Applied, removable filter chips (everything except the free-text query).
  const applied: { key: keyof AssetFilterState; label: string }[] = [];
  if (value.assetType) applied.push({ key: "assetType", label: presentType(value.assetType).label });
  if (value.source) applied.push({ key: "source", label: presentSource(value.source) });
  if (value.lifecycle) applied.push({ key: "lifecycle", label: lifecycleChip(value.lifecycle).label });
  if (activeCollection) applied.push({ key: "collectionId", label: activeCollection.title });

  return (
    <div className="space-y-3 border-b border-line-soft bg-panel/60 px-6 py-4">
      <div className="flex flex-wrap items-center gap-2.5">
        {/* search */}
        <label className="relative min-w-[220px] flex-1">
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 size-[15px] -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            type="search"
            value={value.query}
            onChange={(event) => set({ query: event.target.value })}
            placeholder={
              capabilities && !capabilities.keyword
                ? "按标题或摘要筛选…"
                : "搜索角色、设定、伏笔…"
            }
            aria-label="搜索资产"
            className="h-10 pl-9 text-[13.5px]"
          />
        </label>

        {/* type facet */}
        <FacetPicker
          ariaLabel="按类型筛选"
          placeholder="全部类型"
          value={value.assetType}
          options={types.map((bucket) => ({
            value: bucket.value,
            label: presentType(bucket.value).label,
            count: bucket.count,
          }))}
          onChange={(next) => set({ assetType: next })}
        />

        {/* source facet */}
        <FacetPicker
          ariaLabel="按来源筛选"
          placeholder="全部来源"
          value={value.source}
          options={sources.map((bucket) => ({
            value: bucket.value,
            label: presentSource(bucket.value),
            count: bucket.count,
          }))}
          onChange={(next) => set({ source: next })}
        />

        {/* collection facet (small screens only — the rail covers lg+) */}
        {collections && collections.length > 0 ? (
          <FacetPicker
            ariaLabel="按集合筛选"
            placeholder="全部集合"
            className="lg:hidden"
            value={value.collectionId}
            options={collections.map((collection) => ({
              value: collection.collection_id,
              label: collection.title,
              count: collection.items.length,
            }))}
            onChange={(next) => set({ collectionId: next })}
          />
        ) : null}
      </div>

      {/* lifecycle status chips, driven by the values that actually exist */}
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="按状态筛选">
        <StatusChip
          label="全部"
          active={value.lifecycle === null}
          onClick={() => set({ lifecycle: null })}
        />
        {lifecycleBuckets.map((bucket) => (
          <StatusChip
            key={bucket.value}
            label={`${lifecycleChip(bucket.value).label}（${bucket.count}）`}
            active={value.lifecycle === bucket.value}
            onClick={() => set({ lifecycle: value.lifecycle === bucket.value ? null : bucket.value })}
          />
        ))}
      </div>

      {/* applied filters as removable chips */}
      {applied.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2" aria-label="已应用的筛选">
          {applied.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={() => set({ [chip.key]: null } as Partial<AssetFilterState>)}
              className="group flex h-7 items-center gap-1.5 rounded-full border border-accent/40 bg-accent-wash pl-3 pr-2 text-[12px] font-medium text-accent-strong transition-colors hover:border-accent/60"
              aria-label={`移除筛选：${chip.label}`}
            >
              <span className="truncate">{chip.label}</span>
              <X className="size-[13px] text-accent/70 transition-colors group-hover:text-accent" aria-hidden />
            </button>
          ))}
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="h-7 rounded-full px-2 text-[12px] text-muted transition-colors hover:text-ink"
          >
            清空
          </button>
        </div>
      ) : null}
    </div>
  );
}

function FacetPicker({
  ariaLabel,
  placeholder,
  value,
  options,
  onChange,
  className,
}: {
  ariaLabel: string;
  placeholder: string;
  value: string | null;
  options: { value: string; label: string; count?: number }[];
  onChange: (value: string | null) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  const selected = options.find((option) => option.value === value) ?? null;

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel}
        className={cn(
          "flex h-10 max-w-[190px] items-center gap-2 rounded-[10px] border bg-panel px-3 text-[13px] shadow-sm transition-colors",
          selected
            ? "border-accent/40 text-accent-strong"
            : "border-line text-ink hover:border-accent/40",
        )}
      >
        <span className="truncate">{selected ? selected.label : placeholder}</span>
        <ChevronDown
          className={cn("size-4 shrink-0 text-muted transition-transform duration-200", open && "rotate-180")}
          aria-hidden
        />
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: DUR.fast, ease: EASE }}
            className="absolute left-0 top-[calc(100%+8px)] z-40 max-h-64 w-[220px] origin-top-left overflow-y-auto rounded-card border border-line bg-panel p-1.5 shadow-panel"
          >
            <PickerOption
              label={placeholder}
              checked={value === null}
              onSelect={() => {
                onChange(null);
                setOpen(false);
              }}
            />
            {options.map((option) => (
              <PickerOption
                key={option.value}
                label={option.label}
                count={option.count}
                checked={value === option.value}
                onSelect={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              />
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function PickerOption({
  label,
  count,
  checked,
  onSelect,
}: {
  label: string;
  count?: number;
  checked: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2 rounded-[9px] px-3 py-2 text-left text-[13px] transition-colors",
        checked ? "bg-accent-wash text-accent-strong" : "text-ink-soft hover:bg-paper-deep hover:text-ink",
      )}
    >
      <Check className={cn("size-[15px] shrink-0", checked ? "text-accent" : "text-transparent")} aria-hidden />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {typeof count === "number" ? (
        <span className="shrink-0 text-[11.5px] tabular-nums text-muted">{count}</span>
      ) : null}
    </button>
  );
}

function StatusChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "h-8 rounded-full border px-3.5 text-[12.5px] font-medium transition-colors duration-200",
        active
          ? "border-accent/50 bg-accent-wash text-accent-strong"
          : "border-line bg-panel text-muted hover:border-accent/35 hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}
