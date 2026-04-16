import { Activity, ChevronDown } from "lucide-react";

import { useLlmActivity } from "@/hooks/use-llm-activity";
import { cn } from "@/lib/utils";
import type { LlmActiveCall, LlmChannelActivity } from "@/types/llm";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

/* ---------- helpers ---------- */

function formatElapsed(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(1)}s`;
}

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "running") return "default";
  if (status === "streaming") return "secondary";
  if (status === "waiting") return "outline";
  return "secondary";
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    waiting: "Waiting",
    running: "Running",
    streaming: "Streaming",
  };
  return map[status] ?? status;
}

function concurrencyPct(snap: LlmChannelActivity): number {
  if (!snap.limit) return 0;
  return Math.min(100, Math.round((snap.active_count / snap.limit) * 100));
}

/* ---------- sub-components ---------- */

function CallRow({ call }: { call: LlmActiveCall }) {
  return (
    <div className="border-b border-border/40 py-2 last:border-b-0">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{call.module}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {formatElapsed(call.elapsed_seconds)}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <Badge variant={statusVariant("running")} className="text-[10px]">
          {statusLabel("running")}
        </Badge>
        <span className="font-mono text-[11px] text-muted-foreground">
          {call.model_id}
        </span>
        <span className="font-mono text-[11px] text-muted-foreground/60">
          {call.channel_key}
        </span>
      </div>
    </div>
  );
}

function ChannelBar({
  channelKey,
  snap,
}: {
  channelKey: string;
  snap: LlmChannelActivity;
}) {
  const pct = concurrencyPct(snap);
  const saturated = snap.active_count >= snap.limit;

  return (
    <div className="flex items-center gap-2 py-1">
      <span className="min-w-[80px] shrink-0 font-mono text-xs text-muted-foreground">
        {channelKey}
      </span>
      <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            saturated ? "bg-destructive" : "bg-primary",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="whitespace-nowrap font-mono text-[11px] text-muted-foreground">
        {snap.active_count}/{snap.limit}
      </span>
    </div>
  );
}

/* ---------- main component ---------- */

export function LlmActivityIndicator() {
  const { totalActive, calls, channels } = useLlmActivity();

  const channelEntries = Object.entries(channels);

  if (totalActive === 0) {
    return (
      <div className="flex items-center gap-1.5 rounded-md border border-border/40 px-2.5 py-1 text-xs text-muted-foreground/60">
        <Activity className="h-3 w-3" />
        <span>Idle</span>
      </div>
    );
  }

  return (
    <Popover>
      <PopoverTrigger>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md border border-primary/25 bg-primary/8 px-2.5 py-1 text-xs text-primary transition-colors hover:bg-primary/14"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
          </span>
          <span className="font-mono font-bold">{totalActive}</span>
          <span className="text-muted-foreground">Running</span>
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        </button>
      </PopoverTrigger>

      <PopoverContent
        side="bottom"
        align="end"
        className="w-[400px] max-h-[420px] overflow-y-auto"
      >
        {/* Header */}
        <div className="mb-2 flex items-center justify-between border-b border-border/40 pb-2">
          <span className="text-sm font-semibold">LLM Activity Monitor</span>
          <span className="font-mono text-xs text-muted-foreground">
            {totalActive} request{totalActive !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Call list */}
        <div className="flex flex-col">
          {calls.map((call) => (
            <CallRow key={call.call_id} call={call} />
          ))}
        </div>

        {/* Channel concurrency */}
        {channelEntries.length > 0 && (
          <div className="mt-3 border-t border-border/40 pt-2">
            <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">
              Channel Concurrency
            </div>
            {channelEntries.map(([key, snap]) => (
              <ChannelBar key={key} channelKey={key} snap={snap} />
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
