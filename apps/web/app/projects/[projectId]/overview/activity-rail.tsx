"use client";

import { motion } from "motion/react";
import { AlertCircle, CheckCircle2, Clock, XCircle } from "lucide-react";

import type { SeedRun } from "@/lib/api/overview-types";
import { presentRunMessage, runStatusLabel, type SeedProgress } from "@/lib/api/seed";

/**
 * Activity rail: the recent Seed runs as a quiet history, most recent first.
 * Each row shows a status seal, the run's message/status, and a relative time.
 * The active run is highlighted. Failures are shown plainly.
 */
export function ActivityRail({
  runs,
  progress,
  activeRunId,
}: {
  runs: SeedRun[];
  progress: SeedProgress;
  activeRunId?: string;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: 0.14, ease: [0.22, 1, 0.36, 1] }}
      className="overflow-hidden rounded-modal border border-line bg-panel shadow-hairline"
    >
      <div className="border-b border-line-soft px-5 py-4">
        <h2 className="font-serif text-md font-semibold text-ink">最近分析</h2>
      </div>
      {runs.length === 0 ? (
        <p className="px-5 py-6 text-caption text-muted">还没有分析记录。</p>
      ) : (
        <ul className="divide-y divide-line-soft">
          {runs.slice(0, 6).map((run) => {
            const active = run.run_id === activeRunId;
            return (
              <li
                key={run.run_id}
                className={`flex items-start gap-3 px-5 py-3.5 ${active ? "bg-accent-wash/40" : ""}`}
              >
                <StatusIcon status={run.status} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">{runStatusLabel(run)}</p>
                  <p className="mt-0.5 truncate text-caption text-muted" title={run.message}>
                    {presentRunMessage(run.message) || relativeTime(run.updated_at || run.created_at)}
                  </p>
                </div>
                <span className="shrink-0 pt-0.5 text-caption text-muted-soft">
                  {relativeTime(run.updated_at || run.created_at)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </motion.section>
  );
}

function StatusIcon({ status }: { status: string }) {
  const s = status.toLowerCase();
  if (s === "completed" || s === "succeeded") {
    return <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent-strong" aria-hidden />;
  }
  if (s === "failed" || s === "error") {
    return <XCircle className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />;
  }
  if (s === "cancelled" || s === "canceled") {
    return <AlertCircle className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />;
  }
  return <Clock className="mt-0.5 size-4 shrink-0 animate-pulse text-accent" aria-hidden />;
}

function relativeTime(iso: string): string {
  if (!iso) return "";
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000));
  if (seconds < 60) return "刚刚";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(time).toLocaleDateString("zh-CN");
}
