/**
 * SceneProposalCard — draft scene proposal. User can:
 *   - Adopt as a new scene (POST /scenes)
 *   - Adopt by replacing an existing scene (PUT /scenes/{id})
 *   - Dismiss
 *
 * Strictly a draft surface: nothing is written to DB until a button is clicked.
 */

import * as React from "react";
import { CheckCircle2, Loader2, X, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { createScene, updateScene } from "@/api/writer-agent";

import { useRenderAdopt } from "./use-render-adopt";
import type {
  RenderHostContext,
  SceneProposalData,
  ToolRenderAction,
} from "./types";

export interface SceneProposalCardProps {
  data: SceneProposalData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

function buildScenePayload(data: SceneProposalData) {
  return {
    scene_order: data.scene_order,
    title: data.title,
    summary: data.summary,
    pov: data.pov || "",
    setting: data.setting || "",
    characters: (data.characters || []).join(", "),
    key_events: (data.key_events || []).join("; "),
    notes: data.rationale || data.reason || "",
  };
}

export function SceneProposalCard({ data, context }: SceneProposalCardProps) {
  const [dismissed, setDismissed] = React.useState(false);

  const adoptInsert = useRenderAdopt({
    action: async () => {
      const resp = await createScene(data.chapter_id, {
        ...buildScenePayload(data),
        project_id: context.projectId,
      });
      if (!resp.success) throw new Error(resp.error || "创建场景失败");
      return resp.data;
    },
    successMessage: `场景「${data.title}」已创建`,
    onSuccess: (result) =>
      context.onAdopted?.({ type: "scene_proposal", result }),
  });

  const adoptReplace = useRenderAdopt({
    action: async () => {
      if (!data.replace_scene_id) throw new Error("缺少 replace_scene_id");
      const resp = await updateScene(data.replace_scene_id, {
        ...buildScenePayload(data),
        project_id: context.projectId,
      });
      if (!resp.success) throw new Error(resp.error || "替换场景失败");
      return resp.data;
    },
    successMessage: "场景已替换",
    onSuccess: (result) =>
      context.onAdopted?.({ type: "scene_proposal", result }),
  });

  if (dismissed) {
    return (
      <div className="flex items-center gap-2 rounded border border-border/40 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
        <span className="flex-1 truncate">已忽略: {data.title || data.summary}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-[10px]"
          onClick={() => setDismissed(false)}
        >
          恢复
        </Button>
      </div>
    );
  }

  const insertDone = adoptInsert.state === "adopted";
  const replaceDone = adoptReplace.state === "adopted";
  const adopted = insertDone || replaceDone;
  const inFlight = adoptInsert.state === "adopting" || adoptReplace.state === "adopting";
  const err = adoptInsert.error || adoptReplace.error;

  const canReplace = data.mode === "replace" && !!data.replace_scene_id;

  return (
    <Card
      className={cn(
        "w-full",
        adopted
          ? "border-muted bg-muted/40"
          : "border-amber-500/50 border-dashed bg-amber-500/5",
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <Badge
              variant={adopted ? "secondary" : "outline"}
              className="text-[10px]"
            >
              {adopted ? "已采纳" : "草拟"}
            </Badge>
            <span className="text-[11px] text-muted-foreground">
              第 {data.chapter_order} 章 · 场景 #{data.scene_order} (
              {data.mode === "replace" ? "替换" : "新增"})
            </span>
          </div>
          <div className="text-sm font-medium">{data.title}</div>
        </div>
        {!adopted && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-6 shrink-0"
            onClick={() => setDismissed(true)}
            title="忽略"
          >
            <X className="size-3" />
          </Button>
        )}
      </CardHeader>

      <CardContent className="space-y-2 pt-0 text-[12px]">
        <div className="grid grid-cols-[4rem_1fr] gap-x-2 gap-y-1">
          <span className="text-muted-foreground">POV</span>
          <span>{data.pov || "—"}</span>
          {data.setting && (
            <>
              <span className="text-muted-foreground">场景</span>
              <span>{data.setting}</span>
            </>
          )}
          <span className="text-muted-foreground">概述</span>
          <span className="leading-relaxed">{data.summary}</span>
        </div>

        {data.key_events && data.key_events.length > 0 && (
          <div className="space-y-0.5">
            <div className="text-[11px] text-muted-foreground">
              关键事件 ({data.key_events.length})
            </div>
            <ul className="ml-4 list-disc space-y-0.5">
              {data.key_events.map((ev, i) => (
                <li key={i}>{ev}</li>
              ))}
            </ul>
          </div>
        )}

        {(data.characters?.length || data.related_entities?.length) && (
          <div className="flex flex-wrap gap-1">
            {(data.characters || []).map((c, i) => (
              <Badge key={`ch-${i}`} variant="outline" className="text-[10px]">
                {c}
              </Badge>
            ))}
            {(data.related_entities || []).map((e, i) => (
              <Badge key={`e-${i}`} variant="secondary" className="text-[10px]">
                {e}
              </Badge>
            ))}
          </div>
        )}

        {(data.rationale || data.reason) && (
          <div className="rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px] text-muted-foreground">
            <span className="font-medium">理由: </span>
            {data.rationale || data.reason}
          </div>
        )}

        {err && !adopted && (
          <div className="flex items-center gap-1 rounded border border-red-500/40 bg-red-500/10 p-1.5 text-[11px] text-red-500">
            <AlertTriangle className="size-3" />
            {err}
          </div>
        )}
      </CardContent>

      {!adopted && (
        <>
          <Separator />
          <div className="flex items-center justify-end gap-2 p-2">
            {canReplace && (
              <Button
                size="sm"
                variant="outline"
                disabled={inFlight}
                onClick={() => void adoptReplace.run()}
              >
                {adoptReplace.state === "adopting" ? (
                  <Loader2 className="mr-1 size-3 animate-spin" />
                ) : null}
                采纳，替换原场景
              </Button>
            )}
            <Button
              size="sm"
              disabled={inFlight}
              onClick={() => void adoptInsert.run()}
            >
              {adoptInsert.state === "adopting" ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : (
                <CheckCircle2 className="mr-1 size-3" />
              )}
              采纳为新场景
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
