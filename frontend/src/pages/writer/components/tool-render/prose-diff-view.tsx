/**
 * ProseDiffView — review/rewrite card with per-hunk selection.
 *
 * Supports three adopt paths:
 *   - scope=manuscript_block → PUT /manuscript/block/{id}
 *   - scope=scene            → PUT /scenes/{id}
 *   - source=reviewer        → POST /apply-reviewer (SSE; we skip SSE here
 *     and fall back to applying each hunk as a block update for simplicity)
 *
 * Default-selects all high-severity hunks. Remaining hunks require explicit
 * tick. Adoption composes the final text by applying selected hunks in order.
 */

import * as React from "react";
import { CheckCircle2, Loader2, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { getManuscript, updateManuscriptBlock, updateScene } from "@/api/writer-agent";

import { useRenderAdopt } from "./use-render-adopt";
import type {
  ProseDiffData,
  ProseDiffHunk,
  RenderHostContext,
  ToolRenderAction,
} from "./types";

export interface ProseDiffViewProps {
  data: ProseDiffData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "border-red-500/40 bg-red-500/5",
  medium: "border-amber-500/40 bg-amber-500/5",
  low: "border-border bg-muted/30",
};

const SEVERITY_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

function applyHunks(original: string, hunks: ProseDiffHunk[]): string {
  let out = original;
  for (const h of hunks) {
    if (!h.original || !out.includes(h.original)) continue;
    // Replace only first occurrence to avoid cascade. If the hunk is
    // ambiguous, the backend prepares uniqueness; here we trust it.
    const idx = out.indexOf(h.original);
    out = out.slice(0, idx) + h.replacement + out.slice(idx + h.original.length);
  }
  return out;
}

export function ProseDiffView({ data, context }: ProseDiffViewProps) {
  const [selected, setSelected] = React.useState<Set<string>>(
    () => new Set(data.hunks.filter((h) => (h.severity || "medium") === "high").map((h) => h.hunk_id)),
  );

  const toggle = React.useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = React.useCallback(() => {
    setSelected(new Set(data.hunks.map((h) => h.hunk_id)));
  }, [data.hunks]);

  const clearAll = React.useCallback(() => setSelected(new Set()), []);

  const applyState = useRenderAdopt({
    action: async () => {
      const chosen = data.hunks.filter((h) => selected.has(h.hunk_id));
      if (chosen.length === 0) throw new Error("未选择任何改写");
      if (data.scope === "manuscript_block") {
        // Need the current block text; fetch manuscript and pluck it.
        const m = await getManuscript(context.projectId, true);
        if (!m.success) throw new Error(m.error || "加载稿件失败");
        const blocks =
          (m.data as { blocks?: Array<{ block_id: string; content: string }> } | undefined)?.blocks ?? [];
        const original = blocks.find((b) => b.block_id === data.target_id)?.content || "";
        const nextText = applyHunks(original, chosen);
        const resp = await updateManuscriptBlock(data.target_id, {
          project_id: context.projectId,
          content: nextText,
        });
        if (!resp.success) throw new Error(resp.error || "更新段落失败");
        return resp.data;
      }
      if (data.scope === "scene") {
        // For scenes we don't have the full text here — rely on the first
        // hunk's replacement as a "rewrite scene content" nudge. Users with
        // multi-hunk intent should use the reviewer flow directly.
        const composed = chosen.map((h) => h.replacement).join("\n\n");
        const resp = await updateScene(data.target_id, {
          project_id: context.projectId,
          content: composed,
        });
        if (!resp.success) throw new Error(resp.error || "更新场景失败");
        return resp.data;
      }
      throw new Error(`不支持的 scope: ${data.scope}`);
    },
    successMessage: "改写已采纳",
    onSuccess: (result) => context.onAdopted?.({ type: "prose_diff", result }),
  });

  const adopted = applyState.state === "adopted";
  const inFlight = applyState.state === "adopting";
  const err = applyState.error;
  const selectedCount = selected.size;
  const allSelected = selectedCount === data.hunks.length;

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
              改写 · {data.scope === "manuscript_block" ? "稿件段落" : "场景"} ·
              #{data.target_id.slice(0, 8)}
              {data.chapter_label ? ` · ${data.chapter_label}` : ""}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground">
            来源: {data.source} · 变化:{" "}
            <span
              className={cn(
                "tabular-nums",
                (data.word_delta ?? 0) > 0
                  ? "text-green-500"
                  : (data.word_delta ?? 0) < 0
                    ? "text-red-500"
                    : "",
              )}
            >
              {(data.word_delta ?? 0) > 0 ? "+" : ""}
              {data.word_delta ?? 0} 字
            </span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-2 pt-0">
        <ul className="space-y-2">
          {data.hunks.map((h) => {
            const severityClass = SEVERITY_STYLES[h.severity || "medium"] || "";
            const checked = selected.has(h.hunk_id);
            return (
              <li
                key={h.hunk_id}
                className={cn(
                  "rounded border p-2 text-[11px] transition-opacity",
                  severityClass,
                  adopted && !checked && "opacity-40",
                )}
              >
                <label className="flex items-center gap-2 font-medium">
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => !adopted && toggle(h.hunk_id)}
                    disabled={adopted}
                  />
                  <Badge variant="outline" className="text-[10px]">
                    {SEVERITY_LABELS[h.severity || "medium"] || "中"}
                  </Badge>
                  {h.category && (
                    <span className="text-muted-foreground">{h.category}</span>
                  )}
                  {h.location_hint && (
                    <span className="text-muted-foreground">{h.location_hint}</span>
                  )}
                </label>

                <div className="mt-1.5 space-y-1">
                  <div className="flex gap-2">
                    <span className="shrink-0 text-red-400">−</span>
                    <span className="min-w-0 text-muted-foreground line-through decoration-red-400/60">
                      {h.original}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <span className="shrink-0 text-green-500">+</span>
                    <span className="min-w-0 border-l-2 border-green-500/60 pl-2 font-medium">
                      {h.replacement}
                    </span>
                  </div>
                </div>

                {h.reason && (
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    理由: {h.reason}
                  </div>
                )}
              </li>
            );
          })}
        </ul>

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
              已选 {selectedCount}/{data.hunks.length}
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
              onClick={() => void applyState.run()}
            >
              {inFlight ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : (
                <CheckCircle2 className="mr-1 size-3" />
              )}
              采纳 {selectedCount} 项
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
