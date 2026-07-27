"use client";

import { AnimatePresence, motion } from "motion/react";
import { Check, RefreshCw, ScrollText, X } from "lucide-react";
import { useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ReadinessSnapshot, SeedRun, WorkflowEvent } from "@/lib/api/overview-types";
import { runStatusLabel, type EnrichmentProgress, type SeedProgress } from "@/lib/api/seed";

import { SeedLogModal } from "./seed-log-modal";

/**
 * Seed analysis progress, redesigned as "墨径" — an ink trail.
 *
 * A vermilion ink line winds across the card through all eleven stages. As the
 * pipeline advances, the ink flows forward: completed stages are solid ink
 * seals the line has already passed through, the active stage is a breathing
 * pool of wet ink, and pending stages are dry hollow traces. The line itself is
 * drawn with an animated stroke so progress reads as ink spreading across
 * paper, not a row of static dots. Failure marks the stage where the ink
 * blotted and stopped. Honest states only — a failed run's ink halts; it never
 * pretends to have reached the end.
 */
export function SeedProgressPanel({
  progress,
  run,
  events,
  readiness,
  busy,
  onCancel,
  onRetry,
  canAct,
}: {
  progress: SeedProgress;
  run: SeedRun | null;
  events: WorkflowEvent[];
  readiness: ReadinessSnapshot | null;
  busy: boolean;
  onCancel: (runId: string) => void;
  onRetry: (runId: string) => void;
  canAct: boolean;
}) {
  const gradientId = useId();
  const [logOpen, setLogOpen] = useState(false);
  const running = progress.terminal === "running";
  const failed = progress.terminal === "failed";
  const stalled = progress.terminal === "stalled";
  const completed = progress.terminal === "completed";
  const activeStage = progress.activeIndex >= 0 ? progress.stages[progress.activeIndex] : null;

  // Overall fill of the ink trail, 0..1. Derived from percent so the line
  // length matches the dial elsewhere in the workbench.
  const fill = Math.min(1, Math.max(0, progress.percent / 100));

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
      className="overflow-hidden rounded-modal border border-line bg-panel shadow-hairline"
    >
      {/* header: title + status + actions */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line-soft px-7 py-5">
        <div className="min-w-0">
          <h2 className="font-serif text-lg font-semibold text-ink">分析进度</h2>
          <p className="mt-1 truncate text-sm text-muted" title={progress.headline}>
            {progress.headline}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {failed && <StatusChip tone="failed" label="失败" />}
          {stalled && <StatusChip tone="failed" label="已卡住" />}
          {completed && <StatusChip tone="done" label="已完成" />}
          {running && <StatusChip tone="running" label={`${progress.percent}%`} />}
          {events.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setLogOpen(true)}>
              <ScrollText className="size-3.5" aria-hidden />
              查看日志
            </Button>
          )}
          {run && canAct && running && (
            <Button variant="outline" size="sm" onClick={() => onCancel(run.run_id)} loading={busy}>
              取消
            </Button>
          )}
          {run && canAct && failed && (
            <Button variant="outline" size="sm" onClick={() => onRetry(run.run_id)} loading={busy}>
              <RefreshCw className="size-3.5" aria-hidden />
              重试
            </Button>
          )}
        </div>
      </div>

      {/* the ink trail */}
      <div className="px-4 py-8 sm:px-8">
        <InkTrail progress={progress} gradientId={gradientId} fill={fill} running={running} />
      </div>

      {/* active stage detail (sequential reading) */}
      <AnimatePresence>
        {running && progress.sequentialReading && progress.sequentialReading.total > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden border-t border-line-soft"
          >
            <div className="mx-7 my-5 rounded-panel border border-line-soft bg-paper/60 px-4 py-3">
              <div className="flex items-center justify-between text-caption">
                <span className="text-muted">
                  {progress.sequentialReading.chapterGuess
                    ? `正在读「${progress.sequentialReading.chapterGuess}」`
                    : "正在精读段落"}
                </span>
                <span className="font-medium text-ink">
                  {progress.sequentialReading.completed}/{progress.sequentialReading.total}
                </span>
              </div>
              <div className="mt-2 h-[4px] overflow-hidden rounded-full bg-paper-deep">
                <motion.div
                  className="h-full rounded-full bg-accent"
                  animate={{
                    width: `${Math.round(
                      (progress.sequentialReading.completed / progress.sequentialReading.total) * 100,
                    )}%`,
                  }}
                  transition={{ duration: 0.4 }}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* batched enrichment sub-progress (character profiles / archive candidates) */}
      <EnrichmentBlock running={running} progress={progress.agentProfiles} />
      <EnrichmentBlock running={running} progress={progress.archiveCandidates} />

      {/* whole-book coverage: surface skipped chapters instead of letting a
          partial read pass as complete. Shown once the run is no longer live
          and the snapshot has produced segment counts. */}
      {!running && <CoverageBlock readiness={readiness} run={run} onRetry={onRetry} busy={busy} canAct={canAct} />}

      {run && (
        <div className="border-t border-line-soft px-7 py-3">
          <p className="text-caption tracking-wide text-muted-soft">{runStatusLabel(run)} · 分析由 Seed 流水线驱动</p>
        </div>
      )}

      {/* stalled guidance: a stage failed but the run row still says running, so
          retry is genuinely unavailable — offer the one action that works here
          (cancel the wedged run so it becomes retryable) plus a refresh. */}
      {stalled && run && (
        <div className="border-t border-line-soft bg-paper/40 px-7 py-4">
          <p className="text-caption leading-relaxed text-muted">
            这一步的进度状态没有正常更新，所以暂时无法直接重试。已读出的内容不会丢。取消这次卡住的分析后，就能重新开始了。
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {canAct && (
              <Button variant="outline" size="sm" onClick={() => onCancel(run.run_id)} loading={busy}>
                <X className="size-3.5" aria-hidden />
                取消这次分析
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
              <RefreshCw className="size-3.5" aria-hidden />
              刷新页面
            </Button>
          </div>
        </div>
      )}

      <SeedLogModal
        open={logOpen}
        run={run}
        events={events}
        live={running}
        onClose={() => setLogOpen(false)}
      />
    </motion.section>
  );
}

