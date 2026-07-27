"use client";

import { useEffect, useRef, useState } from "react";

import type { Chapter, ManuscriptBlock } from "@/lib/api/writer-types";

/**
 * The manuscript paper — the dominant artifact surface. A chapter renders as
 * one continuous warm sheet: its manuscript blocks flow in block_order as an
 * unbroken reading column, each independently editable in place. Adopted
 * candidate prose lands as the newest trailing page, so the author always sees
 * the whole chapter, not a single card. Serif body, generous 1.9 line-height,
 * ~680px measure. The rail's 查看正文 scrolls a segment into view and pulses
 * it once, so the author can see exactly where adopted prose landed.
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
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[760px] px-6 pb-10 pt-5">
        {/* Chapter heading on the sheet */}
        <header className="mx-auto max-w-[680px]">
          <p className="text-caption tracking-label text-muted">手稿</p>
          <h1 className="mt-1 font-serif text-xl font-semibold leading-snug text-ink">
            {chapter ? chapter.title : "未命名章节"}
          </h1>
          <div aria-hidden className="mt-3 h-px w-16 bg-gold/60" />
        </header>

        {/* The continuous sheet */}
        <div className="mt-5 rounded-control border border-line-soft bg-panel px-10 py-9 shadow-panel sm:px-14 sm:py-12">
          {segments.length === 0 ? (
            readOnly ? (
              <p className="font-serif text-md text-muted-soft">
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
        </div>

        <p className="mx-auto mt-4 max-w-[680px] text-caption leading-relaxed text-muted-soft">
          你写的每一个字都会自动存入手稿。让人工智能合著者起草的内容永远是「候选稿」，经你明确采用后才会进到这张稿纸上。
        </p>
      </div>
    </div>
  );
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
      className={`rounded-control ${isFirst ? "" : "mt-6 border-t border-line-soft/70 pt-6"}`}
    >
      <textarea
        ref={areaRef}
        value={segment.content_text}
        onChange={(event) => onChange(event.target.value)}
        readOnly={readOnly}
        placeholder={isFirst ? "从这里开始写。空白的稿纸，等第一个字落下。" : "接着写…"}
        aria-label={`手稿第 ${segment.block_order} 段`}
        rows={2}
        className="block w-full resize-none overflow-hidden bg-transparent font-serif text-lg text-ink placeholder:text-muted-soft focus:outline-none"
      />
    </div>
  );
}

/** When the chapter has no segments yet, a single starting sheet. */
function EmptyFirstSegment({ onChange }: { onChange: (text: string) => void }) {
  // Editing a chapter with no block yet is handled by the parent creating a
  // block; here we just show the invitation (parent auto-creates on 新章节).
  return (
    <p className="font-serif text-md text-muted-soft">
      这一章还空着。点上方「新章节」或在左侧让合著者起草第一段。
    </p>
  );
}
