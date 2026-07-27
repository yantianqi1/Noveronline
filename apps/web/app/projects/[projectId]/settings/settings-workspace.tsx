"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, TriangleAlert } from "lucide-react";

import { fetchCsrfToken } from "@/lib/api/session";
import {
  createLLMChannel,
  fetchLLMBindings,
  fetchLLMChannels,
  fetchLLMModels,
  fetchLLMModules,
  LLMError,
  syncLLMChannelModels,
  updateLLMChannel,
  upsertModuleBinding,
  deleteModuleBinding,
} from "@/lib/api/llm-client";
import { readProjectSelection, type ProjectSelection } from "@/lib/api/overview-client";
import {
  enabledChannels,
  groupModules,
  summarizeBindings,
} from "@/lib/api/llm";
import type {
  LLMChannel,
  LLMModel,
  LLMModule,
  LLMModuleBinding,
} from "@/lib/api/llm-types";

import { BatchApplyBar, BatchProgress } from "./batch-apply-bar";
import { ChannelPanel, type ChannelFormValue } from "./channel-panel";
import { ModuleGroupPanel } from "./module-group-card";
import { ModuleGroupTabs } from "./module-group-tabs";
import type { ModelChoice } from "./model-picker";
import type { RowSaveState } from "./module-binding-row";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

type Notice = { tone: "success" | "error"; text: string } | null;

/**
 * The Settings workbench — LLM model binding.
 *
 * This is where each capability (module) gets wired to a concrete model. The
 * friendly path is the batch bar: pick a channel + model once and apply it to
 * every module at once (this is what unblocks Seed analysis). Below it, the
 * module registry is grouped into capability families as compact clustered
 * cards — not one long list — for per-module fine-tuning.
 *
 * Honest by construction: every state shown is read from the live Go API, and
 * every mutation round-trips through the BFF before the UI reflects it.
 */
