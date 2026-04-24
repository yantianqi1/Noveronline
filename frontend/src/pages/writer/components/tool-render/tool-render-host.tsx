/**
 * ToolRenderHost — dispatches a `ToolRenderPayload` to the matching card
 * component. Used inside `ToolCallItem` in the agent-trace panel.
 *
 * Unknown payload versions fall back to a placeholder so partial schema
 * drift never blocks the UI.
 */

import { isRender, type ToolRenderPayload } from "@/types/writer";

import { ChapterStructureProposalCard } from "./chapter-structure-proposal-card";
import { EntityCard } from "./entity-card";
import { ProseDiffView } from "./prose-diff-view";
import { RelationSubgraphCard } from "./relation-subgraph-card";
import { RelationshipProposalCard } from "./relationship-proposal-card";
import { SceneProposalCard } from "./scene-proposal-card";
import { SceneTimelineCard } from "./scene-timeline-card";
import { WordBudgetGauge } from "./word-budget-gauge";
import type { RenderHostContext } from "./types";

export interface ToolRenderHostProps {
  payload: ToolRenderPayload;
  context: RenderHostContext;
  /** Raw LLM text for fallback when payload is unsupported. */
  fullResult?: string;
}

export function ToolRenderHost({ payload, context, fullResult }: ToolRenderHostProps) {
  if (!payload || typeof payload !== "object") {
    return (
      <pre className="whitespace-pre-wrap break-all p-2 font-mono text-[11px] leading-relaxed">
        {fullResult}
      </pre>
    );
  }

  if (payload.version !== 1) {
    return (
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-[11px] text-amber-700 dark:text-amber-200">
        <div className="font-medium">render 版本不兼容: v{payload.version}</div>
        <div className="text-muted-foreground">
          客户端仅支持 v1；请升级前端或降级后端 render 输出。
        </div>
        {fullResult && (
          <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-[10px] opacity-70">
            {fullResult}
          </pre>
        )}
      </div>
    );
  }

  if (isRender(payload, "scene_proposal")) {
    return <SceneProposalCard data={payload.data} actions={payload.actions} context={context} />;
  }
  if (isRender(payload, "chapter_structure_proposal")) {
    return (
      <ChapterStructureProposalCard
        data={payload.data}
        actions={payload.actions}
        context={context}
      />
    );
  }
  if (isRender(payload, "prose_diff")) {
    return <ProseDiffView data={payload.data} actions={payload.actions} context={context} />;
  }
  if (isRender(payload, "word_budget")) {
    return <WordBudgetGauge data={payload.data} actions={payload.actions} context={context} />;
  }
  if (isRender(payload, "entity_card")) {
    return <EntityCard data={payload.data} actions={payload.actions} context={context} />;
  }
  if (isRender(payload, "relationship_proposal")) {
    return (
      <RelationshipProposalCard
        data={payload.data}
        actions={payload.actions}
        context={context}
      />
    );
  }
  if (isRender(payload, "relation_subgraph")) {
    return (
      <RelationSubgraphCard
        data={payload.data}
        actions={payload.actions}
        context={context}
      />
    );
  }
  if (isRender(payload, "scene_timeline")) {
    return (
      <SceneTimelineCard
        data={payload.data}
        actions={payload.actions}
        context={context}
      />
    );
  }

  // Unhandled-but-valid types (thread_board): show the
  // textual result as a graceful fallback.
  return (
    <div className="space-y-1 rounded-md border border-border/40 bg-muted/30 p-2 text-[11px]">
      <div className="font-medium text-muted-foreground">
        {payload.type} · 卡片组件将在后续阶段上线
      </div>
      {fullResult && (
        <pre className="whitespace-pre-wrap break-all font-mono text-[10px] opacity-80">
          {fullResult}
        </pre>
      )}
    </div>
  );
}
