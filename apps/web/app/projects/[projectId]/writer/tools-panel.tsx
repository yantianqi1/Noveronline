"use client";

import {
  BookMarked,
  Download,
  FileDown,
  Loader2,
  Plus,
  RefreshCw,
  ShieldOff,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  createForbiddenEntry,
  createManuscriptExport,
  deleteForbiddenEntry,
  fetchDedupPatterns,
  fetchForbiddenEntries,
  fetchManuscriptExports,
  fetchWriterPresets,
  reviewDedupPattern,
  setForbiddenEntryEnabled,
  setWriterPresetEnabled,
} from "@/lib/api/writer-client";
import type {
  DedupPattern,
  ForbiddenEntry,
  ManuscriptExport,
  WriterPreset,
} from "@/lib/api/writer-types";

/**
 * The tools view (工具) — the canvas's fourth live view. Four quiet cards for
 * the work that supports the manuscript rather than the manuscript itself:
 * export the manuscript, keep the forbidden-lexicon, manage writer presets,
 * and triage duplicate-phrase candidates. Each card owns its own fetch + busy
 * state so one slow area never blocks the others; mutations surface an honest
 * error inline rather than a silent no-op.
 */
export function ToolsPanel({
  projectId,
  tenantId,
  csrfToken,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
}) {
  return (
    <div className="mx-auto w-full max-w-[1040px] px-6 pb-16 pt-7">
      <div className="flex items-baseline gap-3">
        <h2 className="font-serif text-lg font-semibold text-ink">工具</h2>
        <span className="text-sm text-muted">导出 · 违禁词 · 预设 · 重复检测</span>
      </div>
      <p className="mt-1 text-caption text-muted-soft">
        这些是照看手稿的杂务,不常碰但得顺手。导出成稿、守住违禁词、调好写作预设、清掉重复句式。
      </p>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ExportCard projectId={projectId} tenantId={tenantId} csrfToken={csrfToken} />
        <ForbiddenLexiconCard projectId={projectId} tenantId={tenantId} csrfToken={csrfToken} />
        <PresetsCard projectId={projectId} tenantId={tenantId} csrfToken={csrfToken} />
        <DedupCard projectId={projectId} tenantId={tenantId} csrfToken={csrfToken} />
      </div>
    </div>
  );
}

// ── Shared card chrome ───────────────────────────────────────────────────────

function ToolCard({
  icon,
  title,
  hint,
  action,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  hint: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col overflow-hidden rounded-panel border border-line bg-panel">
      <header className="flex items-center gap-2.5 border-b border-line-soft px-4 py-3">
        <span className="text-accent">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="font-serif text-base font-semibold text-ink">{title}</div>
          <div className="text-micro text-muted-soft">{hint}</div>
        </div>
        {action}
      </header>
      <div className="flex-1 px-4 py-3">{children}</div>
    </section>
  );
}

function CardError({ message }: { message: string }) {
  return (
    <div className="mb-3 rounded-control border border-line bg-accent-wash px-3 py-2 text-sm text-accent" role="alert">
      {message}
    </div>
  );
}

function CardLoading({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-soft">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {text}
    </div>
  );
}

function CardEmpty({ text }: { text: string }) {
  return <div className="py-8 text-center text-sm text-muted-soft">{text}</div>;
}

// ── 导出手稿 ─────────────────────────────────────────────────────────────────

const EXPORT_FORMATS = ["txt", "docx", "pdf", "epub"] as const;

function ExportCard({
  projectId,
  tenantId,
  csrfToken,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
}) {
  const [exports, setExports] = useState<ManuscriptExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setExports(await fetchManuscriptExports(projectId, tenantId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出记录读不出来。");
    } finally {
      setLoading(false);
    }
  }, [projectId, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleStart(format: string) {
    if (!csrfToken || starting) return;
    setStarting(format);
    setError(null);
    try {
      await createManuscriptExport(projectId, tenantId, csrfToken, format);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出任务创建失败,请重试。");
    } finally {
      setStarting(null);
    }
  }

  return (
    <ToolCard
      icon={<FileDown className="size-4" aria-hidden />}
      title="导出手稿"
      hint="把整部手稿导成 txt / docx / pdf / epub"
      action={
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          aria-label="刷新"
          title="刷新"
          className="text-muted hover:text-accent disabled:opacity-50"
        >
          <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} aria-hidden />
        </button>
      }
    >
      {error ? <CardError message={error} /> : null}
      <div className="mb-3 flex flex-wrap gap-2">
        {EXPORT_FORMATS.map((format) => (
          <Button
            key={format}
            variant="outline"
            size="sm"
            disabled={!csrfToken || starting !== null}
            loading={starting === format}
            onClick={() => void handleStart(format)}
          >
            <Download className="size-4" aria-hidden /> {format}
          </Button>
        ))}
      </div>
      {loading ? (
        <CardLoading text="读取导出记录…" />
      ) : exports.length === 0 ? (
        <CardEmpty text="还没有导出过。点上面任意格式开始第一份。" />
      ) : (
        <ul className="max-h-[220px] divide-y divide-line-soft overflow-y-auto">
          {exports.map((record) => (
            <li key={record.export_id} className="flex items-center gap-2 py-2">
              <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-micro uppercase text-muted">
                {record.format}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-ink-soft">
                {record.block_count} 块 · {formatBytes(record.artifact_size_bytes)}
              </span>
              <ExportStatus status={record.status} />
            </li>
          ))}
        </ul>
      )}
    </ToolCard>
  );
}

