"use client";

import { useEffect, useRef, useState } from "react";

import type { Chapter, ManuscriptBlock } from "@/lib/api/writer-types";

/** A live selection inside one manuscript segment, surfaced for the action bar. */
export type PaperSelection = {
  blockId: string;
  /** The exact highlighted text (textarea selection, display coordinates). */
  text: string;
  /** Viewport coordinates of the selection, so the bar can float beside it. */
  rect: { left: number; top: number; bottom: number; width: number };
};

/** The quick co-writer actions offered on a text selection. */
export type SelectionActionKind = "rewrite" | "continue" | "polish" | "expand";

const SELECTION_ACTIONS: ReadonlyArray<{ kind: SelectionActionKind; label: string }> = [
  { kind: "rewrite", label: "改写" },
  { kind: "continue", label: "续写" },
  { kind: "polish", label: "润色" },
  { kind: "expand", label: "扩写" },
];

/**
 * The manuscript paper — the dominant artifact surface, typeset as a book
 * page: a centred running head (eyebrow chapter label + serif title + rule
 * ornament), the chapter's blocks flowing as one continuous reading column
 * (664px book measure, `text-reading` 17px/1.85, 2em paragraph indent,
 * justified), and a quiet folio footer. Blocks stay independently editable in
 * place; adopted candidate prose lands as the newest trailing page.
 *
 * Agent drafts often open with a literal markdown `# 第一章` line. The paper
 * lifts that line out of the first block in the DISPLAY LAYER ONLY and sets it
 * as the running head — the stored text keeps its markdown untouched, and the
 * block's edits are re-joined under the original heading before autosave. The
 * rail's 查看正文 scrolls a segment into view and pulses it once, so the author
 * can see exactly where adopted prose landed.
 */
export function ManuscriptPaper({
  chapter,
  segments,
  onChangeSegment,
  readOnly,
  revealBlockId,
  onRevealConsumed,
  onSelectionAction,
}: {
  chapter: Chapter | null;
  segments: ManuscriptBlock[];
  onChangeSegment: (blockId: string, next: string) => void;
  readOnly: boolean;
  /** Block to scroll to and pulse once (from the rail's 查看正文). */
  revealBlockId?: string | null;
  onRevealConsumed?: () => void;
  /** Fires when the author picks a quick action on a text selection. */
  onSelectionAction?: (action: SelectionActionKind, selection: PaperSelection) => void;
}) {
  const leadHeading =
    segments.length > 0 ? splitLeadingHeading(segments[0].content_text).heading : null;
  const chapterLabel = chapter?.title.trim() ? chapter.title.trim() : null;
  const wordCount = segments.reduce(
    (sum, segment) => sum + segment.content_text.replace(/\s/g, "").length,
    0,
  );

  // The live in-page selection that the floating action bar is anchored to.
  // Cleared when the author collapses the caret, switches chapter, or starts
  // editing; re-armed on the next highlight.
  const [selection, setSelection] = useState<PaperSelection | null>(null);
  const paperRef = useRef<HTMLDivElement | null>(null);

  function handleSelect(sel: PaperSelection | null) {
    setSelection(sel);
  }

  function handleAction(kind: SelectionActionKind) {
    if (!selection || !onSelectionAction) return;
    onSelectionAction(kind, selection);
    setSelection(null);
  }

  return (
    <div ref={paperRef} className="relative flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[664px] px-6 pb-8 pt-11">
        <RunningHead
          title={leadHeading ?? chapterLabel}
          eyebrow={
            leadHeading && chapterLabel && chapterLabel !== leadHeading ? chapterLabel : null
          }
        />

        {segments.length === 0 ? (
          readOnly ? (
            <p className="font-serif text-reading text-muted-soft">
              这一章还空着。回到书架重新进入项目后，就能在这里落笔。
            </p>
          ) : (
            <EmptyFirstSegment onChange={(text) => onChangeSegment("__first__", text)} />
          )
        ) : (
          <div className="flex flex-col">
            {segments.map((segment, index) => (
              <SegmentEditor
                key={segment.block_id}
                segment={segment}
                isFirst={index === 0}
                onChange={(text) => onChangeSegment(segment.block_id, text)}
                readOnly={readOnly}
                reveal={revealBlockId === segment.block_id}
                onRevealConsumed={onRevealConsumed}
                onSelect={readOnly || !onSelectionAction ? undefined : handleSelect}
              />
            ))}
          </div>
        )}

        <PageFoot chapterLabel={chapterLabel} wordCount={wordCount} />
      </div>

      {selection && onSelectionAction ? (
        <SelectionActionBar selection={selection} onAction={handleAction} onDismiss={() => setSelection(null)} />
      ) : null}
    </div>
  );
}

