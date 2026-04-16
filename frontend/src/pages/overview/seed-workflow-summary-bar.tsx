import { STAGE_TO_CHAPTER, type ChapterViewModel } from "./seed-pipeline-chapters";

export default function SeedWorkflowSummaryBar({
  chapters,
  activeStageKey,
}: {
  chapters: ChapterViewModel[];
  activeStageKey: string;
}) {
  const chapter = resolveChapter(chapters, activeStageKey);
  const completed = chapter.steps.filter((step) => step.status === "completed").length;
  const percent = chapter.stepCount === 0 ? 0 : Math.round((completed / chapter.stepCount) * 100);

  return (
    <header className="rounded-lg border border-red-900/10 bg-white px-3 py-2 shadow-sm">
      <div className="flex items-center gap-3 min-h-[28px] flex-wrap">
        <span className="font-serif text-sm text-foreground whitespace-nowrap">
          {chapter.label}
        </span>
        <div className="flex-1 min-w-[60px]">
          <div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
            <div
              className="seed-progress-flow h-full rounded-full bg-red-700 transition-[width] duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
        <Metric text={`${completed}/${chapter.stepCount} 步骤`} />
        <Metric text={formatMs(chapter.elapsedMs)} />
        <Metric text={`${chapter.llmCallCount}次LLM`} />
      </div>
    </header>
  );
}

function resolveChapter(chapters: ChapterViewModel[], activeStageKey: string): ChapterViewModel {
  const chapterKey = STAGE_TO_CHAPTER[activeStageKey] || "text_prep";
  return chapters.find((chapter) => chapter.key === chapterKey) || {
    key: "text_prep",
    label: "文本准备",
    status: "pending",
    steps: [],
    stepCount: 0,
    elapsedMs: 0,
    llmCallCount: 0,
  };
}

function Metric({ text }: { text: string }) {
  return (
    <span className="font-mono text-[11px] text-muted-foreground whitespace-nowrap">
      {text}
    </span>
  );
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const rem = Math.round(sec % 60);
  return `${min}m${rem}s`;
}