export function SettingsWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<ProjectSelection | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  const [modules, setModules] = useState<LLMModule[]>([]);
  const [channels, setChannels] = useState<LLMChannel[]>([]);
  const [bindings, setBindings] = useState<LLMModuleBinding[]>([]);
  const [modelsByChannel, setModelsByChannel] = useState<Record<string, LLMModel[]>>({});

  const [batchChoice, setBatchChoice] = useState<ModelChoice>({ channelId: "", modelId: "" });
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null);
  const [rowStates, setRowStates] = useState<Record<string, RowSaveState>>({});
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [savingKeyId, setSavingKeyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const applying = batchProgress !== null;
  const readyChannels = useMemo(() => enabledChannels(channels), [channels]);
  const groups = useMemo(() => groupModules(modules), [modules]);
  const summary = useMemo(() => summarizeBindings(modules, bindings), [modules, bindings]);
  const modelCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const [channelId, models] of Object.entries(modelsByChannel)) {
      counts[channelId] = models.length;
    }
    return counts;
  }, [modelsByChannel]);

  // Default the tab to the first family that still has unbound modules (so the
  // user lands where action is needed), else the first family.
  const resolvedGroup =
    groups.find((g) => g.key === activeGroup) ??
    groups.find((g) =>
      g.modules.some((m) => {
        const b = bindings.find((x) => x.module_key === m.module_key);
        return !b;
      }),
    ) ??
    groups[0] ??
    null;

  function flash(next: Notice) {
    setNotice(next);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    if (next) {
      noticeTimer.current = setTimeout(() => setNotice(null), 4200);
    }
  }

  const ensureModels = useCallback(
    async (sel: ProjectSelection, channelId: string) => {
      if (!channelId || modelsByChannel[channelId]) return;
      try {
        const models = await fetchLLMModels(sel.project_id, sel.tenant_id, channelId);
        setModelsByChannel((prev) => (prev[channelId] ? prev : { ...prev, [channelId]: models }));
      } catch {
        // A missing catalog is non-fatal; the picker just shows no models.
      }
    },
    [modelsByChannel],
  );

  const loadAll = useCallback(async (sel: ProjectSelection) => {
    const [mods, chans, binds] = await Promise.all([
      fetchLLMModules(sel.project_id, sel.tenant_id),
      fetchLLMChannels(sel.project_id, sel.tenant_id),
      fetchLLMBindings(sel.project_id, sel.tenant_id),
    ]);
    setModules(mods);
    setChannels(chans);
    setBindings(binds);
    // Eagerly fetch catalogs for enabled channels so pickers are populated.
    const active = chans.filter((c) => c.enabled);
    const entries = await Promise.all(
      active.map(async (c): Promise<readonly [string, LLMModel[]]> => {
        try {
          return [c.channel_id, await fetchLLMModels(sel.project_id, sel.tenant_id, c.channel_id)];
        } catch {
          return [c.channel_id, []];
        }
      }),
    );
    const catalog: Record<string, LLMModel[]> = {};
    for (const [id, models] of entries) catalog[id] = models;
    setModelsByChannel(catalog);
    // Pre-select the first channel + model that already has bindings, else the first.
    const firstBound = binds.find((b) => b.scope !== "platform");
    const defaultChannel = firstBound?.channel_id ?? active[0]?.channel_id ?? "";
    setBatchChoice((prev) => ({
      channelId: prev.channelId || defaultChannel,
      modelId: prev.modelId || firstBound?.model_id || "",
    }));
  }, []);

  useEffect(() => {
    const sel = readProjectSelection();
    if (!sel || sel.project_id !== projectId) {
      setState({ status: "no-selection" });
      return;
    }
    setSelection(sel);
    let cancelled = false;
    (async () => {
      try {
        await loadAll(sel);
        const token = await fetchCsrfToken().catch(() => null);
        if (!cancelled) {
          setCsrfToken(token);
          setState({ status: "ready" });
        }
      } catch (error) {
        if (!cancelled) {
          if (error instanceof LLMError && error.status === 401) {
            router.replace("/login");
            return;
          }
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "加载失败，请重试。",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, loadAll, router]);

  // Lazy-load a channel's catalog when the batch bar browses to it.
  useEffect(() => {
    if (selection && batchChoice.channelId) {
      void ensureModels(selection, batchChoice.channelId);
    }
  }, [selection, batchChoice.channelId, ensureModels]);

  async function handleBatchApply() {
    if (!selection || !csrfToken || !batchChoice.channelId || !batchChoice.modelId) return;
    const targets = modules;
    setBatchProgress({ done: 0, total: targets.length });
    let succeeded = 0;
    let firstError: string | null = null;
    for (let i = 0; i < targets.length; i++) {
      const mod = targets[i];
      try {
        const binding = await upsertModuleBinding(selection.project_id, selection.tenant_id, csrfToken, mod.module_key, {
          channel_id: batchChoice.channelId,
          model_id: batchChoice.modelId,
        });
        succeeded += 1;
        setBindings((prev) => mergeBinding(prev, binding));
      } catch (error) {
        if (!firstError) firstError = error instanceof Error ? error.message : "部分功能绑定失败";
      }
      setBatchProgress({ done: i + 1, total: targets.length });
    }
    setBatchProgress(null);
    if (succeeded === targets.length) {
      flash({ tone: "success", text: `已把全部 ${succeeded} 个功能套用到所选模型。` });
    } else {
      flash({
        tone: "error",
        text: `已绑定 ${succeeded}/${targets.length} 个功能。${firstError ?? "请重试剩余功能。"}`,
      });
    }
  }

  async function handleRowSave(moduleKey: string, choice: ModelChoice) {
    if (!selection || !csrfToken || !choice.channelId || !choice.modelId) return;
    setRowState(moduleKey, "saving");
    try {
      const binding = await upsertModuleBinding(selection.project_id, selection.tenant_id, csrfToken, moduleKey, {
        channel_id: choice.channelId,
        model_id: choice.modelId,
      });
      setBindings((prev) => mergeBinding(prev, binding));
      setRowState(moduleKey, "saved");
      scheduleRowIdle(moduleKey);
    } catch (error) {
      setRowState(moduleKey, "error");
      flash({ tone: "error", text: error instanceof Error ? error.message : "绑定失败，请重试。" });
      scheduleRowIdle(moduleKey);
    }
  }

  async function handleRowReset(moduleKey: string) {
    if (!selection || !csrfToken) return;
    setRowState(moduleKey, "saving");
    try {
      await deleteModuleBinding(selection.project_id, selection.tenant_id, csrfToken, moduleKey);
      // Re-read so the row falls back to the real inherited state.
      const binds = await fetchLLMBindings(selection.project_id, selection.tenant_id);
      setBindings(binds);
      setRowState(moduleKey, "saved");
      scheduleRowIdle(moduleKey);
    } catch (error) {
      setRowState(moduleKey, "error");
      flash({ tone: "error", text: error instanceof Error ? error.message : "恢复默认失败。" });
      scheduleRowIdle(moduleKey);
    }
  }

  async function handleSync(channelId: string) {
    if (!selection || !csrfToken) return;
    setSyncingId(channelId);
    try {
      await syncLLMChannelModels(selection.tenant_id, csrfToken, channelId);
      const models = await fetchLLMModels(selection.project_id, selection.tenant_id, channelId);
      setModelsByChannel((prev) => ({ ...prev, [channelId]: models }));
      flash({ tone: "success", text: `已同步 ${models.length} 个模型。` });
    } catch (error) {
      flash({ tone: "error", text: error instanceof Error ? error.message : "同步模型失败。" });
    } finally {
      setSyncingId(null);
    }
  }

  async function handleCreateChannel(value: ChannelFormValue): Promise<boolean> {
    if (!selection || !csrfToken) return false;
    setCreating(true);
    try {
      const channel = await createLLMChannel(selection.tenant_id, csrfToken, {
        name: value.name,
        provider: "openai-compatible",
        base_url: value.base_url,
        api_key: value.api_key,
        max_concurrency: value.max_concurrency,
        external_provider_opt_in: true,
      });
      setChannels((prev) => [...prev, channel]);
      // Sync its catalog right away so it's immediately bindable.
      await syncLLMChannelModels(selection.tenant_id, csrfToken, channel.channel_id).catch(() => undefined);
      const models: LLMModel[] = await fetchLLMModels(
        selection.project_id,
        selection.tenant_id,
        channel.channel_id,
      ).catch((): LLMModel[] => []);
      setModelsByChannel((prev) => ({ ...prev, [channel.channel_id]: models }));
      setBatchChoice({ channelId: channel.channel_id, modelId: models[0]?.model_id ?? "" });
      flash(
        models.length > 0
          ? { tone: "success", text: `已连接「${channel.name}」，同步到 ${models.length} 个模型。` }
          : { tone: "error", text: `已连接「${channel.name}」，但没同步到模型 — 请核对密钥后点同步重试。` },
      );
      return true;
    } catch (error) {
      flash({ tone: "error", text: error instanceof Error ? error.message : "连接渠道失败。" });
      return false;
    } finally {
      setCreating(false);
    }
  }

  async function handleUpdateKey(channel: LLMChannel, apiKey: string): Promise<boolean> {
    if (!selection || !csrfToken) return false;
    setSavingKeyId(channel.channel_id);
    try {
      const updated = await updateLLMChannel(selection.tenant_id, csrfToken, channel.channel_id, {
        name: channel.name,
        base_url: channel.base_url,
        api_key: apiKey,
        max_concurrency: channel.max_concurrency,
        external_provider_opt_in: channel.external_provider_opt_in,
        enabled: channel.enabled,
      });
      setChannels((prev) => prev.map((c) => (c.channel_id === updated.channel_id ? updated : c)));
      // Re-sync with the new key so the catalog reflects reality.
      await syncLLMChannelModels(selection.tenant_id, csrfToken, channel.channel_id).catch(() => undefined);
      const models: LLMModel[] = await fetchLLMModels(
        selection.project_id,
        selection.tenant_id,
        channel.channel_id,
      ).catch((): LLMModel[] => []);
      setModelsByChannel((prev) => ({ ...prev, [channel.channel_id]: models }));
      flash(
        models.length > 0
          ? { tone: "success", text: `密钥已更新，同步到 ${models.length} 个模型。` }
          : { tone: "error", text: "密钥已保存，但仍未同步到模型 — 请确认密钥有效。" },
      );
      return models.length > 0;
    } catch (error) {
      flash({ tone: "error", text: error instanceof Error ? error.message : "更新密钥失败。" });
      return false;
    } finally {
      setSavingKeyId(null);
    }
  }

  function setRowState(moduleKey: string, s: RowSaveState) {
    setRowStates((prev) => ({ ...prev, [moduleKey]: s }));
  }

  function scheduleRowIdle(moduleKey: string) {
    if (savedTimers.current[moduleKey]) clearTimeout(savedTimers.current[moduleKey]);
    savedTimers.current[moduleKey] = setTimeout(() => {
      setRowStates((prev) => ({ ...prev, [moduleKey]: "idle" }));
    }, 2200);
  }

  if (state.status === "loading") {
    return <SettingsSkeleton />;
  }
  if (state.status === "no-selection") {
    return <NoSelection onBack={() => router.push("/workspace")} />;
  }
  if (state.status === "error") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-8 text-center">
        <h2 className="font-serif text-xl font-semibold text-ink">设置暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-sm text-muted">{state.message}</p>
      </div>
    );
  }

  const canManage = Boolean(csrfToken);

  return (
    <div className="mx-auto w-full max-w-[1320px] px-8 py-8">
      {/* header */}
      <header className="mb-6">
        <p className="mb-1 text-caption font-medium tracking-label text-muted">设置</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-display font-semibold leading-tight text-ink">模型绑定</h1>
            <p className="mt-2 max-w-[560px] text-sm leading-relaxed text-muted">
              给每个功能指定要用的模型。先用「一键套用」把全部功能接到同一个模型，再按需要单独微调。
              绑定之后，原文分析、图谱、写作台才会真正跑起来。
            </p>
          </div>
          <SummaryPills bound={summary.bound} overridden={summary.overridden} total={summary.total} />
        </div>
      </header>

      {/* transient notice */}
      <AnimatePresence>
        {notice && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className={`mb-5 flex items-center gap-2.5 rounded-panel border px-4 py-3 text-sm ${
 notice.tone === "success"
                ? "border-success/30 bg-success-wash text-success"
                : "border-accent/30 bg-accent-wash/50 text-accent-strong"
            }`}
          >
            {notice.tone === "success" ? (
              <CheckCircle2 className="size-4 shrink-0" aria-hidden />
            ) : (
              <TriangleAlert className="size-4 shrink-0" aria-hidden />
            )}
            {notice.text}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-5">
        {/* channel manager — collapsible strip, never competes for space */}
        <ChannelPanel
          channels={channels}
          modelCounts={modelCounts}
          onSync={handleSync}
          onCreate={handleCreateChannel}
          onUpdateKey={handleUpdateKey}
          syncingId={syncingId}
          creating={creating}
          savingKeyId={savingKeyId}
        />

        {/* batch apply — the primary, friendly path */}
        <div>
          <BatchApplyBar
            channels={readyChannels}
            models={modelsByChannel[batchChoice.channelId] ?? []}
            choice={batchChoice}
            onChoiceChange={setBatchChoice}
            onApply={handleBatchApply}
            applying={applying}
            disabled={!canManage}
            boundCount={summary.bound}
            totalCount={summary.total}
          />
          <AnimatePresence>
            {batchProgress && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <BatchProgress done={batchProgress.done} total={batchProgress.total} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* per-module fine-tuning, one family at a time at full width */}
        <div>
          <ModuleGroupTabs
            groups={groups}
            bindings={bindings}
            active={resolvedGroup?.key ?? ""}
            onChange={setActiveGroup}
          />
          <div className="mt-4">
            {resolvedGroup && (
              <ModuleGroupPanel
                group={resolvedGroup}
                bindings={bindings}
                channels={readyChannels}
                modelsByChannel={modelsByChannel}
                onSave={handleRowSave}
                onReset={handleRowReset}
                rowState={(key) => rowStates[key] ?? "idle"}
                disabled={!canManage || applying}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Insert or replace a binding, keeping the project override authoritative. */
function mergeBinding(prev: LLMModuleBinding[], next: LLMModuleBinding): LLMModuleBinding[] {
  const rest = prev.filter((b) => !(b.module_key === next.module_key && b.scope === "project"));
  return [...rest, next];
}

function SummaryPills({ bound, overridden, total }: { bound: number; overridden: number; total: number }) {
  return (
    <div className="flex items-center gap-2">
      <Pill label="已绑定" value={`${bound}/${total}`} tone={bound === total ? "ok" : "warn"} />
      <Pill label="自定义" value={String(overridden)} tone="neutral" />
    </div>
  );
}

function Pill({ label, value, tone }: { label: string; value: string; tone: "ok" | "warn" | "neutral" }) {
  const cls =
    tone === "ok"
      ? "border-success/30 bg-success-wash text-success"
      : tone === "warn"
        ? "border-accent/30 bg-accent-wash/50 text-accent-strong"
        : "border-line bg-panel text-ink-soft";
  return (
    <span className={`inline-flex items-baseline gap-1.5 rounded-full border px-3 py-1.5 text-caption ${cls}`}>
      <span className="font-medium">{value}</span>
      <span className="opacity-75">{label}</span>
    </span>
  );
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-xl font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-sm text-muted">
        设置需要知道你正在配置哪个项目。回到书架，挑一部作品再进来。
      </p>
      <button
        type="button"
        onClick={onBack}
        className="mt-6 rounded-panel border border-line bg-panel px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
      >
        返回书架
      </button>
    </div>
  );
}

function SettingsSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1320px] px-8 py-8">
      <div className="space-y-3">
        <div className="h-3 w-16 animate-pulse rounded-control bg-line-soft" />
        <div className="h-9 w-56 animate-pulse rounded-control bg-line-soft" />
        <div className="h-4 w-[480px] animate-pulse rounded-control bg-line-soft" />
      </div>
      <div className="mt-8 space-y-5">
        <div className="h-[64px] animate-pulse rounded-modal border border-line bg-panel" />
        <div className="h-[76px] animate-pulse rounded-modal border border-line bg-panel" />
        <div className="h-[44px] animate-pulse rounded-modal border border-line bg-panel" />
        <div className="h-[320px] animate-pulse rounded-modal border border-line bg-panel" />
      </div>
    </div>
  );
}