/** Chapter running head: folio-level eyebrow + serif title + double-rule ornament. */
function RunningHead({ title, eyebrow }: { title: string | null; eyebrow: string | null }) {
  if (!title) return null;
  return (
    <header className="mb-8 text-center">
      {eyebrow ? <p className="text-micro tracking-label text-muted">{eyebrow}</p> : null}
      <h1 className="mt-2.5 font-serif text-display font-bold text-ink">{title}</h1>
      <div className="mt-4 flex items-center justify-center gap-3" aria-hidden>
        <span className="h-px w-13 bg-line" />
        <span className="size-[7px] rotate-45 bg-accent" />
        <span className="h-px w-13 bg-line" />
      </div>
    </header>
  );
}

/** Book folio footer: chapter · word count · autosave note, winged by hairlines. */
function PageFoot({ chapterLabel, wordCount }: { chapterLabel: string | null; wordCount: number }) {
  const parts = [
    chapterLabel,
    wordCount > 0 ? `共 ${wordCount} 字` : "尚未落笔",
    "稿纸自动留痕",
  ].filter(Boolean);
  return (
    <footer className="mt-12 flex items-center justify-center gap-3.5 text-micro tracking-label text-muted">
      <span className="h-px w-16 bg-line-soft" aria-hidden />
      <span>{parts.join(" · ")}</span>
      <span className="h-px w-16 bg-line-soft" aria-hidden />
    </footer>
  );
}

/**
 * Lift a leading markdown `# ` line out of a block's text. `prefix` is the
 * exact heading line plus its trailing blank lines, so `prefix + body` stays
 * byte-identical to the stored text.
 */
function splitLeadingHeading(text: string): { heading: string | null; prefix: string; body: string } {
  const match = /^#[ \t]+([^\n]*?)[ \t\r]*(\n+|$)/.exec(text);
  if (!match || !match[1]) return { heading: null, prefix: "", body: text };
  return { heading: match[1], prefix: match[0], body: text.slice(match[0].length) };
}

/** Re-join an edited body under its lifted heading (one blank line after `# …`). */
function joinUnderHeading(prefix: string, next: string): string {
  return next && !prefix.endsWith("\n") ? `${prefix}\n\n${next}` : prefix + next;
}