function ExportStatus({ status }: { status: string }) {
  const { label, className } = ((): { label: string; className: string } => {
    switch (status) {
      case "completed":
        return { label: "已完成", className: "bg-success-wash text-success" };
      case "generating":
      case "queued":
        return { label: "生成中", className: "bg-candidate-wash text-candidate" };
      case "failed":
        return { label: "失败", className: "bg-danger-wash text-danger" };
      default:
        return { label: status, className: "bg-paper text-muted" };
    }
  })();
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-micro ${className}`}>{label}</span>;
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── 违禁词库 ─────────────────────────────────────────────────────────────────

function ForbiddenLexiconCard({
  projectId,
  tenantId,
  csrfToken,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
}) {
  const [entries, setEntries] = useState<ForbiddenEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setEntries(await fetchForbiddenEntries(projectId, tenantId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "违禁词读不出来。");
    } finally {
      setLoading(false);
    }
  }, [projectId, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAdd() {
    const value = term.trim();
    if (!csrfToken || !value || adding) return;
    setAdding(true);
    setError(null);
    try {
      await createForbiddenEntry(projectId, tenantId, csrfToken, { term: value, severity: "medium" });
      setTerm("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败,请重试。");
    } finally {
      setAdding(false);
    }
  }

  async function handleToggle(entry: ForbiddenEntry) {
    if (!csrfToken || busyId) return;
    setBusyId(entry.lexicon_entry_id);
    setError(null);
    try {
      await setForbiddenEntryEnabled(projectId, tenantId, csrfToken, entry, !entry.enabled);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败,请重试。");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(entry: ForbiddenEntry) {
    if (!csrfToken || busyId) return;
    setBusyId(entry.lexicon_entry_id);
    setError(null);
    try {
      await deleteForbiddenEntry(projectId, tenantId, csrfToken, entry.lexicon_entry_id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败,请重试。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <ToolCard
      icon={<ShieldOff className="size-4" aria-hidden />}
      title="违禁词库"
      hint="写稿与审校时会拦下的词"
    >
      {error ? <CardError message={error} /> : null}
      <div className="mb-3 flex gap-2">
        <input
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleAdd();
          }}
          placeholder="加一个违禁词…"
          className="min-w-0 flex-1 rounded-control border border-line bg-paper px-2.5 py-1.5 text-sm text-ink focus:outline-none"
        />
        <Button variant="primary" size="sm" disabled={!csrfToken || !term.trim()} loading={adding} onClick={() => void handleAdd()}>
          <Plus className="size-4" aria-hidden /> 添加
        </Button>
      </div>
      {loading ? (
        <CardLoading text="读取违禁词…" />
      ) : entries.length === 0 ? (
        <CardEmpty text="还没有违禁词。加一个,审校时就会盯住它。" />
      ) : (
        <ul className="max-h-[220px] divide-y divide-line-soft overflow-y-auto">
          {entries.map((entry) => (
            <li key={entry.lexicon_entry_id} className="group flex items-center gap-2 py-2">
              <span className={`min-w-0 flex-1 truncate text-sm ${entry.enabled ? "text-ink" : "text-muted-soft line-through"}`}>
                {entry.term}
              </span>
              {entry.severity ? (
                <span className="shrink-0 rounded-full bg-paper px-2 py-0.5 text-micro text-muted">{entry.severity}</span>
              ) : null}
              <button
                type="button"
                onClick={() => void handleToggle(entry)}
                disabled={!csrfToken || busyId === entry.lexicon_entry_id}
                className="shrink-0 text-micro text-muted hover:text-accent disabled:opacity-50"
              >
                {busyId === entry.lexicon_entry_id ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : entry.enabled ? "停用" : "启用"}
              </button>
              <button
                type="button"
                onClick={() => void handleDelete(entry)}
                disabled={!csrfToken || busyId === entry.lexicon_entry_id}
                aria-label="删除"
                className="shrink-0 rounded p-1 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 disabled:opacity-50"
              >
                <Trash2 className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </ToolCard>
  );
}

// ── 写作预设 ─────────────────────────────────────────────────────────────────

function PresetsCard({
  projectId,
  tenantId,
  csrfToken,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
}) {
  const [presets, setPresets] = useState<WriterPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPresets(await fetchWriterPresets(projectId, tenantId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "写作预设读不出来。");
    } finally {
      setLoading(false);
    }
  }, [projectId, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleToggle(preset: WriterPreset) {
    if (!csrfToken || busyId) return;
    setBusyId(preset.writer_preset_id);
    setError(null);
    try {
      await setWriterPresetEnabled(projectId, tenantId, csrfToken, preset, !preset.enabled);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败,请重试。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <ToolCard
      icon={<Sparkles className="size-4" aria-hidden />}
      title="写作预设"
      hint="给 Agent 的写作口味开关"
    >
      {error ? <CardError message={error} /> : null}
      {loading ? (
        <CardLoading text="读取预设…" />
      ) : presets.length === 0 ? (
        <CardEmpty text="这个项目还没有写作预设。" />
      ) : (
        <ul className="max-h-[260px] divide-y divide-line-soft overflow-y-auto">
          {presets.map((preset) => (
            <li key={preset.writer_preset_id} className="flex items-start gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className={`text-sm ${preset.enabled ? "text-ink" : "text-muted-soft"}`}>{preset.name}</div>
                {preset.description ? (
                  <div className="mt-0.5 line-clamp-2 text-micro text-muted-soft">{preset.description}</div>
                ) : null}
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={preset.enabled}
                onClick={() => void handleToggle(preset)}
                disabled={!csrfToken || busyId === preset.writer_preset_id}
                className={`mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full px-0.5 transition-colors disabled:opacity-50 ${
                  preset.enabled ? "bg-accent justify-end" : "bg-line justify-start"
                }`}
              >
                {busyId === preset.writer_preset_id ? (
                  <Loader2 className="size-3 animate-spin text-white" aria-hidden />
                ) : (
                  <span className="size-4 rounded-full bg-white shadow" />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </ToolCard>
  );
}

// ── 重复检测 ─────────────────────────────────────────────────────────────────

function DedupCard({
  projectId,
  tenantId,
  csrfToken,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
}) {
  const [patterns, setPatterns] = useState<DedupPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPatterns(await fetchDedupPatterns(projectId, tenantId, "candidate"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "重复候选读不出来。");
    } finally {
      setLoading(false);
    }
  }, [projectId, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleReview(pattern: DedupPattern, decision: "accept" | "reject") {
    if (!csrfToken || busyId) return;
    setBusyId(pattern.pattern_id);
    setError(null);
    try {
      await reviewDedupPattern(projectId, tenantId, csrfToken, pattern.pattern_id, decision);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "处理失败,请重试。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <ToolCard
      icon={<BookMarked className="size-4" aria-hidden />}
      title="重复检测"
      hint="Agent 找出的重复句式,逐条取舍"
      action={
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          aria-label="刷新"
          title="刷新"
          className="text-muted hover:text-accent disabled:opacity-50"
        >
          <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} aria-hidden />
        </button>
      }
    >
      {error ? <CardError message={error} /> : null}
      {loading ? (
        <CardLoading text="读取重复候选…" />
      ) : patterns.length === 0 ? (
        <CardEmpty text="没有待处理的重复候选。Agent 跑过去重后会列在这里。" />
      ) : (
        <ul className="max-h-[260px] divide-y divide-line-soft overflow-y-auto">
          {patterns.map((pattern) => (
            <li key={pattern.pattern_id} className="py-2.5">
              <div className="flex items-start gap-2">
                <p className="min-w-0 flex-1 truncate text-sm text-ink" title={pattern.pattern_text}>
                  {pattern.pattern_text}
                </p>
                <span className="shrink-0 rounded-full bg-candidate-wash px-2 py-0.5 font-mono text-micro text-candidate">
                  ×{pattern.occurrence_count}
                </span>
              </div>
              <div className="mt-2 flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!csrfToken || busyId === pattern.pattern_id}
                  loading={busyId === pattern.pattern_id}
                  onClick={() => void handleReview(pattern, "accept")}
                >
                  保留
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!csrfToken || busyId === pattern.pattern_id}
                  onClick={() => void handleReview(pattern, "reject")}
                >
                  去除
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </ToolCard>
  );
}
