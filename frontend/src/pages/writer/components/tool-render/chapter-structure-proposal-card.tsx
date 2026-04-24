/**
 * ChapterStructureProposalCard — batch chapter structure proposal.
 *
 * Displays N drafted chapters as a check-list. Default selects all.
 * On adoption:
 *   1. createChapter(projectId, {chapter_order, title}) per selected row
 *   2. updateChapter(chapter_id, {summary, hook, word_target, pov_character})
 *
 * Errors from any row surface as a destructive toast + keep the card open.
 */

import * as React from "react";
import { CheckCircle2, Loader2, X, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { createChapter, updateChapter } from "@/api/writer-agent";

import { useRenderAdopt } from "./use-render-adopt";
import type {
  ChapterStructureProposalData,
  RenderHostContext,
  ToolRenderAction,
} from "./types";

export interface ChapterStructureProposalCardProps {
  data: ChapterStructureProposalData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

export function ChapterStructureProposalCard({
  data,
  context,
}: ChapterStructureProposalCardProps) {
  const [dismissed, setDismissed] = React.useState(false);
  const [selected, setSelected] = React.useState<Set<number>>(
    () => new Set(data.chapters.map((c) => c.chapter_order)),
  );

  const toggle = React.useCallback((order: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(order)) next.delete(order);
      else next.add(order);
      return next;
    });
  }, []);

  const selectAll = React.useCallback(() => {
    setSelected(new Set(data.chapters.map((c) => c.chapter_order)));
  }, [data.chapters]);

  const clearAll = React.useCallback(() => setSelected(new Set()), []);

  const adopt = useRenderAdopt({
    action: async () => {
      const chosen = data.chapters.filter((c) => selected.has(c.chapter_order));
      if (chosen.length === 0) throw new Error("未选择任何章节");
      const created: string[] = [];
      for (const ch of chosen) {
        const resp = await createChapter(context.projectId, {
          title: ch.title,
          chapter_order: ch.chapter_order,
        });
        if (!resp.success) {
          throw new Error(
            resp.error || `第 ${ch.chapter_order} 章创建失败`,
          );
        }
        const chapter_id = (resp.data as { chapter_id?: string } | undefined)?.chapter_id;
        if (!chapter_id) continue;
        created.push(chapter_id);
        // Stash summary/hook/pov into chapter metadata — update is best-effort;
        // a partial failure here shouldn't roll back the creation.
        try {
          await updateChapter(chapter_id, {
            project_id: context.projectId,
            summary: ch.summary,
            pov_character: ch.pov_character || "",
          });
        } catch {
          // Silent — updates are additive, creation already succeeded.
        }
      }
      return { created_chapter_ids: created };
    },
    successMessage: `已创建 ${selected.size} 个章节`,
    onSuccess: (result) =>
      context.onAdopted?.({ type: "chapter_structure_proposal", result }),
  });

  if (dismissed) {
    return (
      <div className="flex items-center gap-2 rounded border border-border/40 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
        <span className="flex-1 truncate">
          已忽略: {data.chapters.length} 章结构提案
        </span>
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

  const adopted = adopt.state === "adopted";
  const inFlight = adopt.state === "adopting";
  const err = adopt.error;
  const selectedCount = selected.size;
  const allSelected = selectedCount === data.chapters.length;

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
              章节结构提案 · 共 {data.chapters.length} 章 (第{" "}
              {data.start_chapter_order}–
              {data.start_chapter_order + data.chapters.length - 1} 章)
            </span>
          </div>
          {data.overall_arc && (
            <div className="text-[12px] font-medium">{data.overall_arc}</div>
          )}
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
        <ul className="space-y-1.5">
          {data.chapters.map((ch) => {
            const checked = selected.has(ch.chapter_order);
            return (
              <li
                key={ch.chapter_order}
                className={cn(
                  "rounded border border-border/40 bg-background/60 p-2 text-[11px]",
                  adopted && !checked && "opacity-40",
                )}
              >
                <label className="flex items-start gap-2">
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => !adopted && toggle(ch.chapter_order)}
                    disabled={adopted}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">
                        Ch.{ch.chapter_order}
                      </Badge>
                      <span className="font-medium">{ch.title}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
                        目标 {ch.word_target.toLocaleString()} 字
                      </span>
                    </div>
                    <div className="mt-1 leading-relaxed text-muted-foreground">
                      {ch.summary}
                    </div>
                    {ch.hook && (
                      <div className="mt-1 text-[10px] text-muted-foreground">
                        钩子: {ch.hook}
                      </div>
                    )}
                    {(ch.pov_character || ch.key_threads?.length) && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {ch.pov_character && (
                          <Badge variant="outline" className="text-[10px]">
                            POV: {ch.pov_character}
                          </Badge>
                        )}
                        {ch.key_threads?.map((t, i) => (
                          <Badge
                            key={i}
                            variant="secondary"
                            className="text-[10px]"
                          >
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </label>
              </li>
            );
          })}
        </ul>

        {data.rationale && (
          <div className="rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px] text-muted-foreground">
            <span className="font-medium">理由: </span>
            {data.rationale}
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
          <div className="flex items-center justify-between gap-2 p-2 text-[11px]">
            <div className="text-muted-foreground">
              已选 {selectedCount}/{data.chapters.length}
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-2 text-[10px]"
                onClick={allSelected ? clearAll : selectAll}
              >
                {allSelected ? "全部取消" : "全部勾选"}
              </Button>
            </div>
            <Button
              size="sm"
              disabled={inFlight || selectedCount === 0}
              onClick={() => void adopt.run()}
            >
              {inFlight ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : (
                <CheckCircle2 className="mr-1 size-3" />
              )}
              采纳 {selectedCount} 章
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
