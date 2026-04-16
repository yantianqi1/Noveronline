/**
 * PipelineVisualization — full or compact pipeline stage display.
 */

import { cn } from "@/lib/utils";
import type { ActiveStage } from "@/lib/seed-upload-task-state";
import {
  buildFullPipelineNodes,
  buildPipelineRailWindow,
  type PipelineNode,
  type RailEntry,
} from "./overview-workbench-state";

/* ---------- Props ---------- */

interface PipelineVisualizationProps {
  uploadPhase?: string;
  taskStatus?: string;
  activeStage?: ActiveStage;
  compact?: boolean;
}

/* ---------- Helpers ---------- */

function formatNodeState(state: string): string {
  if (state === "done") return "已完成";
  if (state === "active") return "当前";
  if (state === "failed") return "中断";
  return "待命";
}

function resolveHeadline(
  uploadPhase: string,
  taskStatus: string,
  activeStage?: ActiveStage,
): string {
  if (uploadPhase === "uploading")
    return "文件正在上传，上传完成后会自动进入后台分析。";
  if (taskStatus === "processing") {
    return activeStage?.label
      ? `当前焦点：${activeStage.label}`
      : "后台正在依次推进骨架扫描、事实提取与种子聚合。";
  }
  if (taskStatus === "completed" || uploadPhase === "success")
    return "分析已完成，可以查看档案和分析结果。";
  if (taskStatus === "failed" || uploadPhase === "error")
    return "当前轮次中断了，完整卷宗会保留失败阶段。";
  return "等待新的分析任务启动。";
}

const stateClasses: Record<string, string> = {
  pending: "border-border/60 bg-card/60 opacity-90",
  active:
    "border-amber-500/40 bg-gradient-to-b from-amber-50 to-amber-50/30 shadow-md -translate-y-0.5",
  done: "border-emerald-500/25 bg-emerald-50/80",
  failed: "border-red-500/35 bg-red-50/90",
};

const barClasses: Record<string, string> = {
  pending: "bg-muted-foreground/20",
  active: "bg-gradient-to-r from-amber-500 to-amber-300",
  done: "bg-gradient-to-r from-emerald-600 to-emerald-400",
  failed: "bg-gradient-to-r from-red-600 to-red-400",
};

const chipClasses: Record<string, string> = {
  pending: "bg-muted text-muted-foreground",
  active: "bg-amber-100 text-amber-700",
  done: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

/* ---------- Component ---------- */

export default function PipelineVisualization({
  uploadPhase = "idle",
  taskStatus = "",
  activeStage,
  compact = false,
}: PipelineVisualizationProps) {
  const context = { uploadPhase, taskStatus, activeStage };
  const fullNodes = buildFullPipelineNodes(context);
  const railItems = buildPipelineRailWindow(context).items;
  const headline = resolveHeadline(uploadPhase, taskStatus, activeStage);

  return (
    <section
      className={cn(
        "mt-3 rounded-xl border p-3 bg-gradient-to-b from-amber-50/60 to-background",
        compact && "p-2.5",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-serif text-lg font-semibold">
            {compact ? "当前阶段轨道" : "分析流程"}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{headline}</p>
        </div>
        {!compact && (
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              待命
            </span>
            <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs text-amber-700">
              进行中
            </span>
            <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs text-emerald-700">
              已完成
            </span>
          </div>
        )}
      </div>

      {/* Pipeline nodes */}
      {compact ? (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2 items-stretch">
          {railItems.map((item) =>
            item.kind === "node" ? (
              <CompactNode key={item.stage} node={item as PipelineNode & { kind: "node" }} />
            ) : (
              <SummaryPill
                key={`${item.state}_${item.count}`}
                state={item.state}
                label={item.label}
              />
            ),
          )}
        </div>
      ) : (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {fullNodes.map((node) => (
            <FullNode key={node.stage} node={node} />
          ))}
        </div>
      )}
    </section>
  );
}

/* ---------- Sub-components ---------- */

function CompactNode({ node }: { node: PipelineNode }) {
  return (
    <article
      className={cn(
        "relative min-h-[5.5rem] rounded-lg border p-2.5 flex flex-col justify-between gap-1.5 overflow-hidden transition-transform",
        stateClasses[node.state],
      )}
      title={node.tooltip}
    >
      <div className={cn("absolute inset-x-0 top-0 h-1", barClasses[node.state])} />
      <span className="font-mono text-xs text-muted-foreground">
        {String(node.sequence).padStart(2, "0")}
      </span>
      <strong className="text-sm">{node.title}</strong>
    </article>
  );
}

function FullNode({ node }: { node: PipelineNode }) {
  return (
    <article
      className={cn(
        "relative min-h-[7rem] rounded-lg border p-2.5 flex flex-col gap-2 overflow-hidden transition-transform",
        stateClasses[node.state],
      )}
      title={node.tooltip}
    >
      <div className={cn("absolute inset-x-0 top-0 h-1", barClasses[node.state])} />
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">
          {String(node.sequence).padStart(2, "0")}
        </span>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[11px]",
            chipClasses[node.state],
          )}
        >
          {formatNodeState(node.state)}
        </span>
      </div>
      <strong className="text-sm">{node.title}</strong>
      <small className="text-xs text-muted-foreground leading-relaxed">
        {node.detail}
      </small>
    </article>
  );
}

function SummaryPill({ state, label }: { state: string; label: string }) {
  return (
    <div
      className={cn(
        "min-h-[5.5rem] flex items-center justify-center text-center rounded-lg border border-dashed px-2.5 py-2 text-xs",
        state === "done"
          ? "bg-emerald-50/60 text-emerald-700"
          : "bg-card/60 text-muted-foreground",
      )}
    >
      {label}
    </div>
  );
}
