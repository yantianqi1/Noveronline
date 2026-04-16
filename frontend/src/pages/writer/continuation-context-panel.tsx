/**
 * ContinuationContextPanel — shows continuation context (tail text, recent summaries, threads).
 */

import * as React from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ContinuationCtx } from "./use-writer-state";

interface ContinuationContextPanelProps {
  context: ContinuationCtx;
}

export function ContinuationContextPanel({ context }: ContinuationContextPanelProps) {
  const [collapsed, setCollapsed] = React.useState(true);

  const hasContent =
    (context.recent_summaries && context.recent_summaries.length > 0) ||
    (context.active_threads && context.active_threads.length > 0) ||
    context.tail_text;

  if (!hasContent) return null;

  const truncatedTail = React.useMemo(() => {
    const text = context.tail_text || "";
    if (text.length <= 300) return text;
    const start = text.length - 300;
    const slice = text.slice(start);
    const boundaryMatch = slice.match(/^[^。！？]*[。！？]/);
    if (
      boundaryMatch &&
      (boundaryMatch.index ?? 0) + boundaryMatch[0].length < 60
    ) {
      return "..." + slice.slice((boundaryMatch.index ?? 0) + boundaryMatch[0].length);
    }
    return "..." + slice;
  }, [context.tail_text]);

  const anchorRef = React.useMemo(() => {
    const parts: string[] = [];
    if (context.last_chapter_tag) parts.push(context.last_chapter_tag);
    if (context.last_block_order) parts.push(`#${context.last_block_order}`);
    return parts.join(" ");
  }, [context.last_chapter_tag, context.last_block_order]);

  return (
    <div className="mb-3 rounded-lg border border-border/40 bg-card text-[13px]">
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-1.5 px-3 py-2"
        onClick={() => setCollapsed(!collapsed)}
      >
        <span className="flex-1 text-left font-semibold">续写上下文</span>
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>

      {/* Anchor — always visible */}
      {context.tail_text && (
        <div className="mx-3 mb-2 rounded-r-md border-l-[3px] border-l-primary bg-muted/50 p-3">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-primary">
              续写起点
            </span>
            {anchorRef && (
              <span className="font-mono text-[11px] text-muted-foreground">
                {anchorRef}
              </span>
            )}
          </div>
          <div className="whitespace-pre-wrap break-all leading-relaxed">
            {truncatedTail}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {context.last_pov && (
              <Badge variant="secondary" className="text-[10px]">
                POV: {context.last_pov}
              </Badge>
            )}
            {context.last_location && (
              <Badge variant="secondary" className="text-[10px]">
                {context.last_location}
              </Badge>
            )}
            {context.narrative_note && (
              <Badge variant="secondary" className="text-[10px]">
                {context.narrative_note}
              </Badge>
            )}
          </div>
        </div>
      )}

      {/* Collapsible body */}
      {!collapsed && (
        <div className="px-3 pb-2.5">
          {/* Recent summaries */}
          {context.recent_summaries && context.recent_summaries.length > 0 && (
            <div className="mb-2">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                近期段落
              </div>
              {context.recent_summaries.map((s, i) => (
                <div key={i} className="flex gap-2 py-0.5 leading-relaxed">
                  <span className="min-w-[40px] shrink-0 text-[11px] text-muted-foreground">
                    {s.chapter_tag ? `[${s.chapter_tag}]` : ""} #{s.block_order}
                  </span>
                  <span>{s.summary}</span>
                </div>
              ))}
            </div>
          )}

          {/* Active threads */}
          {context.active_threads && context.active_threads.length > 0 && (
            <div className="mb-2">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                活跃伏笔
              </div>
              {context.active_threads.map((t, i) => (
                <div key={i} className="py-0.5 pl-3 text-xs text-amber-500 before:mr-1.5 before:content-['*']">
                  {t}
                </div>
              ))}
            </div>
          )}

          {/* Stats */}
          <div className="text-right text-[11px] text-muted-foreground">
            {context.total_words || 0} 字 &middot; {context.total_blocks || 0} 段
          </div>
        </div>
      )}
    </div>
  );
}
