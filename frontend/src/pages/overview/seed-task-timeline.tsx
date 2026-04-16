/**
 * SeedTaskTimeline — vertical timeline of processing stage events.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TimelineEvent } from "@/lib/seed-upload-task-state";
import {
  buildEventChips,
  formatTimelineTimestamp,
} from "@/lib/seed-upload-task-view";

/* ---------- Display helpers ---------- */

const STAGE_KEY_TEXT: Record<string, string> = {
  queued: "等待开始",
  extract_text: "提取上传文本",
  smart_segmentation: "智能分段",
  sequential_reading: "顺序深度阅读",
  arc_summary: "弧线摘要",
  global_integration: "全局整合",
  ontology: "梳理故事结构",
  agent_profiles: "角色Agent档案",
  completed: "全部完成",
  failed: "执行失败",
  uploading: "文件上传",
};

function formatStageKey(key: string): string {
  return STAGE_KEY_TEXT[key] || key;
}

/* ---------- Props ---------- */

interface SeedTaskTimelineProps {
  events: TimelineEvent[];
  title?: string;
  hintText?: string;
}

/* ---------- Component ---------- */

export default function SeedTaskTimeline({
  events,
  title = "阶段日志",
  hintText = "自动追踪最新事件",
}: SeedTaskTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoStick, setAutoStick] = useState(true);

  const scrollToBottom = useCallback(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, []);

  useEffect(() => {
    if (autoStick) scrollToBottom();
  }, [events.length, autoStick, scrollToBottom]);

  const handleScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    setAutoStick(distance < 40);
  }, []);

  return (
    <section className="rounded-xl border p-2.5 bg-gradient-to-b from-amber-50/80 to-amber-50/40 space-y-2.5">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-[11px] tracking-wide text-muted-foreground">
            时间轴卷宗
          </div>
          <h3 className="mt-1 font-serif text-base font-semibold">{title}</h3>
        </div>
        <span className="text-xs text-muted-foreground">{hintText}</span>
      </div>

      {/* Events list */}
      <div
        ref={scrollRef}
        className="mt-2.5 max-h-[420px] overflow-auto pr-1 space-y-2.5"
        onScroll={handleScroll}
      >
        {events.map((event, idx) => {
          const chips = buildEventChips(event);
          return (
            <article
              key={event.id}
              className="grid gap-2"
              style={{ gridTemplateColumns: "18px minmax(0,1fr)" }}
            >
              {/* Rail */}
              <div className="relative">
                <span
                  className={cn(
                    "relative z-[1] block w-4 h-4 rounded-full border-2",
                    event.status === "active"
                      ? "border-amber-500 bg-amber-100"
                      : event.status === "failed"
                        ? "border-red-500 bg-red-100"
                        : "border-muted-foreground/40 bg-amber-50",
                  )}
                />
                {idx < events.length - 1 && (
                  <div className="absolute left-[7px] top-4 bottom-[-18px] w-px bg-muted-foreground/30" />
                )}
              </div>

              {/* Body */}
              <div
                className={cn(
                  "rounded-lg border p-2.5",
                  event.status === "active"
                    ? "border-amber-500/40 bg-amber-50/80 shadow-md"
                    : event.status === "failed"
                      ? "border-red-500/40 bg-red-50/80"
                      : event.status === "completed"
                        ? "border-border bg-amber-50/60 opacity-90"
                        : "border-border bg-amber-50/60",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-sm">{event.title}</strong>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {formatTimelineTimestamp(event.timestamp)}
                  </span>
                </div>
                {event.detail && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    {event.detail}
                  </p>
                )}
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  <Badge variant="secondary" className="text-[11px]">
                    {formatStageKey(event.stage)}
                  </Badge>
                  {chips.map((chip) => (
                    <Badge
                      key={`${event.id}_${chip}`}
                      variant="secondary"
                      className="text-[11px]"
                    >
                      {chip}
                    </Badge>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
