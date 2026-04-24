/**
 * WordBudgetGauge — read-only card for the `word_budget` render type.
 * Shows current chapter word count vs target, per-block breakdown, and
 * a tolerance-aware status badge.
 *
 * Actions (no adoption): "让 Agent 扩写 N 字" / "精简 N 字" prepend a
 * prompt into the author input via context.onPrependToInput.
 */

import { ArrowUpRight, Minimize2, Maximize2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

import type {
  RenderHostContext,
  ToolRenderAction,
  WordBudgetData,
} from "./types";

export interface WordBudgetGaugeProps {
  data: WordBudgetData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

function clampPct(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((value / max) * 100)));
}

export function WordBudgetGauge({ data, context }: WordBudgetGaugeProps) {
  const status = data.status;
  const statusClass = {
    under: "border-blue-500/40 bg-blue-500/5",
    on_target: "border-green-500/40 bg-green-500/5",
    over: "border-red-500/40 bg-red-500/5",
  }[status];
  const statusLabel = {
    under: "字数不足",
    on_target: "达标",
    over: "超出",
  }[status];
  const barMax = Math.max(data.target, data.total, 1);
  const deficit = Math.max(0, data.target - data.total);
  const excess = Math.max(0, data.total - data.target);

  return (
    <Card className={cn("w-full", statusClass)}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="space-y-0.5">
          <div className="text-sm font-medium">
            字数预算 · 第 {data.chapter_order} 章
            {data.chapter_title ? ` · ${data.chapter_title}` : ""}
          </div>
          <div className="text-[11px] text-muted-foreground">
            目标 {data.target.toLocaleString()} 字 · 当前 {data.total.toLocaleString()} 字 · 差值{" "}
            <span
              className={cn(
                "tabular-nums",
                data.diff > 0
                  ? "text-red-500"
                  : data.diff < 0
                    ? "text-blue-500"
                    : "text-green-500",
              )}
            >
              {data.diff > 0 ? "+" : ""}
              {data.diff}
            </span>
          </div>
        </div>
        <Badge variant="secondary" className="text-[10px]">
          {statusLabel}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-3 pt-0">
        <div className="space-y-1">
          <Progress value={clampPct(data.total, barMax)} className="h-2" />
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>0</span>
            <span className="tabular-nums">{data.target.toLocaleString()}</span>
            <span className="tabular-nums">{barMax.toLocaleString()}</span>
          </div>
        </div>

        {data.blocks.length > 0 && (
          <div className="space-y-1">
            <div className="text-[11px] text-muted-foreground">
              段落明细 ({data.blocks.length})
            </div>
            <ul className="space-y-0.5">
              {data.blocks.slice(0, 8).map((b) => (
                <li
                  key={b.block_id}
                  className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px]"
                >
                  <span className="w-6 shrink-0 text-muted-foreground tabular-nums">
                    #{b.block_order}
                  </span>
                  <span className="w-12 shrink-0 tabular-nums text-muted-foreground">
                    {b.word_count.toLocaleString()}字
                  </span>
                  <span className="min-w-0 flex-1 truncate">{b.preview || ""}</span>
                  {context.onJumpToBlock && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="size-5 shrink-0"
                      onClick={() => context.onJumpToBlock?.(b.block_id)}
                      title="跳到段落"
                    >
                      <ArrowUpRight className="size-3" />
                    </Button>
                  )}
                </li>
              ))}
              {data.blocks.length > 8 && (
                <li className="px-2 text-[10px] text-muted-foreground">
                  ... 另有 {data.blocks.length - 8} 段
                </li>
              )}
            </ul>
          </div>
        )}

        {(status !== "on_target" && context.onPrependToInput) && (
          <div className="flex gap-2 pt-1">
            {deficit > 0 && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() =>
                  context.onPrependToInput?.(
                    `请将本章扩写约 ${deficit} 字，保持角色语气与节奏。`,
                  )
                }
              >
                <Maximize2 className="mr-1 size-3" />
                让 Agent 扩写 {deficit} 字
              </Button>
            )}
            {excess > 0 && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() =>
                  context.onPrependToInput?.(
                    `请将本章精简约 ${excess} 字，保留关键冲突与伏笔。`,
                  )
                }
              >
                <Minimize2 className="mr-1 size-3" />
                让 Agent 精简 {excess} 字
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
