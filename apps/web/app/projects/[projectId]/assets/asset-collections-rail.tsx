"use client";

import { FolderOpen, Layers, Plus } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";
import type { Collection } from "@/lib/api/asset-types";

/**
 * The collections rail: a quiet way to organize assets into named sets
 * (角色卡、设定集…). Selecting a collection filters the list to its members.
 * Creating a set is a small inline form; destructive delete lives on the
 * inspector, not here, to keep this rail light.
 */
export function AssetCollectionsRail({
  collections,
  activeCollectionId,
  canManage,
  onSelect,
  onCreate,
}: {
  collections: Collection[];
  activeCollectionId: string | null;
  canManage: boolean;
  onSelect: (collectionId: string | null) => void;
  onCreate: (title: string) => Promise<void>;
}) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onCreate(trimmed);
      setTitle("");
      setCreating(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="hidden w-[218px] shrink-0 flex-col overflow-y-auto border-r border-line-soft py-5 lg:flex">
      <p className="px-6 pb-2 text-[11.5px] font-medium tracking-[0.22em] text-muted">
        集合
      </p>
      <nav aria-label="资产集合" className="flex flex-col gap-0.5 px-3">
        <RailItem
          icon={Layers}
          label="全部资产"
          active={activeCollectionId === null}
          onClick={() => onSelect(null)}
        />
        {collections.map((collection) => (
          <RailItem
            key={collection.collection_id}
            icon={FolderOpen}
            label={collection.title}
            count={collection.items.length}
            active={activeCollectionId === collection.collection_id}
            onClick={() =>
              onSelect(activeCollectionId === collection.collection_id ? null : collection.collection_id)
            }
          />
        ))}
      </nav>

      {canManage ? (
        <div className="mt-3 px-3">
          {creating ? (
            <form
              className="flex flex-col gap-2 rounded-[10px] border border-line bg-panel p-2.5"
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <input
                autoFocus
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="集合名称，如「主要角色」"
                aria-label="新集合名称"
                className="h-9 rounded-[8px] border border-line bg-panel px-2.5 text-[13px] text-ink outline-none placeholder:text-muted/60 focus:border-accent/50 focus:ring-2 focus:ring-accent/15"
              />
              <div className="flex gap-1.5">
                <button
                  type="submit"
                  disabled={!title.trim() || busy}
                  className="h-8 flex-1 rounded-[8px] bg-accent text-[12.5px] font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-50"
                >
                  新建
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setTitle("");
                  }}
                  className="h-8 rounded-[8px] border border-line px-3 text-[12.5px] text-muted transition-colors hover:text-ink"
                >
                  取消
                </button>
              </div>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="flex h-9 w-full items-center gap-2 rounded-[10px] border border-dashed border-line px-3.5 text-[13px] text-muted transition-colors hover:border-accent/45 hover:text-accent"
            >
              <Plus className="size-[15px]" aria-hidden />
              新建集合
            </button>
          )}
        </div>
      ) : null}
    </aside>
  );
}

function RailItem({
  icon: Icon,
  label,
  count,
  active,
  onClick,
}: {
  icon: typeof Layers;
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "true" : undefined}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-[10px] px-3 py-2.5 text-left text-[13.5px] transition-colors duration-200",
        active ? "bg-accent-wash font-medium text-accent-strong" : "text-ink-soft hover:bg-paper-deep hover:text-ink",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "absolute left-0 top-1/2 h-[16px] w-[3px] -translate-y-1/2 rounded-full bg-accent transition-opacity duration-200",
          active ? "opacity-100" : "opacity-0",
        )}
      />
      <Icon
        className={cn("size-[16px] shrink-0", active ? "text-accent" : "text-muted group-hover:text-ink")}
        aria-hidden
      />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {typeof count === "number" ? (
        <span className="shrink-0 text-[11.5px] tabular-nums text-muted">{count}</span>
      ) : null}
    </button>
  );
}
