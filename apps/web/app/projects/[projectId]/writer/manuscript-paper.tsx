"use client";

import { useEffect, useRef, useState } from "react";

import type { Chapter, ManuscriptBlock } from "@/lib/api/writer-types";

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
}: {
  chapter: Chapter | null;
  segments: ManuscriptBlock[];
  onChangeSegment: (blockId: string, next: string) => void;
  readOnly: boolean;
  /** Block to scroll to and pulse once (from the rail's 查看正文). */
  revealBlockId?: string | null;
  onRevealConsumed?: () => void;
}) {
  const leadHeading =
    segments.length > 0 ? splitLeadingHeading(segments[0].content_text).heading : null;
  const chapterLabel = chapter?.title.trim() ? chapter.title.trim() : null;
  const wordCount = segments.reduce(
    (sum, segment) => sum + segment.content_text.replace(/\s/g, "").length,
    0,
  );

  return (
    <div className="flex-1 overflow-y-auto">
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
              />
            ))}
          </div>
        )}

        <PageFoot chapterLabel={chapterLabel} wordCount={wordCount} />
      </div>
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
}: {
  segment: ManuscriptBlock;
  isFirst: boolean;
  onChange: (next: string) => void;
  readOnly: boolean;
  reveal: boolean;
  onRevealConsumed?: () => void;
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
