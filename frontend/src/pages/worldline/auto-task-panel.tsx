import * as React from "react";

import { cn } from "@/lib/utils";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface TaskSnapshot {
  branch_title?: string;
  status?: string;
  progress?: number;
  error?: string;
  message?: string;
  stop_reason?: string;
}

interface AutoTaskPanelProps {
  task: TaskSnapshot | null;
}

/* ================================================================ */
/*  Helpers                                                          */
/* ================================================================ */

const STATUS_LABELS: Record<string, string> = {
  idle: "待命",
  pending: "连接中",
  processing: "演化中",
  completed: "已完成",
  failed: "失败",
};

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function AutoTaskPanel({ task }: AutoTaskPanelProps) {
  if (!task) return null;

  const isStreaming =
    task.status === "pending" || task.status === "processing";
  const progress = task.progress || 0;

  return (
    <section className="flex flex-col gap-3.5 p-3 border border-amber-300/20 rounded-lg bg-gradient-to-b from-amber-50/85 to-white/95">
      <div className="flex justify-between gap-2 items-start">
        <div>
          <p className="font-mono text-xs text-amber-700 tracking-widest">
            03 / 自动演化
          </p>
          <h3 className="text-[0.95rem] font-semibold text-stone-800 mt-0.5">
            当前世界自动推进
          </h3>
        </div>
        <p className="text-xs text-stone-500">
          SSE 流式推进后，候选事件会出现在右侧导演台等待审核。
        </p>
      </div>

      {/* Task card */}
      <article
        className={cn(
          "border rounded-xl p-3 bg-white/90 flex flex-col gap-2",
          task.status === "processing" && "border-amber-500/30",
          task.status === "completed" && "border-blue-500/20",
          task.status === "failed" && "border-red-600/25",
          !task.status && "border-stone-200",
        )}
      >
        <div className="flex justify-between gap-3 items-center">
          <strong className="text-sm">{task.branch_title || "当前世界"}</strong>
          <span className="font-mono px-2 py-0.5 rounded-full bg-amber-200/80 text-amber-800 text-xs">
            {STATUS_LABELS[task.status || ""] || "处理中"}
          </span>
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 rounded-full bg-amber-300/15 overflow-hidden">
            <div
              className={cn(
                "h-full bg-gradient-to-r from-amber-500 to-amber-700 transition-all duration-400",
                isStreaming && "animate-pulse",
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="font-mono text-xs text-stone-500">{progress}%</span>
        </div>

        <p className="text-xs text-stone-500 m-0">
          {task.error || task.message || "等待任务状态..."}
        </p>
        {task.stop_reason && (
          <p className="font-mono text-xs text-stone-400 m-0">
            stop: {task.stop_reason}
          </p>
        )}
      </article>
    </section>
  );
}