/* -------------------------------------------------------------------------- */
/*  Batched enrichment sub-progress                                            */
/* -------------------------------------------------------------------------- */

/**
 * A slim progress strip for a batched enrichment stage (character profiles,
 * archive candidates). The backend already localizes the status line (e.g.
 * "正在生成角色档案 5/7 · 角色00"), so this renders that message verbatim and a
 * thin fill bar — it appears only while the run is live and the stage has
 * reported a real total.
 */
function EnrichmentBlock({
  running,
  progress,
}: {
  running: boolean;
  progress: EnrichmentProgress | null;
}) {
  return (
    <AnimatePresence>
      {running && progress && progress.total > 0 && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.3 }}
          className="overflow-hidden border-t border-line-soft"
        >
          <div className="mx-7 my-5 rounded-panel border border-line-soft bg-paper/60 px-4 py-3">
            <div className="flex items-center justify-between gap-3 text-caption">
              <span className="truncate text-muted" title={progress.message}>
                {progress.message}
              </span>
              <span className="shrink-0 font-medium text-ink">
                {progress.completed}/{progress.total}
              </span>
            </div>
            <div className="mt-2 h-[4px] overflow-hidden rounded-full bg-paper-deep">
              <motion.div
                className="h-full rounded-full bg-accent"
                animate={{
                  width: `${Math.round((progress.completed / progress.total) * 100)}%`,
                }}
                transition={{ duration: 0.4 }}
              />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* -------------------------------------------------------------------------- */
/*  Whole-book coverage                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Coverage reconciliation strip: how many chapters were read out of the whole
 * book, and which segment ids were skipped. Rendered only once the run is no
 * longer live and the readiness snapshot has produced segment counts. A full
 * read shows a quiet confirmation; a partial read lists the missed segment ids
 * in red and offers a retry (re-running the seed re-reads missing chapters).
 */
function CoverageBlock({
  readiness,
  run,
  onRetry,
  busy,
  canAct,
}: {
  readiness: ReadinessSnapshot | null;
  run: SeedRun | null;
  onRetry: (runId: string) => void;
  busy: boolean;
  canAct: boolean;
}) {
  const coverage = readiness?.coverage;
  if (!coverage || coverage.total_segment_count <= 0) return null;

  const total = coverage.total_segment_count;
  const succeeded = coverage.succeeded_segment_count;
  const failedIds = coverage.failed_segment_ids ?? [];
  const complete = succeeded >= total && failedIds.length === 0;

  return (
    <div className="border-t border-line-soft px-7 py-4">
      {complete ? (
        <p className="text-caption text-muted">
          全书 <span className="font-medium text-ink">{total}</span> 章已全部拆解完成。
        </p>
      ) : (
        <div className="rounded-panel border border-accent/30 bg-accent-wash/40 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-caption text-ink">
              已拆解 <span className="font-semibold text-accent">{succeeded}/{total}</span> 章，
              <span className="text-accent"> {failedIds.length > 0 ? `${failedIds.length} 章` : `部分章节`}</span>
              没有读成功，这些章的内容不会进资产库。
            </p>
            {run && canAct && (
              <Button variant="outline" size="sm" onClick={() => onRetry(run.run_id)} loading={busy}>
                <RefreshCw className="size-3.5" aria-hidden />
                重新分析补齐
              </Button>
            )}
          </div>
          {failedIds.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {failedIds.slice(0, 24).map((id) => (
                <span
                  key={id}
                  className="rounded-control border border-accent/30 bg-panel px-1.5 py-0.5 font-mono text-caption text-accent"
                >
                  {shortSegmentId(id)}
                </span>
              ))}
              {failedIds.length > 24 && (
                <span className="px-1 py-0.5 text-caption text-muted">+{failedIds.length - 24} 章</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Segment ids are long; show a readable tail so chapters stay distinguishable. */
function shortSegmentId(id: string): string {
  if (id.length <= 12) return id;
  return `…${id.slice(-8)}`;
}

/* -------------------------------------------------------------------------- */
/*  Ink trail geometry                                                         */
/* -------------------------------------------------------------------------- */

const VW = 1200; // viewBox width
const VH = 190; // viewBox height
const ROWS = [
  { y: 46, count: 6 }, // top row: 6 stages, left → right
  { y: 144, count: 5 }, // bottom row: 5 stages, right → left
];
const X_START = 110;
const X_END = VW - 110;

type Pt = { x: number; y: number };

/** Distribute stage anchors along a two-row serpentine path. */
function stageAnchors(total: number): Pt[] {
  const pts: Pt[] = [];
  const top = ROWS[0];
  const bottom = ROWS[1];
  for (let i = 0; i < top.count; i++) {
    const t = top.count === 1 ? 0 : i / (top.count - 1);
    pts.push({ x: X_START + t * (X_END - X_START), y: top.y });
  }
  for (let i = 0; i < bottom.count; i++) {
    const t = bottom.count === 1 ? 0 : i / (bottom.count - 1);
    // bottom row runs right → left so the trail snakes back.
    pts.push({ x: X_END - t * (X_END - X_START), y: bottom.y });
  }
  return pts.slice(0, total);
}

/** Build a smooth path through the anchors with a connector dip between rows. */
function trailPath(anchors: Pt[]): string {
  if (anchors.length === 0) return "";
  const topCount = ROWS[0].count;
  let d = `M ${anchors[0].x} ${anchors[0].y}`;
  // top row straight segments
  for (let i = 1; i < Math.min(topCount, anchors.length); i++) {
    d += ` L ${anchors[i].x} ${anchors[i].y}`;
  }
  // connector from end of top row down to start of bottom row (right side)
  if (anchors.length > topCount) {
    const topEnd = anchors[topCount - 1];
    const bottomStart = anchors[topCount];
    const midY = (topEnd.y + bottomStart.y) / 2;
    d += ` C ${topEnd.x} ${midY}, ${bottomStart.x} ${midY}, ${bottomStart.x} ${bottomStart.y}`;
    // bottom row straight segments (right → left)
    for (let i = topCount + 1; i < anchors.length; i++) {
      d += ` L ${anchors[i].x} ${anchors[i].y}`;
    }
  }
  return d;
}

function InkTrail({
  progress,
  gradientId,
  fill,
  running,
}: {
  progress: SeedProgress;
  gradientId: string;
  fill: number;
  running: boolean;
}) {
  const anchors = stageAnchors(progress.stages.length);
  const path = trailPath(anchors);
  const failedColor = "#b04a42";
  const inkColor = "#7a1a15";

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${VW} ${VH}`}
        className="h-auto w-full"
        role="img"
        aria-label={`分析进度 ${progress.percent}%`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#8f211b" />
            <stop offset="100%" stopColor="#7a1a15" />
          </linearGradient>
        </defs>

        {/* dry track — the full path the ink will travel */}
        <path
          d={path}
          fill="none"
          stroke="rgba(86,69,45,0.18)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="0.5 7"
        />

        {/* wet ink — animated stroke that flows forward with progress */}
        <motion.path
          d={path}
          fill="none"
          stroke={progress.terminal === "failed" || progress.terminal === "stalled" ? failedColor : `url(#${gradientId})`}
          strokeWidth="3.5"
          strokeLinecap="round"
          pathLength={1}
          initial={{ strokeDasharray: "0 1" }}
          animate={{ strokeDasharray: `${Math.max(0.001, fill)} 1` }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
        />

        {/* traveling "reading" pulse — a bright dash that runs the whole trail
            while the pipeline is live, so the line visibly works. */}
        {running && (
          <motion.path
            d={path}
            fill="none"
            stroke="#a5261c"
            strokeWidth="3"
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray="0.05 0.95"
            initial={{ strokeDashoffset: 0.05, opacity: 0 }}
            animate={{ strokeDashoffset: -1, opacity: [0, 1, 1, 0] }}
            transition={{
              strokeDashoffset: { duration: 3.2, repeat: Infinity, ease: "linear" },
              opacity: { duration: 3.2, repeat: Infinity, times: [0, 0.08, 0.9, 1] },
            }}
            style={{ filter: "drop-shadow(0 0 4px rgba(165,38,28,0.6))" }}
          />
        )}

        {/* stage nodes */}
        {anchors.map((pt, i) => {
          const stage = progress.stages[i];
          const active = i === progress.activeIndex;
          return (
            <StageSeal
              key={stage.key}
              x={pt.x}
              y={pt.y}
              status={stage.status}
              active={active}
              inkColor={inkColor}
              failedColor={failedColor}
              index={i}
            />
          );
        })}
      </svg>

      {/* labels — absolutely positioned under/over anchors, aligned to the svg */}
      <div className="pointer-events-none absolute inset-0 hidden select-none sm:block">
        {anchors.map((pt, i) => {
          const stage = progress.stages[i];
          const active = i === progress.activeIndex;
          const topRow = i < ROWS[0].count;
          const leftPct = (pt.x / VW) * 100;
          const topPct = (pt.y / VH) * 100;
          // Keep the first and last labels inside the card instead of clipping
          // at the edges: near-left anchors pin left, near-right pin right.
          const edge: "left" | "right" | "center" =
            leftPct < 9 ? "left" : leftPct > 91 ? "right" : "center";
          const alignStyle =
            edge === "left"
              ? { left: `${leftPct}%`, transform: "translateX(0)" }
              : edge === "right"
                ? { left: `${leftPct}%`, transform: "translateX(-100%)" }
                : { left: `${leftPct}%`, transform: "translateX(-50%)" };
          return (
            <span
              key={stage.key}
              className={`absolute whitespace-nowrap text-caption transition-colors ${
 active
                  ? "font-semibold text-ink"
                  : stage.status === "completed"
                    ? "text-ink-soft"
                    : stage.status === "failed"
                      ? "text-accent"
                      : "text-muted-soft"
              }`}
              style={{
                ...alignStyle,
                top: topRow ? `calc(${topPct}% - 30px)` : `calc(${topPct}% + 18px)`,
              }}
            >
              {stage.label}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function StageSeal({
  x,
  y,
  status,
  active,
  inkColor,
  failedColor,
  index,
}: {
  x: number;
  y: number;
  status: "pending" | "active" | "completed" | "failed";
  active: boolean;
  inkColor: string;
  failedColor: string;
  index: number;
}) {
  if (status === "completed") {
    return (
      <motion.g
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: index * 0.06, type: "spring", stiffness: 300, damping: 18 }}
        style={{ transformOrigin: `${x}px ${y}px` }}
      >
        <circle cx={x} cy={y} r="11" fill={inkColor} />
        <path
          d={`M ${x - 4.5} ${y} l 3 3 l 6 -6`}
          fill="none"
          stroke="#fffdf8"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </motion.g>
    );
  }
  if (status === "failed") {
    return (
      <motion.g
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 16 }}
        style={{ transformOrigin: `${x}px ${y}px` }}
      >
        <circle cx={x} cy={y} r="12" fill={failedColor} />
        <path
          d={`M ${x - 4} ${y - 4} L ${x + 4} ${y + 4} M ${x + 4} ${y - 4} L ${x - 4} ${y + 4}`}
          stroke="#fffdf8"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </motion.g>
    );
  }
  if (active) {
    // wet, breathing pool of ink
    return (
      <g>
        <motion.circle
          cx={x}
          cy={y}
          r="11"
          fill="none"
          stroke={inkColor}
          strokeWidth="2"
          animate={{ r: [11, 16, 11], opacity: [0.8, 0, 0.8] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.circle
          cx={x}
          cy={y}
          r="7"
          fill={inkColor}
          animate={{ scale: [1, 1.15, 1] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          style={{ transformOrigin: `${x}px ${y}px` }}
        />
      </g>
    );
  }
  // pending — a dry hollow trace
  return (
    <circle
      cx={x}
      cy={y}
      r="9"
      fill="#fffdf8"
      stroke="rgba(86,69,45,0.3)"
      strokeWidth="1.5"
      strokeDasharray="2 3"
    />
  );
}

/**
 * Run status. "已完成" and "失败" were previously both solid vermilion, which
 * meant the colour said nothing about the outcome — the icon was doing all the
 * work. Success now reads green, failure danger-red, in progress neutral gold,
 * each still paired with an icon so colour is never the only signal.
 */
function StatusChip({
  tone,
  label,
}: {
  tone: "running" | "failed" | "done";
  label: string;
}) {
  return (
    <Badge tone={tone === "failed" ? "danger" : tone === "done" ? "success" : "warning"}>
      {tone === "done" && <Check className="size-3" aria-hidden />}
      {tone === "failed" && <X className="size-3" aria-hidden />}
      {label}
    </Badge>
  );
}
