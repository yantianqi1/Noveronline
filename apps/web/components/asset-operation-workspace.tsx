"use client";

import {
  ArchiveRestore,
  Boxes,
  FileInput,
  ListChecks,
  MessageSquare,
  PencilLine,
  Plus,
  SearchCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export type AssetOperationItem = {
  id: "create" | "update" | "delete" | "adopt" | "bulk" | "ingest" | "reindex" | "style";
  title: ReactNode;
  description: ReactNode;
  content: ReactNode;
  tone?: "default" | "danger";
};

type AssetOperationWorkspaceProps = {
  items: AssetOperationItem[];
  title: ReactNode;
  description: ReactNode;
  openLabel: ReactNode;
  /** Label for secondary “more operations” control. */
  moreLabel?: ReactNode;
  /** Operation opened by the primary button. Defaults to create when present. */
  primaryId?: AssetOperationItem["id"];
  /** `toolbar` hides the card heading and renders a compact action cluster. */
  variant?: "card" | "toolbar";
};

const operationIcons = {
  create: Plus,
  update: PencilLine,
  delete: Trash2,
  adopt: ArchiveRestore,
  bulk: ListChecks,
  ingest: FileInput,
  reindex: SearchCheck,
  style: Sparkles,
};

export function AssetOperationWorkspace({
  description,
  items,
  moreLabel,
  openLabel,
  primaryId = "create",
  title,
  variant = "card",
}: AssetOperationWorkspaceProps) {
  const [activeId, setActiveId] = useState<AssetOperationItem["id"] | null>(null);
  const [mounted, setMounted] = useState(false);
  const activeItem = useMemo(() => items.find((item) => item.id === activeId) ?? null, [activeId, items]);
  const primaryItem = useMemo(
    () => items.find((item) => item.id === primaryId) ?? items[0] ?? null,
    [items, primaryId],
  );
  const secondaryItems = useMemo(
    () => items.filter((item) => item.id !== primaryItem?.id),
    [items, primaryItem],
  );
  const isToolbar = variant === "toolbar";

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!activeItem) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActiveId(null);
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [activeItem]);

  return (
    <section
      className="asset-command-center"
      data-variant={variant}
      aria-labelledby={isToolbar ? undefined : "asset-command-center-title"}
    >
      {!isToolbar ? (
        <div className="asset-command-heading">
          <span className="asset-command-icon" aria-hidden="true"><Boxes size={20} strokeWidth={1.7} /></span>
          <span>
            <strong id="asset-command-center-title">{title}</strong>
            <small>{description}</small>
          </span>
        </div>
      ) : null}
      <div className="asset-command-actions">
        <button
          className="asset-command-launch"
          data-tone="primary"
          disabled={!primaryItem}
          onClick={() => setActiveId(primaryItem?.id ?? null)}
          type="button"
        >
          <Plus aria-hidden="true" size={18} strokeWidth={1.7} />
          <span>{openLabel}</span>
        </button>
        {secondaryItems.length > 0 ? (
          <button
            className="asset-command-more"
            data-tone="secondary"
            onClick={() => setActiveId(secondaryItems[0]?.id ?? null)}
            type="button"
          >
            <MessageSquare aria-hidden="true" size={16} strokeWidth={1.7} />
            <span>{moreLabel ?? "More"}</span>
          </button>
        ) : null}
      </div>

      {activeItem && mounted ? createPortal((
        <div className="asset-workspace-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) {
            setActiveId(null);
          }
        }}>
          <section
            aria-labelledby="asset-workspace-title"
            aria-modal="true"
            className="asset-workspace-dialog"
            data-tone={activeItem.tone ?? "default"}
            role="dialog"
          >
            <header className="asset-workspace-header">
              <span>
                <small>{description}</small>
                <strong id="asset-workspace-title">{activeItem.title}</strong>
                <span>{activeItem.description}</span>
              </span>
              <button
                aria-label="关闭资产操作 / Close asset operation"
                className="asset-workspace-close"
                onClick={() => setActiveId(null)}
                title="关闭 / Close"
                type="button"
              >
                <X aria-hidden="true" size={21} />
              </button>
            </header>
            <div className="asset-workspace-layout">
              <nav className="asset-workspace-nav" aria-label="资产操作 / Asset operations">
                {items.map((item) => {
                  const Icon = operationIcons[item.id];
                  return (
                    <button
                      aria-current={item.id === activeItem.id ? "page" : undefined}
                      data-tone={item.tone ?? "default"}
                      key={item.id}
                      onClick={() => setActiveId(item.id)}
                      type="button"
                    >
                      <Icon aria-hidden="true" size={17} />
                      <span>{item.title}</span>
                    </button>
                  );
                })}
              </nav>
              <div className="asset-workspace-content">{activeItem.content}</div>
            </div>
          </section>
        </div>
      ), document.body) : null}
    </section>
  );
}
