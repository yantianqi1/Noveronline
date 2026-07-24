"use client";

import { CheckCircle2, EyeOff, History, Pin, PinOff, RotateCcw, Sparkles, X } from "lucide-react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import type { AssetVersion, CatalogAsset, Collection } from "@/lib/api/asset-types";

import { DUR, EASE } from "./asset-motion";
import { formatAssetDateTime, isCandidate, lifecycleChip, presentSource, presentType } from "./asset-present";

type InspectorTab = "summary" | "versions" | "collections";

/**
 * The asset inspector: the right-hand detail surface for the selected asset.
 * The header plus the panel's explicit actions (candidate → canon adoption,
 * pin) stay pinned at the top; the body is grouped into 摘要 / 版本 / 集合
 * tabs so long content no longer stacks into one flat scroll. Every action is
 * capability-gated by what the backend says this actor may do.
 */
export function AssetInspector({
  asset,
  versions,
  collections,
  busy,
  onClose,
  onAdopt,
  onRestore,
  onTogglePin,
  onToggleAlwaysOn,
  onSetRevealAfter,
  onToggleCollection,
}: {
  asset: CatalogAsset;
  versions: AssetVersion[] | null;
  collections: Collection[];
  busy: boolean;
  onClose: () => void;
  onAdopt: () => Promise<void>;
  onRestore: (versionNumber: number) => Promise<void>;
  onTogglePin: () => Promise<void>;
  onToggleAlwaysOn: () => Promise<void>;
  onSetRevealAfter: (chapterOrder: number | null) => Promise<void>;
  onToggleCollection: (collectionId: string, member: boolean) => Promise<void>;
}) {
  const type = presentType(asset.asset_type);
  const chip = lifecycleChip(asset.lifecycle);
  const candidate = isCandidate(asset.lifecycle);
  const canMutate = asset.capabilities.mutate;
  const canManageCollections = asset.capabilities.manage_collections;
  const memberOf = new Set(asset.collections.map((c) => c.collection_id));

  const [tab, setTab] = useState<InspectorTab>("summary");
  // Switching assets always lands back on the summary tab.
  useEffect(() => {
    setTab("summary");
  }, [asset.asset_id]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* header */}
      <div className="flex items-start gap-3 border-b border-line-soft px-5 py-4">
        <span className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-[10px] border border-line bg-paper text-accent">
          <type.icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[11.5px] font-medium tracking-wide text-muted">{type.label}</span>
            <span className={cn("rounded-full border px-2 py-px text-[11px] font-medium", chip.className)}>
              {chip.label}
            </span>
          </div>
          <h2 className="mt-1 break-words font-serif text-[19px] font-semibold leading-snug text-ink">
            {asset.title || "未命名资产"}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭详情"
          className="grid size-8 shrink-0 place-items-center rounded-[8px] text-muted transition-colors hover:bg-paper-deep hover:text-ink"
        >
          <X className="size-[17px]" aria-hidden />
        </button>
      </div>

      {/* pinned actions (always visible) */}
      <div className="space-y-3 border-b border-line-soft px-5 py-4">
        {candidate && canMutate ? <AdoptCard busy={busy} onAdopt={onAdopt} /> : null}
        {canMutate ? (
          <button
            type="button"
            onClick={() => void onTogglePin()}
            disabled={busy}
            className="flex h-9 w-full items-center justify-center gap-2 rounded-[10px] border border-line bg-panel text-[13px] font-medium text-ink shadow-sm transition-colors hover:border-accent/45 hover:text-accent disabled:opacity-50"
          >
            {asset.pinned ? (
              <>
                <PinOff className="size-[15px]" aria-hidden /> 取消置顶
              </>
            ) : (
              <>
                <Pin className="size-[15px]" aria-hidden /> 置顶这条资产
              </>
            )}
          </button>
        ) : null}
        {canMutate ? (
          <RecallControls
            alwaysOn={asset.always_on}
            revealAfter={asset.reveal_after_chapter_order}
            busy={busy}
            onToggleAlwaysOn={onToggleAlwaysOn}
            onSetRevealAfter={onSetRevealAfter}
          />
        ) : null}
      </div>

      {/* tabs */}
      <InspectorTabs
        active={tab}
        counts={{ versions: versions?.length ?? null, collections: memberOf.size }}
        onChange={setTab}
      />

      {/* tab panels */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: DUR.fast, ease: EASE }}
            className="space-y-5 px-5 py-5"
          >
            {tab === "summary" ? (
              <>
                {asset.summary ? (
                  <Section title="摘要">
                    <p className="text-[13.5px] leading-relaxed text-ink-soft">{asset.summary}</p>
                  </Section>
                ) : null}

                {asset.private?.content_text ? (
                  <Section title="正文">
                    <p className="whitespace-pre-wrap break-words font-serif text-[14px] leading-[1.85] text-ink">
                      {asset.private.content_text}
                    </p>
                  </Section>
                ) : null}

                <Section title="属性">
                  <dl className="space-y-2 text-[13px]">
                    <Field label="来源" value={presentSource(asset.source.kind)} />
                    {asset.category ? <Field label="分类" value={asset.category} /> : null}
                    <Field label="更新于" value={formatAssetDateTime(asset.updated_at)} />
                    <Field label="版本" value={`v${asset.current_version}`} />
                  </dl>
                  {asset.tags.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {asset.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full border border-line bg-paper px-2.5 py-0.5 text-[11.5px] text-muted"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </Section>
              </>
            ) : null}

            {tab === "versions" ? (
              <Section title={`版本历史${versions ? `（${versions.length}）` : ""}`} icon={History}>
                {versions === null ? (
                  <p className="text-[12.5px] text-muted">正在读取版本…</p>
                ) : versions.length === 0 ? (
                  <p className="text-[12.5px] text-muted">还没有历史版本。</p>
                ) : (
                  <ul className="space-y-1.5">
                    {versions.map((version) => {
                      const isCurrent = version.version_number === asset.current_version;
                      return (
                        <li
                          key={version.version_id}
                          className="flex items-center gap-2.5 rounded-[9px] border border-line-soft bg-paper/60 px-3 py-2"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-[12.5px] font-medium text-ink">
                              v{version.version_number}
                              {isCurrent ? <span className="ml-1.5 text-[11px] text-accent">当前</span> : null}
                            </p>
                            <p className="truncate text-[11.5px] text-muted">
                              {version.title || asset.title} · {formatAssetDateTime(version.created_at)}
                            </p>
                          </div>
                          {!isCurrent && canMutate ? (
                            <RestoreButton busy={busy} onRestore={() => onRestore(version.version_number)} />
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Section>
            ) : null}

            {tab === "collections" ? (
              <Section title="所属集合">
                {canManageCollections && collections.length > 0 ? (
                  <ul className="space-y-1.5">
                    {collections.map((collection) => {
                      const member = memberOf.has(collection.collection_id);
                      return (
                        <li key={collection.collection_id}>
                          <button
                            type="button"
                            onClick={() => void onToggleCollection(collection.collection_id, !member)}
                            disabled={busy}
                            aria-pressed={member}
                            className={cn(
                              "flex h-9 w-full items-center justify-between rounded-[9px] border px-3 text-[13px] transition-colors disabled:opacity-50",
                              member
                                ? "border-accent/40 bg-accent-wash text-accent-strong"
                                : "border-line bg-panel text-ink-soft hover:border-accent/35",
                            )}
                          >
                            <span className="truncate">{collection.title}</span>
                            <span className="text-[11.5px] text-muted">{member ? "已加入" : "加入"}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-[12.5px] text-muted">还没有可归入的集合。</p>
                )}
              </Section>
            ) : null}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function InspectorTabs({
  active,
  counts,
  onChange,
}: {
  active: InspectorTab;
  counts: { versions: number | null; collections: number };
  onChange: (tab: InspectorTab) => void;
}) {
  const tabs: { key: InspectorTab; label: string; count: number | null }[] = [
    { key: "summary", label: "摘要", count: null },
    { key: "versions", label: "版本", count: counts.versions },
    { key: "collections", label: "集合", count: counts.collections },
  ];
  return (
    <LayoutGroup id="asset-inspector-tabs">
      <div role="tablist" aria-label="资产详情" className="flex items-center gap-1 border-b border-line-soft px-4 py-2">
        {tabs.map((t) => {
          const selected = t.key === active;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(t.key)}
              className={cn(
                "relative flex items-center gap-1.5 rounded-[9px] px-3 py-1.5 text-[12.5px] font-medium transition-colors",
                selected ? "text-accent-strong" : "text-muted hover:text-ink",
              )}
            >
              {selected ? (
                <motion.span
                  layoutId="inspector-tab-pill"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  className="absolute inset-0 rounded-[9px] border border-accent/25 bg-accent-wash"
                />
              ) : null}
              <span className="relative z-10">{t.label}</span>
              {t.count !== null ? (
                <span
                  className={cn(
                    "relative z-10 rounded-full px-1.5 py-px text-[10.5px] tabular-nums",
                    selected ? "bg-panel text-accent-strong" : "bg-paper-deep/70 text-muted/80",
                  )}
                >
                  {t.count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}

function AdoptCard({ busy, onAdopt }: { busy: boolean; onAdopt: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="rounded-[12px] border border-gold/45 bg-gold/[0.07] p-4">
      <div className="flex items-start gap-2.5">
        <CheckCircle2 className="mt-0.5 size-[18px] shrink-0 text-[#8a6a33]" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-medium text-ink">这是一条候选资产</p>
          <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">
            采用后会写进故事正典，成为后续创作的正式依据。这个动作需要你明确确认。
          </p>
          {confirming ? (
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void onAdopt()}
                className="h-9 flex-1 rounded-[9px] bg-accent text-[13px] font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-50"
              >
                确认采用为正典
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirming(false)}
                className="h-9 rounded-[9px] border border-line bg-panel px-3.5 text-[13px] text-muted transition-colors hover:text-ink"
              >
                再想想
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="mt-3 h-9 rounded-[9px] border border-[#8a6a33]/40 bg-panel px-4 text-[13px] font-medium text-[#8a6a33] transition-colors hover:bg-gold/10"
            >
              采用为正典…
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Writer-recall controls (doc 41): constant injection (always_on) and the
 * spoiler gate (reveal_after_chapter_order). These are the two levers an author
 * pulls to decide whether an asset is always in the writing context, and from
 * which chapter onward recall may see it at all.
 */
function RecallControls({
  alwaysOn,
  revealAfter,
  busy,
  onToggleAlwaysOn,
  onSetRevealAfter,
}: {
  alwaysOn: boolean;
  revealAfter: number | null;
  busy: boolean;
  onToggleAlwaysOn: () => Promise<void>;
  onSetRevealAfter: (chapterOrder: number | null) => Promise<void>;
}) {
  const gated = revealAfter !== null;
  const [order, setOrder] = useState<string>(revealAfter === null ? "" : String(revealAfter));
  // Re-sync the field when a different asset (or a fresh value) loads.
  useEffect(() => {
    setOrder(revealAfter === null ? "" : String(revealAfter));
  }, [revealAfter]);

  const commitOrder = (raw: string) => {
    const trimmed = raw.trim();
    if (trimmed === "") {
      void onSetRevealAfter(null);
      return;
    }
    const parsed = Number.parseInt(trimmed, 10);
    if (Number.isInteger(parsed) && parsed >= 0) {
      void onSetRevealAfter(parsed);
    }
  };

  return (
    <div className="space-y-2.5 rounded-[10px] border border-line-soft bg-paper/50 px-3.5 py-3">
      <p className="text-[11px] font-medium tracking-[0.14em] text-muted">写作召回</p>

      {/* always_on: constant injection into every run */}
      <button
        type="button"
        onClick={() => void onToggleAlwaysOn()}
        disabled={busy}
        aria-pressed={alwaysOn}
        className={cn(
          "flex h-9 w-full items-center justify-between rounded-[9px] border px-3 text-[12.5px] transition-colors disabled:opacity-50",
          alwaysOn
            ? "border-gold/50 bg-gold/10 text-ink"
            : "border-line bg-panel text-ink-soft hover:border-accent/35",
        )}
      >
        <span className="flex items-center gap-2">
          <Sparkles className="size-[14px] shrink-0" aria-hidden />
          常驻设定 · 每次写作都在场
        </span>
        <span className={cn("text-[11px]", alwaysOn ? "text-[#8a6a33]" : "text-muted")}>
          {alwaysOn ? "已开启" : "关闭"}
        </span>
      </button>

      {/* spoiler gate: hidden from recall until a chapter */}
      <div className="flex items-center gap-2">
        <EyeOff className="size-[14px] shrink-0 text-muted" aria-hidden />
        <label htmlFor="reveal-after" className="flex-1 text-[12.5px] text-ink-soft">
          第几章后才允许召回
        </label>
        <input
          id="reveal-after"
          type="number"
          min={0}
          inputMode="numeric"
          placeholder="不限制"
          value={order}
          disabled={busy}
          onChange={(e) => setOrder(e.target.value)}
          onBlur={(e) => commitOrder(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
          className="h-8 w-20 rounded-[8px] border border-line bg-panel px-2 text-right text-[12.5px] text-ink tabular-nums placeholder:text-muted/70 focus:border-accent/50 focus:outline-none disabled:opacity-50"
        />
      </div>
      <p className="text-[11px] leading-relaxed text-muted">
        {gated
          ? `写作到第 ${revealAfter} 章前，这条对召回隐藏（防剧透）。清空则恢复始终可见。`
          : "留空表示始终可见；填章节号则在写到该章前对召回隐藏。"}
      </p>
    </div>
  );
}

function RestoreButton({ busy, onRestore }: { busy: boolean; onRestore: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  if (confirming) {
    return (
      <span className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          disabled={busy}
          onClick={() => void onRestore()}
          className="rounded-[7px] bg-accent px-2.5 py-1 text-[11.5px] font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-50"
        >
          确认
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => setConfirming(false)}
          className="rounded-[7px] border border-line px-2 py-1 text-[11.5px] text-muted hover:text-ink"
        >
          取消
        </button>
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={() => setConfirming(true)}
      disabled={busy}
      aria-label="恢复到此版本"
      className="grid size-7 shrink-0 place-items-center rounded-[7px] text-muted transition-colors hover:bg-paper-deep hover:text-accent disabled:opacity-50"
    >
      <RotateCcw className="size-[14px]" aria-hidden />
    </button>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon?: typeof History;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-2 flex items-center gap-1.5 text-[11.5px] font-medium tracking-[0.18em] text-muted">
        {Icon ? <Icon className="size-[13px]" aria-hidden /> : null}
        {title}
      </h3>
      {children}
    </section>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 truncate text-ink-soft">{value}</dd>
    </div>
  );
}
