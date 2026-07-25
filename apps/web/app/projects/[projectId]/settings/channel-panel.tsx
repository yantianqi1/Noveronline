import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Cable, ChevronDown, KeyRound, Loader2, Plus, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { LLMChannel } from "@/lib/api/llm-types";

/**
 * The channel (provider) manager, rendered as a collapsible strip in the
 * settings header. Collapsed it's a single summary row ("N 个渠道 · M 个模型")
 * so it never competes with the module grid for space; expanded it reveals the
 * channel list with sync / rotate-key actions and the connect form. API keys go
 * only to Go, which encrypts them at rest; a key is never shown after saving.
 */
export function ChannelPanel({
  channels,
  modelCounts,
  onSync,
  onCreate,
  onUpdateKey,
  syncingId,
  creating,
  savingKeyId,
}: {
  channels: LLMChannel[];
  /** Synced model count per channel id, for a quick health read. */
  modelCounts: Record<string, number>;
  onSync: (channelId: string) => void;
  onCreate: (input: ChannelFormValue) => Promise<boolean>;
  onUpdateKey: (channel: LLMChannel, apiKey: string) => Promise<boolean>;
  syncingId: string | null;
  creating: boolean;
  savingKeyId: string | null;
}) {
  // Auto-open when there are no channels yet (first-run guidance).
  const [open, setOpen] = useState(channels.length === 0);
  const [formOpen, setFormOpen] = useState(false);
  const totalModels = Object.values(modelCounts).reduce((a, b) => a + b, 0);

  return (
    <section className="overflow-hidden rounded-card border border-line bg-panel shadow-[0_1px_2px_rgba(23,26,27,0.05)]">
      {/* summary row — always visible, toggles the manager */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-paper/50"
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-accent-wash text-accent">
            <Cable className="size-4" aria-hidden />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13.5px] font-semibold text-ink">模型渠道</span>
            <span className="block truncate text-[12px] text-muted">
              {channels.length === 0
                ? "还没有渠道 — 连接一个模型服务"
                : `${channels.length} 个渠道 · ${totalModels} 个模型`}
            </span>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          {channels.length > 0 && (
            <span className="hidden rounded-full bg-paper-deep px-2 py-0.5 text-[11px] text-muted sm:inline">
              {channels.filter((c) => c.enabled).length} 启用
            </span>
          )}
          <ChevronDown
            className={cn("size-4 text-muted transition-transform duration-300", open && "rotate-180")}
            aria-hidden
          />
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden border-t border-line-soft"
          >
            <div className="space-y-2.5 p-4">
              {channels.length === 0 ? (
                <p className="rounded-[10px] border border-dashed border-line bg-paper/50 px-4 py-5 text-center text-[12.5px] leading-relaxed text-muted">
                  还没有可用渠道。连接一个模型渠道，才能给各功能绑定模型。
                </p>
              ) : (
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {channels.map((channel) => (
                    <ChannelRow
                      key={channel.channel_id}
                      channel={channel}
                      modelCount={modelCounts[channel.channel_id]}
                      onSync={() => onSync(channel.channel_id)}
                      onUpdateKey={(apiKey) => onUpdateKey(channel, apiKey)}
                      syncing={syncingId === channel.channel_id}
                      savingKey={savingKeyId === channel.channel_id}
                    />
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={() => setFormOpen((v) => !v)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-[9px] border border-dashed border-line px-3.5 py-2 text-[12.5px] font-medium transition-colors",
                  formOpen
                    ? "border-accent/40 bg-accent-wash text-accent"
                    : "text-muted hover:border-accent/40 hover:text-accent",
                )}
              >
                <Plus className={cn("size-3.5 transition-transform", formOpen && "rotate-45")} aria-hidden />
                连接新渠道
              </button>

              <AnimatePresence initial={false}>
                {formOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                    className="overflow-hidden"
                  >
                    <ChannelForm
                      creating={creating}
                      onSubmit={async (value) => {
                        const ok = await onCreate(value);
                        if (ok) setFormOpen(false);
                      }}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function ChannelRow({
  channel,
  modelCount,
  onSync,
  onUpdateKey,
  syncing,
  savingKey,
}: {
  channel: LLMChannel;
  modelCount: number | undefined;
  onSync: () => void;
  onUpdateKey: (apiKey: string) => Promise<boolean>;
  syncing: boolean;
  savingKey: boolean;
}) {
  const [editingKey, setEditingKey] = useState(false);
  const [key, setKey] = useState("");
  const noModels = channel.enabled && modelCount !== undefined && modelCount === 0;

  return (
    <div className="rounded-[10px] border border-line-soft bg-paper/40 px-3.5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn("size-[7px] shrink-0 rounded-full", channel.enabled ? "bg-emerald-700/70" : "bg-muted/50")}
              aria-hidden
            />
            <span className="truncate text-[13px] font-medium text-ink">{channel.name}</span>
            <span className="shrink-0 rounded-full bg-paper-deep px-1.5 py-px text-[10.5px] text-muted">
              {channel.provider}
            </span>
          </div>
          <p className="mt-0.5 truncate pl-[15px] text-[11.5px] text-muted/80" title={channel.base_url}>
            {channel.base_url}
          </p>
          {modelCount !== undefined && (
            <p className={cn("mt-0.5 pl-[15px] text-[11px]", noModels ? "text-accent" : "text-muted/70")}>
              {noModels ? "0 个模型 — 检查密钥后重试同步" : `${modelCount} 个模型`}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => setEditingKey((v) => !v)}
            title="更新 API 密钥"
            className={cn(
              "grid size-7 place-items-center rounded-[7px] transition-colors",
              editingKey ? "bg-accent-wash text-accent" : "text-muted/70 hover:bg-accent-wash hover:text-accent",
            )}
          >
            <KeyRound className="size-3.5" aria-hidden />
          </button>
          <button
            type="button"
            onClick={onSync}
            disabled={syncing}
            title="同步该渠道的最新模型目录"
            className="grid size-7 place-items-center rounded-[7px] text-muted/70 transition-colors hover:bg-accent-wash hover:text-accent disabled:opacity-50"
          >
            {syncing ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <RefreshCw className="size-3.5" aria-hidden />
            )}
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {editingKey && (
          <motion.form
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
            onSubmit={async (e) => {
              e.preventDefault();
              if (key.trim() === "") return;
              const ok = await onUpdateKey(key.trim());
              if (ok) {
                setKey("");
                setEditingKey(false);
              }
            }}
          >
            <div className="mt-2.5 flex items-center gap-1.5">
              <Input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="新的 API Key"
                type="password"
                className="h-8 flex-1 text-[12.5px]"
              />
              <Button type="submit" size="sm" disabled={key.trim() === "" || savingKey} loading={savingKey} className="h-8 px-3">
                保存
              </Button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
    </div>
  );
}

export type ChannelFormValue = {
  name: string;
  base_url: string;
  api_key: string;
  max_concurrency: number;
};

function ChannelForm({
  creating,
  onSubmit,
}: {
  creating: boolean;
  onSubmit: (value: ChannelFormValue) => void;
}) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const valid = name.trim() !== "" && baseUrl.trim() !== "" && apiKey.trim() !== "";

  return (
    <form
      className="space-y-2.5 rounded-[10px] border border-line-soft bg-paper/40 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        onSubmit({ name: name.trim(), base_url: baseUrl.trim(), api_key: apiKey.trim(), max_concurrency: 4 });
      }}
    >
      <p className="text-[12px] leading-relaxed text-muted">
        接入一个 OpenAI 兼容的模型服务。密钥只发往服务端加密保存，这里不会再显示。
      </p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="渠道名称，如 我的 GPT" className="h-9 text-[13px]" />
        <Input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="Base URL，如 https://api.example.com/v1"
          className="h-9 text-[13px]"
        />
      </div>
      <Input
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder="API Key"
        type="password"
        className="h-9 text-[13px]"
      />
      <Button type="submit" size="sm" disabled={!valid || creating} loading={creating} className="w-full">
        {creating ? "连接中…" : "连接并同步模型"}
      </Button>
    </form>
  );
}