/** One editable paragraph-block within the continuous sheet. */
function SegmentEditor({
  segment,
  isFirst,
  onChange,
  readOnly,
  reveal,
  onRevealConsumed,
  onSelect,
}: {
  segment: ManuscriptBlock;
  isFirst: boolean;
  onChange: (next: string) => void;
  readOnly: boolean;
  reveal: boolean;
  onRevealConsumed?: () => void;
  onSelect?: (sel: PaperSelection | null) => void;
}) {
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [flash, setFlash] = useState(false);
  // A leading `# 第一章` in the first block is set as the page's running head;
  // this textarea edits only the body beneath it (the heading line stays in
  // the stored text, re-attached on every change).
  const lead = isFirst ? splitLeadingHeading(segment.content_text) : null;

  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    area.style.height = "0px";
    area.style.height = `${Math.max(area.scrollHeight, 48)}px`;
  }, [segment.content_text]);

  // The rail asked to reveal this segment: scroll it into view and pulse the
  // surface once, then hand the token back so it can fire again later. The
  // flash arm is deferred past mount so the transparent → wash change is a
  // real transition, not a same-tick style commit the browser would coalesce.
  useEffect(() => {
    if (!reveal) return;
    wrapRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    const arm = setTimeout(() => setFlash(true), 60);
    const timer = setTimeout(() => {
      setFlash(false);
      onRevealConsumed?.();
    }, 1900);
    return () => {
      clearTimeout(arm);
      clearTimeout(timer);
    };
  }, [reveal, onRevealConsumed]);

  // Surface a non-collapsed selection to the paper so it can float the action
  // bar. Fires on mouse-up (drag select), key-up (shift-select), and select.
  // A collapsed caret reports null so the bar tucks away.
  function reportSelection() {
    if (!onSelect) return;
    const area = areaRef.current;
    if (!area) return;
    const { selectionStart, selectionEnd } = area;
    if (selectionEnd <= selectionStart) {
      onSelect(null);
      return;
    }
    const text = area.value.slice(selectionStart, selectionEnd);
    if (!text.trim()) {
      onSelect(null);
      return;
    }
    const rect = measureSelectionRect(area, selectionStart, selectionEnd);
    onSelect({ blockId: segment.block_id, text, rect });
  }

  return (
    <div
      ref={wrapRef}
      style={{
        backgroundColor: flash ? "rgba(143, 33, 27, 0.10)" : "transparent",
        boxShadow: flash ? "0 0 0 6px rgba(143, 33, 27, 0.07)" : "none",
        transition: "background-color 480ms ease, box-shadow 480ms ease",
      }}
      className={`rounded-control ${isFirst ? "" : "mt-1"}`}
    >
      <textarea
        ref={areaRef}
        value={lead ? lead.body : segment.content_text}
        onChange={(event) =>
          onChange(lead ? joinUnderHeading(lead.prefix, event.target.value) : event.target.value)
        }
        onMouseUp={reportSelection}
        onKeyUp={(event) => {
          if (event.shiftKey || event.key.startsWith("Arrow")) reportSelection();
        }}
        onBlur={() => onSelect?.(null)}
        readOnly={readOnly}
        placeholder={isFirst ? "从这里开始写。空白的稿纸，等第一个字落下。" : "接着写——"}
        aria-label={`手稿第 ${segment.block_order} 段`}
        rows={2}
        className="block w-full resize-none overflow-hidden bg-transparent font-serif text-reading text-ink caret-accent indent-[2em] text-justify placeholder:text-muted-soft focus:outline-none"
      />
    </div>
  );
}

/** When the chapter has no segments yet, a single starting sheet. */
function EmptyFirstSegment({ onChange }: { onChange: (text: string) => void }) {
  // Editing a chapter with no block yet is handled by the parent creating a
  // block; here we just show the invitation (parent auto-creates on 新章节).
  return (
    <p className="font-serif text-reading text-muted-soft">
      这一章还空着。点上方「新章节」或在左侧让合著者起草第一段。
    </p>
  );
}

/**
 * The floating quick-action bar shown next to a highlighted passage. It floats
 * fixed over the page (viewport coords), centred on the selection's first
 * line, and offers the four co-writer verbs. Clicking one hands the action +
 * the exact selected text to the workspace, which builds the run instruction.
 */
