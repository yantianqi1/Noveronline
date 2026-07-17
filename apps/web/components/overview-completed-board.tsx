"use client";

import { ChevronRight, X } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { Bi } from "./bilingual-text";

export type OverviewCompletedBoardCard = {
  id: string;
  icon: ReactNode;
  title: ReactNode;
  subtitle: ReactNode;
  body: ReactNode;
};

type OverviewCompletedBoardProps = {
  cards: OverviewCompletedBoardCard[];
  /** Restored from ?board= after navigation so file preview keeps the modal open. */
  initialActiveId?: string | null;
};

function resolveActiveId(
  cards: OverviewCompletedBoardCard[],
  candidate: string | null | undefined,
) {
  if (!candidate) {
    return null;
  }
  return cards.some((card) => card.id === candidate) ? candidate : null;
}

/**
 * Completed-overview peer cards open a modal instead of expanding the page.
 * Keeps the 2×2 board geometry stable while reviewing details.
 * Active card is mirrored to ?board= so in-modal navigations (workspace files) remount with the dialog open.
 */
export function OverviewCompletedBoard({
  cards,
  initialActiveId = null,
}: OverviewCompletedBoardProps) {
  const router = useRouter();
  const [activeId, setActiveId] = useState<string | null>(() =>
    resolveActiveId(cards, initialActiveId),
  );
  const [mounted, setMounted] = useState(false);
  const titleId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const lastInitialActiveId = useRef(initialActiveId);

  const activeCard = cards.find((card) => card.id === activeId) ?? null;

  useEffect(() => {
    setMounted(true);
  }, []);

  // Only follow server ?board= when that param actually changes (e.g. back/forward), not on every parent render.
  useEffect(() => {
    if (lastInitialActiveId.current === initialActiveId) {
      return;
    }
    lastInitialActiveId.current = initialActiveId;
    setActiveId(resolveActiveId(cards, initialActiveId));
  }, [cards, initialActiveId]);

  useEffect(() => {
    if (!mounted) {
      return;
    }
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (activeCard) {
      if (!dialog.open) {
        dialog.showModal();
      }
      closeRef.current?.focus();
      return;
    }
    if (dialog.open) {
      dialog.close();
    }
  }, [activeCard, mounted]);

  function syncBoardQuery(boardId: string | null) {
    if (typeof window === "undefined") {
      return;
    }
    const url = new URL(window.location.href);
    if (boardId) {
      url.searchParams.set("board", boardId);
    } else {
      url.searchParams.delete("board");
      url.searchParams.delete("workspacePath");
    }
    const next = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState(window.history.state, "", next);
    router.replace(next, { scroll: false });
  }

  function openCard(cardId: string) {
    setActiveId(cardId);
    syncBoardQuery(cardId);
  }

  function closeDialog() {
    const previousId = activeId;
    setActiveId(null);
    syncBoardQuery(null);
    if (previousId) {
      triggerRefs.current[previousId]?.focus();
    }
  }

  const dialogNode = (
    <dialog
      aria-labelledby={titleId}
      className="overview-board-dialog"
      data-surface="paper"
      onCancel={(event) => {
        event.preventDefault();
        closeDialog();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          closeDialog();
        }
      }}
      ref={dialogRef}
    >
      {activeCard ? (
        <>
          <div className="overview-board-dialog-header">
            <div className="overview-board-dialog-heading">
              <span className="overview-board-dialog-icon" aria-hidden="true">
                {activeCard.icon}
              </span>
              <div>
                <h2 id={titleId}>{activeCard.title}</h2>
                <p>{activeCard.subtitle}</p>
              </div>
            </div>
            <button
              aria-label="Close"
              className="overview-board-dialog-close"
              onClick={() => closeDialog()}
              ref={closeRef}
              type="button"
            >
              <X aria-hidden="true" size={18} strokeWidth={1.8} />
              <span><Bi zh="关闭" en="Close" /></span>
            </button>
          </div>
          <div className="overview-board-dialog-body">{activeCard.body}</div>
        </>
      ) : null}
    </dialog>
  );

  return (
    <div className="overview-completed-board" data-board="completed-disclosures" data-interaction="modal">
      {cards.map((card) => (
        <button
          aria-haspopup="dialog"
          aria-expanded={activeId === card.id}
          className="overview-board-card"
          data-active={activeId === card.id ? "true" : "false"}
          key={card.id}
          onClick={() => openCard(card.id)}
          ref={(node) => {
            triggerRefs.current[card.id] = node;
          }}
          type="button"
        >
          <span className="overview-board-card-icon" aria-hidden="true">
            {card.icon}
          </span>
          <span className="overview-board-card-copy">
            <strong>{card.title}</strong>
            <small>{card.subtitle}</small>
          </span>
          <ChevronRight className="overview-board-card-chevron" aria-hidden="true" size={18} />
        </button>
      ))}
      {mounted ? createPortal(dialogNode, document.body) : null}
    </div>
  );
}
