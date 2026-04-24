/**
 * SceneTimelineCard — read-only timeline of scenes / actions / state changes
 * along a single axis (scene_order / chapter_order / step).
 *
 * Events are rendered as stacked rows sorted by axis_value. event_type drives
 * the icon + color so users can visually skim what shifted across the axis.
 * Clicking a scene event jumps to it via context.onOpenScene.
 */

import {
  ArrowUpRight,
  Brain,
  Circle,
  Flame,
  GitBranch,
  Heart,
  Lightbulb,
  Sparkles,
  Wand2,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import type {
  RenderHostContext,
  SceneTimelineData,
  SceneTimelineEvent,
  ToolRenderAction,
} from "./types";

export interface SceneTimelineCardProps {
  data: SceneTimelineData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

const EVENT_TYPE_ICON: Record<
  NonNullable<SceneTimelineEvent["event_type"]>,
  LucideIcon
> = {
  scene: Wand2,
  action: Flame,
  state_change: Sparkles,
  knowledge: Lightbulb,
  emotional: Heart,
  branch_step: GitBranch,
};

const EVENT_TYPE_COLOR: Record<
  NonNullable<SceneTimelineEvent["event_type"]>,
  string
> = {
  scene: "border-blue-500/50 bg-blue-500/10 text-blue-900 dark:text-blue-200",
  action: "border-orange-500/50 bg-orange-500/10 text-orange-900 dark:text-orange-200",
  state_change: "border-purple-500/50 bg-purple-500/10 text-purple-900 dark:text-purple-200",
  knowledge: "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  emotional: "border-pink-500/50 bg-pink-500/10 text-pink-900 dark:text-pink-200",
  branch_step: "border-green-500/50 bg-green-500/10 text-green-900 dark:text-green-200",
};

const AXIS_LABEL: Record<SceneTimelineData["axis"], string> = {
  scene_order: "场景序",
  chapter_order: "章节序",
  step: "推演步",
};

const MODE_LABEL: Record<SceneTimelineData["mode"], string> = {
  chapter: "章节视角",
  character: "角色视角",
  branch: "分支推演",
};

export function SceneTimelineCard({ data, context }: SceneTimelineCardProps) {
  const sorted = [...data.events].sort((a, b) => a.axis_value - b.axis_value);
  const minAxis = sorted[0]?.axis_value ?? 0;
  const maxAxis = sorted[sorted.length - 1]?.axis_value ?? minAxis;

  return (
    <Card className="w-full border-blue-500/40 bg-blue-500/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-0.5">
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-[10px]">
                {MODE_LABEL[data.mode]}
              </Badge>
              <span className="text-[11px] text-muted-foreground">
                {AXIS_LABEL[data.axis]} {minAxis}
                {maxAxis !== minAxis ? ` → ${maxAxis}` : ""} · {data.events.length} 事件
              </span>
            </div>
            <div className="truncate text-sm font-medium">{data.title}</div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        {sorted.length === 0 ? (
          <div className="rounded border border-dashed border-border/40 bg-background/60 px-2 py-3 text-center text-[11px] text-muted-foreground">
            暂无事件
          </div>
        ) : (
          <ol className="relative space-y-1.5 pl-5">
            {/* vertical spine */}
            <div className="absolute bottom-1 left-1.5 top-1 w-px bg-border/60" />
            {sorted.map((e) => {
              const Icon = e.event_type ? EVENT_TYPE_ICON[e.event_type] : Circle;
              const colorClass = e.event_type
                ? EVENT_TYPE_COLOR[e.event_type]
                : "border-border/40 bg-background/60";
              const jumpable = e.event_type === "scene" && context.onOpenScene;
              return (
                <li
                  key={e.event_id}
                  className={cn(
                    "relative rounded border px-2 py-1 text-[11px]",
                    colorClass,
                    e.highlight && "ring-1 ring-foreground/40",
                  )}
                >
                  {/* dot */}
                  <span className="absolute -left-[14px] top-1.5 flex size-3 items-center justify-center rounded-full bg-background">
                    <Icon className="size-2.5" />
                  </span>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="shrink-0 tabular-nums text-[10px] text-muted-foreground">
                          #{e.axis_value}
                        </span>
                        <span className="truncate font-medium">{e.label}</span>
                      </div>
                      {e.subtitle && (
                        <div className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
                          {e.subtitle}
                        </div>
                      )}
                      {(e.related_entity_id || e.related_thread_key) && (
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {e.related_entity_id && (
                            <button
                              type="button"
                              onClick={() =>
                                context.onOpenEntity?.(e.related_entity_id!)
                              }
                              disabled={!context.onOpenEntity}
                              className={cn(
                                "inline-flex items-center gap-0.5 rounded-sm border border-border/40 bg-background/60 px-1 text-[9px]",
                                context.onOpenEntity &&
                                  "cursor-pointer hover:bg-accent",
                              )}
                            >
                              <Brain className="size-2.5" />
                              <span className="max-w-[6rem] truncate">
                                {e.related_entity_id}
                              </span>
                            </button>
                          )}
                          {e.related_thread_key && (
                            <span className="inline-flex items-center gap-0.5 rounded-sm border border-border/40 bg-background/60 px-1 text-[9px] text-muted-foreground">
                              <GitBranch className="size-2.5" />
                              <span className="max-w-[6rem] truncate">
                                {e.related_thread_key}
                              </span>
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    {jumpable && (
                      <button
                        type="button"
                        onClick={() => context.onOpenScene?.(e.event_id)}
                        className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
                        title="跳到场景"
                      >
                        <ArrowUpRight className="size-3" />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