function SelectionActionBar({
  selection,
  onAction,
  onDismiss,
}: {
  selection: PaperSelection;
  onAction: (kind: SelectionActionKind) => void;
  onDismiss: () => void;
}) {
  const barRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  // Position above the selection's first line, clamped into the viewport; fall
  // below when there's no headroom. Measured after mount so we know our width.
  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const barWidth = bar.offsetWidth;
    const barHeight = bar.offsetHeight;
    const margin = 8;
    let left = selection.rect.left + selection.rect.width / 2 - barWidth / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - barWidth - margin));
    let top = selection.rect.top - barHeight - 10;
    if (top < margin) top = selection.rect.bottom + 10;
    setPos({ left, top });
  }, [selection]);

  // Dismiss on Escape or any pointer press outside the bar (but not on the
  // selection itself — that re-reports a fresh selection).
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onDismiss();
    }
    function onPointer(event: PointerEvent) {
      if (barRef.current && !barRef.current.contains(event.target as Node)) {
        // Let the textarea's own mouseup re-report first; only dismiss when the
        // press landed somewhere that isn't another selection surface.
        const target = event.target as HTMLElement;
        if (target.tagName !== "TEXTAREA") onDismiss();
      }
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [onDismiss]);

  return (
    <div
      ref={barRef}
      role="toolbar"
      aria-label="选中文字操作"
      style={{
        position: "fixed",
        left: pos ? pos.left : selection.rect.left,
        top: pos ? pos.top : selection.rect.top - 44,
        visibility: pos ? "visible" : "hidden",
      }}
      className="z-50 flex items-center gap-0.5 rounded-panel border border-line bg-panel p-1 shadow-hairline"
    >
      {SELECTION_ACTIONS.map(({ kind, label }) => (
        <button
          key={kind}
          type="button"
          onClick={() => onAction(kind)}
          className="rounded-control px-2.5 py-1.5 text-caption font-medium text-ink transition-colors hover:bg-accent-wash hover:text-accent"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/**
 * Approximate the viewport rect of a textarea selection. A textarea has no
 * native per-character rects, so we mirror its text into a hidden div with
 * identical typography and read the offset of a marker span placed at the
 * selection start. Width uses the first selected line; that's enough to centre
 * the bar.
 */
function measureSelectionRect(
  area: HTMLTextAreaElement,
  start: number,
  end: number,
): PaperSelection["rect"] {
  const style = window.getComputedStyle(area);
  const mirror = document.createElement("div");
  const properties = [
    "boxSizing",
    "width",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "borderTopWidth",
    "borderRightWidth",
    "borderBottomWidth",
    "borderLeftWidth",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "lineHeight",
    "letterSpacing",
    "textIndent",
    "textAlign",
    "whiteSpace",
    "overflowWrap",
    "wordBreak",
  ] as const;
  for (const prop of properties) {
    mirror.style.setProperty(
      prop.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`),
      style.getPropertyValue(prop.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)),
    );
  }
  mirror.style.position = "absolute";
  mirror.style.visibility = "hidden";
  mirror.style.whiteSpace = "pre-wrap";
  mirror.style.overflowWrap = "break-word";
  mirror.style.top = "0";
  mirror.style.left = "-9999px";

  const before = area.value.slice(0, start);
  const selected = area.value.slice(start, end);
  mirror.textContent = before;
  const marker = document.createElement("span");
  // Measure only the first selected line for the bar's anchor width.
  const firstLine = selected.split("\n", 1)[0] || "　";
  marker.textContent = firstLine;
  mirror.appendChild(marker);
  document.body.appendChild(mirror);

  const areaRect = area.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const mirrorRect = mirror.getBoundingClientRect();
  document.body.removeChild(mirror);

  // The marker's offset inside the mirror, transposed onto the textarea's box
  // (minus scroll, though these textareas don't scroll — they grow).
  const left = areaRect.left + (markerRect.left - mirrorRect.left) - area.scrollLeft;
  const top = areaRect.top + (markerRect.top - mirrorRect.top) - area.scrollTop;
  const lineHeight = parseFloat(style.lineHeight) || markerRect.height || 24;
  return {
    left,
    top,
    bottom: top + Math.max(markerRect.height, lineHeight),
    width: markerRect.width,
  };
}
