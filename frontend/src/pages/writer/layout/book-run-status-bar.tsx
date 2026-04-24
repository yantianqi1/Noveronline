/**
 * BookRunStatusBar — 38 px persistent top bar for the writer workbench.
 *
 * Reads runtime state exclusively from `useBookRunStatusStore`. Does NOT
 * own the SSE subscription; BookPlanPanel is still the connection owner
 * (W-1 scope). StatusBar only shows data the store already has.
 */

import * as React from "react";
import { BookOpen, BookmarkCheck, Dot, PlayCircle, Square, PanelRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useBookRunStatusStore } from "@/stores/book-run-store";

const STAGE_LABELS: Record<string, string> = {
  PLAN_INIT: "初始化",
  RETRIEVE: "检索",
  OUTLINE: "大纲",
  CHAPTER_WRITE: "逐章写作",
  WORD_AUDIT: "字数审计",
  LEXICON_AUDIT: "禁词审计",
  CHAPTER_COMMIT: "章节落库",
  DONE: "完成",
};

function formatEventFreshness(lastEventAt: number | null): string {
  if (!lastEventAt) return "—";
  const delta = Date.now() - lastEventAt;
  if (delta < 2_000) return "刚刚";
  if (delta < 60_000) return `${Math.round(delta / 1000)} 秒前`;
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)} 分前`;
  return ">1h";
}

export interface BookRunStatusBarProps {
  onOpenDrawer: () => void;
  onAbort?: () => void;
  onCreatePlan?: () => void;
  className?: string;
}

export function BookRunStatusBar({
  onOpenDrawer,
  onAbort,
  onCreatePlan,
  className,
}: BookRunStatusBarProps) {
  const status = useBookRunStatusStore((s) => s.status);
  const stage = useBookRunStatusStore((s) => s.stage);
  const running = useBookRunStatusStore((s) => s.running);
  const lastEventAt = useBookRunStatusStore((s) => s.lastEventAt);

  const [, tick] = React.useState(0);
  React.useEffect(() => {
    if (!lastEventAt) return;
    const id = window.setInterval(() => tick((v) => v + 1), 10_000);
    return () => window.clearInterval(id);
  }, [lastEventAt]);

  if (!status) {
    return (
      <div
        className={cn(
          "flex h-[38px] w-full items-center gap-2 border-b bg-muted/30 px-3 text-xs text-muted-foreground",
          className,
        )}
      >
        <BookOpen className="size-3.5" />
        <span>尚无成书计划</span>
        <div className="ml-auto flex items-center gap-1">
          {onCreatePlan && (
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={onCreatePlan}>
              创建计划
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs"
            onClick={onOpenDrawer}
            title="打开成书抽屉 (⌘B)"
          >
            <PanelRight className="size-3.5 mr-1" />
            成书 ⌘B
          </Button>
        </div>
      </div>
    );
  }

  const stageLabel =
    STAGE_LABELS[stage || ""] || STAGE_LABELS[status.last_stage?.split("#")[0] || ""] || "待启动";
  const pct = Math.min(100, Math.max(0, status.progress_pct || 0));
  const dotClass = running ? "text-green-500" : "text-muted-foreground";

  return (
    <div
      className={cn(
        "flex h-[38px] w-full items-center gap-3 border-b bg-muted/30 px-3 text-xs",
        className,
      )}
    >
      <BookmarkCheck className="size-3.5 text-primary" />
      <span className="truncate font-medium" title={status.title}>
        {status.title || "未命名计划"}
      </span>

      <Badge variant="outline" className="h-5 gap-1 px-1.5 text-[10px]">
        <Dot className={cn("size-3", dotClass)} />
        {stageLabel}
      </Badge>

      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">
          {status.completed_chapter_count}/{status.chapter_count} 章
        </span>
        <Progress value={pct} className="h-1.5 w-24" />
        <span className="tabular-nums">{pct.toFixed(1)}%</span>
      </div>

      <span className="text-muted-foreground tabular-nums">
        {status.words_written_total.toLocaleString()} / {status.total_word_target.toLocaleString()} 字
      </span>

      {status.error_count > 0 && (
        <Badge variant="destructive" className="h-5 px-1.5 text-[10px]">
          {status.error_count} 个错误
        </Badge>
      )}

      <span className="text-muted-foreground">SSE {formatEventFreshness(lastEventAt)}</span>

      <div className="ml-auto flex items-center gap-1">
        {running && onAbort && (
          <Button size="sm" variant="destructive" className="h-6 px-2 text-xs" onClick={onAbort}>
            <Square className="size-3 mr-1" />
            终止
          </Button>
        )}
        {!running && status.status === "draft" && (
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
            <PlayCircle className="size-3 mr-1" />
            草稿
          </Badge>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-xs"
          onClick={onOpenDrawer}
          title="打开成书抽屉 (⌘B)"
        >
          <PanelRight className="size-3.5 mr-1" />
          成书 ⌘B
        </Button>
      </div>
    </div>
  );
}
