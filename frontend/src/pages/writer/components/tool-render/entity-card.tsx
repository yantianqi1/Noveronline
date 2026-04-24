/**
 * EntityCard — read-only view of a character/org/item/location/skill.
 * Presents 5 section tabs (overview/profile/relations/events/memories).
 * Tab switching is local only — the card renders whatever section the
 * backend returned; clicking a different tab just shows a gentle prompt
 * to call `query_entity(section=...)` via the author input.
 *
 * mode=propose (new entity draft) is currently rendered read-only with an
 * extra amber badge; real adoption is done by the agent via manage_entity.
 */

import * as React from "react";
import { ArrowUpRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import type {
  EntityCardData,
  EntityCardSection,
  RenderHostContext,
  ToolRenderAction,
} from "./types";

export interface EntityCardProps {
  data: EntityCardData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

const SECTION_LABEL: Record<EntityCardSection, string> = {
  overview: "概览",
  profile: "档案",
  relations: "关系",
  events: "事件",
  memories: "记忆",
};

const TYPE_LABEL: Record<string, string> = {
  character: "角色",
  organization: "组织",
  item: "物品",
  location: "地点",
  skill: "技能",
};

export function EntityCard({ data, context }: EntityCardProps) {
  const [, setSection] = React.useState<EntityCardSection>(data.section);
  const isPropose = data.mode === "propose";

  function renderSection() {
    switch (data.section) {
      case "overview":
        if (!data.overview) return <div className="text-[11px] text-muted-foreground">无概览数据</div>;
        return (
          <dl className="grid grid-cols-[5rem_1fr] gap-x-2 gap-y-1 text-[12px]">
            {data.overview.core_drive && (
              <>
                <dt className="text-muted-foreground">核心驱动</dt>
                <dd>{data.overview.core_drive}</dd>
              </>
            )}
            {data.overview.surface_mask && (
              <>
                <dt className="text-muted-foreground">表面</dt>
                <dd>{data.overview.surface_mask}</dd>
              </>
            )}
            {data.overview.hidden_tension && (
              <>
                <dt className="text-muted-foreground">内在矛盾</dt>
                <dd>{data.overview.hidden_tension}</dd>
              </>
            )}
            {data.overview.current_objective && (
              <>
                <dt className="text-muted-foreground">当前目标</dt>
                <dd>{data.overview.current_objective}</dd>
              </>
            )}
          </dl>
        );
      case "profile":
        if (!data.profile) return <div className="text-[11px] text-muted-foreground">无档案数据</div>;
        return (
          <div className="space-y-2 text-[12px]">
            {data.profile.deep_profile_md && (
              <pre className="whitespace-pre-wrap rounded border border-border/40 bg-background/60 p-2 font-sans leading-relaxed">
                {data.profile.deep_profile_md}
              </pre>
            )}
            <dl className="grid grid-cols-[5rem_1fr] gap-x-2 gap-y-1">
              {data.profile.values_text && (
                <>
                  <dt className="text-muted-foreground">价值观</dt>
                  <dd>{data.profile.values_text}</dd>
                </>
              )}
              {data.profile.fears_text && (
                <>
                  <dt className="text-muted-foreground">恐惧</dt>
                  <dd>{data.profile.fears_text}</dd>
                </>
              )}
              {data.profile.voice_style && (
                <>
                  <dt className="text-muted-foreground">语气</dt>
                  <dd>{data.profile.voice_style}</dd>
                </>
              )}
              {data.profile.decision_pattern && (
                <>
                  <dt className="text-muted-foreground">决策</dt>
                  <dd>{data.profile.decision_pattern}</dd>
                </>
              )}
            </dl>
          </div>
        );
      case "relations":
        if (!data.relations?.length) return <div className="text-[11px] text-muted-foreground">无关系</div>;
        return (
          <ul className="space-y-1">
            {data.relations.map((r, i) => (
              <li
                key={i}
                className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px]"
              >
                <Badge variant="outline" className="text-[10px]">
                  {r.relation_type}
                </Badge>
                <span className="font-medium">{r.other_name}</span>
                {typeof r.trust_level === "number" && (
                  <span className="text-muted-foreground tabular-nums">
                    信任 {r.trust_level.toFixed(1)}
                  </span>
                )}
                {r.description && (
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">
                    {r.description}
                  </span>
                )}
                {context.onOpenEntity && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="size-5 shrink-0"
                    onClick={() => context.onOpenEntity?.(r.other_entity_id)}
                  >
                    <ArrowUpRight className="size-3" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        );
      case "events":
        if (!data.events?.length) return <div className="text-[11px] text-muted-foreground">无事件</div>;
        return (
          <ul className="space-y-1">
            {data.events.map((ev) => (
              <li
                key={ev.event_id}
                className="rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px]"
              >
                <div className="flex items-center gap-1.5">
                  {ev.chapter_order != null && (
                    <Badge variant="outline" className="text-[10px]">
                      第 {ev.chapter_order} 章
                    </Badge>
                  )}
                  <Badge variant="secondary" className="text-[10px]">
                    {ev.event_type}
                  </Badge>
                </div>
                <div className="mt-0.5">{ev.summary}</div>
              </li>
            ))}
          </ul>
        );
      case "memories":
        if (!data.memories?.length) return <div className="text-[11px] text-muted-foreground">无记忆</div>;
        return (
          <ul className="space-y-1">
            {data.memories.map((m) => (
              <li
                key={m.memory_id}
                className="rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px]"
              >
                <div className="flex items-center gap-1.5">
                  <Badge variant={m.canon ? "secondary" : "outline"} className="text-[10px]">
                    {m.canon ? "canon" : "candidate"}
                  </Badge>
                  <span className="text-muted-foreground tabular-nums">
                    显著性 {m.salience.toFixed(2)}
                  </span>
                </div>
                <div className="mt-0.5">{m.content}</div>
              </li>
            ))}
          </ul>
        );
      default:
        return null;
    }
  }

  const sectionsLoaded = data.section;

  return (
    <Card
      className={cn(
        "w-full",
        isPropose
          ? "border-amber-500/40 border-dashed bg-amber-500/5"
          : "border-blue-500/30 bg-blue-500/5",
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{data.name}</span>
            <Badge variant="outline" className="text-[10px]">
              {TYPE_LABEL[data.entity_type] || data.entity_type}
            </Badge>
            {data.entity_id && (
              <span className="text-[10px] text-muted-foreground tabular-nums">
                #{data.entity_id.slice(0, 8)}
              </span>
            )}
            <Badge variant="secondary" className="text-[10px]">
              {isPropose ? "草拟" : "只读"}
            </Badge>
          </div>
          {(data.aliases?.length || data.tags?.length) && (
            <div className="flex flex-wrap gap-1 text-[10px]">
              {data.aliases?.map((a, i) => (
                <span key={`al-${i}`} className="text-muted-foreground">
                  {a}
                </span>
              ))}
              {data.tags?.map((t, i) => (
                <Badge key={`tg-${i}`} variant="outline" className="text-[10px]">
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </div>
        {context.onOpenEntity && data.entity_id && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={() => context.onOpenEntity?.(data.entity_id!)}
          >
            <ArrowUpRight className="mr-1 size-3" />
            图谱
          </Button>
        )}
      </CardHeader>

      <CardContent className="space-y-2 pt-0">
        {/* Section switcher — clicking a different section asks the user to
            nudge the agent via input (we don't re-call the tool here). */}
        <div className="flex flex-wrap gap-1">
          {(Object.keys(SECTION_LABEL) as EntityCardSection[]).map((s) => (
            <Button
              key={s}
              size="sm"
              variant={s === sectionsLoaded ? "secondary" : "ghost"}
              className="h-6 px-2 text-[10px]"
              onClick={() => {
                setSection(s);
                if (s !== sectionsLoaded && context.onPrependToInput) {
                  context.onPrependToInput(
                    `请再查询 ${data.name} 的 ${SECTION_LABEL[s]} 信息。`,
                  );
                }
              }}
            >
              {SECTION_LABEL[s]}
            </Button>
          ))}
        </div>

        {data.summary && (
          <div className="text-[11px] leading-relaxed text-muted-foreground">
            {data.summary}
          </div>
        )}

        <div>{renderSection()}</div>
      </CardContent>
    </Card>
  );
}
