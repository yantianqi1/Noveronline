/**
 * RelationshipProposalCard — suggested new/updated relationship between two
 * entities. Adoption re-invokes the writer agent with a precise instruction
 * that nudges `manage_relationship` to persist the proposal.
 *
 * Unlike EntityCard, this always starts as a draft (amber) with an explicit
 * adopt button. Displays evidence snippet + proposed metadata for reviewer.
 */

import * as React from "react";
import { CheckCircle2, Loader2, X, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { updateWorldData } from "@/api/writer-agent";

import { useRenderAdopt } from "./use-render-adopt";
import type {
  RelationshipProposalData,
  RenderHostContext,
  ToolRenderAction,
} from "./types";

export interface RelationshipProposalCardProps {
  data: RelationshipProposalData;
  actions: ToolRenderAction[];
  context: RenderHostContext;
}

function buildAdoptInstruction(data: RelationshipProposalData): string {
  const parts: string[] = [
    `请调用 manage_relationship 在 ${data.entity_a} 与 ${data.entity_b} 之间建立/更新关系。`,
    `关系类型: ${data.relation_type}`,
    `描述: ${data.description}`,
  ];
  if (typeof data.trust_level === "number") {
    parts.push(`信任度: ${data.trust_level.toFixed(2)}`);
  }
  if (data.power_dynamic) parts.push(`权力结构: ${data.power_dynamic}`);
  if (data.conflict_trigger) parts.push(`冲突触发: ${data.conflict_trigger}`);
  if (data.evidence_snippet) {
    parts.push(`原文证据:\n${data.evidence_snippet}`);
  }
  return parts.join("\n");
}

export function RelationshipProposalCard({
  data,
  context,
}: RelationshipProposalCardProps) {
  const [dismissed, setDismissed] = React.useState(false);

  const adopt = useRenderAdopt({
    action: async () => {
      // updateWorldData uses SSE; consume it synchronously with a collector.
      const events: unknown[] = [];
      await new Promise<void>((resolve, reject) => {
        let resolved = false;
        updateWorldData(
          {
            project_id: context.projectId,
            content: buildAdoptInstruction(data),
          },
          {
            onEvent: (ev) => events.push(ev),
            onError: (err) => {
              if (!resolved) {
                resolved = true;
                reject(err instanceof Error ? err : new Error(String(err)));
              }
            },
            onDone: () => {
              if (!resolved) {
                resolved = true;
                resolve();
              }
            },
          },
        ).catch((err) => {
          if (!resolved) reject(err);
        });
      });
      return { events };
    },
    successMessage: `已创建关系: ${data.entity_a} → ${data.entity_b}`,
    onSuccess: (result) =>
      context.onAdopted?.({ type: "relationship_proposal", result }),
  });

  if (dismissed) {
    return (
      <div className="flex items-center gap-2 rounded border border-border/40 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
        <span className="flex-1 truncate">
          已忽略关系: {data.entity_a} — {data.entity_b}
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
            <span className="text-[11px] text-muted-foreground">关系提案</span>
          </div>
          <div className="flex items-center gap-2 text-sm font-medium">
            <span>{data.entity_a}</span>
            <Badge variant="outline" className="text-[10px]">
              {data.relation_type}
            </Badge>
            <span>{data.entity_b}</span>
          </div>
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
        <div className="leading-relaxed">{data.description}</div>

        <div className="grid grid-cols-[5rem_1fr] gap-x-2 gap-y-0.5 text-[11px]">
          {typeof data.trust_level === "number" && (
            <>
              <span className="text-muted-foreground">信任度</span>
              <span className="tabular-nums">{data.trust_level.toFixed(2)}</span>
            </>
          )}
          {data.power_dynamic && (
            <>
              <span className="text-muted-foreground">权力</span>
              <span>{data.power_dynamic}</span>
            </>
          )}
          {data.conflict_trigger && (
            <>
              <span className="text-muted-foreground">冲突</span>
              <span>{data.conflict_trigger}</span>
            </>
          )}
        </div>

        {data.evidence_snippet && (
          <div className="rounded border border-border/40 bg-background/60 px-2 py-1 text-[11px] text-muted-foreground">
            <div className="mb-0.5 text-[10px] font-medium">原文证据:</div>
            <div className="leading-relaxed">{data.evidence_snippet}</div>
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
            <Button
              size="sm"
              disabled={inFlight}
              onClick={() => void adopt.run()}
            >
              {inFlight ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : (
                <CheckCircle2 className="mr-1 size-3" />
              )}
              采纳并落库
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
