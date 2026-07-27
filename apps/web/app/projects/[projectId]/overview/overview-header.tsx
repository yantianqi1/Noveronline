"use client";

import { motion } from "motion/react";

import { Eyebrow } from "@/components/ui/badge";
import type { ProjectOverview, ReadinessSnapshot } from "@/lib/api/overview-types";
import type { SeedProgress } from "@/lib/api/seed";

/**
 * Overview masthead: the workbench eyebrow + title, a one-line stage hint, and
 * a compact readiness strip (source files, ready entities/relationships/rules,
 * graph nodes/edges). Counts are honest — they read straight from the API and
 * render as "—" only while a snapshot hasn't been produced yet.
 */
export function OverviewHeader({
  overview,
  readiness,
  progress,
  hasRun,
}: {
  overview: ProjectOverview | null;
  readiness: ReadinessSnapshot | null;
  progress: SeedProgress;
  hasRun: boolean;
}) {
  const stageHint = headerHint(overview, progress, hasRun);

  return (
    <motion.header
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-line-soft px-6 py-3"
    >
      <div className="flex min-w-0 items-center gap-3">
        <Eyebrow>总览</Eyebrow>
        <h1 className="shrink-0 font-serif text-lg font-semibold text-ink">导入与分析</h1>
        <span aria-hidden className="h-4 w-px shrink-0 bg-line" />
        <p title={stageHint} className="min-w-0 truncate text-caption text-muted">
          {stageHint}
        </p>
      </div>

      {/* readiness strip */}
      <dl className="flex shrink-0 flex-wrap items-stretch gap-px overflow-hidden rounded-panel border border-line bg-line-soft shadow-hairline">
        <Stat label="原文" value={count(overview?.source_file_count)} />
        <CoverageStat overview={overview} readiness={readiness} />
        <Stat label="实体" value={count(readiness?.ready_entity_count ?? overview?.ready_entity_count)} accent />
        <Stat label="关系" value={count(readiness?.ready_relationship_count ?? overview?.ready_relationship_count)} accent />
        <Stat label="世界规则" value={count(readiness?.ready_world_rule_count ?? overview?.ready_world_rule_count)} accent />
        <Stat label="图谱节点" value={count(overview?.graph_node_count)} />
        <Stat label="图谱边" value={count(overview?.graph_edge_count)} />
      </dl>
    </motion.header>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex min-w-[70px] flex-col items-center gap-0.5 bg-panel px-3 py-1.5">
      <dd
        className={`font-serif text-md font-semibold ${
 accent ? "text-accent-strong" : "text-ink"
        }`}
      >
        {value}
      </dd>
      <dt className="text-caption tracking-wide text-muted">{label}</dt>
    </div>
  );
}

/**
 * Whole-book reading coverage: "已拆解 X/Y". Reads from the readiness
 * snapshot's coverage block when present, else the overview row. Renders "—"
 * until a snapshot has produced segment counts, and turns red when some
 * chapters were skipped (succeeded < total) so a partial read can't pass as
 * complete.
 */
function CoverageStat({
  overview,
  readiness,
}: {
  overview: ProjectOverview | null;
  readiness: ReadinessSnapshot | null;
}) {
  const total = readiness?.coverage?.total_segment_count ?? overview?.total_segment_count;
  const succeeded =
    readiness?.coverage?.succeeded_segment_count ?? overview?.succeeded_segment_count;
  if (total === undefined || total === null || total === 0) {
    return <Stat label="已拆解" value="—" />;
  }
  const done = succeeded ?? 0;
  const incomplete = done < total;
  return (
    <div className="flex min-w-[70px] flex-col items-center gap-0.5 bg-panel px-3 py-1.5">
      <dd
        title={incomplete ? `有 ${total - done} 章未拆解成功` : undefined}
        className={`font-serif text-md font-semibold ${
 incomplete ? "text-accent" : "text-ink"
        }`}
      >
        {done}/{total}
      </dd>
      <dt className="text-caption tracking-wide text-muted">已拆解</dt>
    </div>
  );
}

function count(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return String(value);
}

function headerHint(
  overview: ProjectOverview | null,
  progress: SeedProgress,
  hasRun: boolean,
): string {
  if (!overview || overview.source_file_count === 0) {
    return "把小说原文放上来，开始第一次分析。分析会读出人物、关系、伏笔与世界规则，搭起这部作品的底子。";
  }
  if (progress.terminal === "running") {
    return progress.headline;
  }
  if (progress.terminal === "failed") {
    return "上次分析没有走完。看看失败原因，修好后重试——已读出的部分不会丢。";
  }
  if (progress.terminal === "stalled") {
    return "上次分析中途卡住，进度状态没有更新。取消这次卡住的分析，就能重新开始。";
  }
  if (hasRun) {
    return "分析已完成。故事素材已经就绪，可以去图谱、资产库或写作台继续。";
  }
  return "原文已就位，可以开始分析了。";
}
