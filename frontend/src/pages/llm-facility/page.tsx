/**
 * LLM Facility page — global channel management and module binding dashboard.
 *
 * Polls settings every 2 seconds for live runtime metrics.
 */

import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Radio, Cpu, Link2 } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  createLlmChannel,
  deleteLlmChannel,
  deleteLlmModuleBinding,
  getLlmSettings,
  syncLlmChannelModels,
  updateLlmChannel,
  updateLlmModuleBinding,
} from "@/api/llm";
import type { LlmChannel, LlmModule } from "@/types/llm";

import ChannelPanel from "./channel-panel";
import { getLlmSettingsRefetchInterval } from "./binding-select-open-state";
import ModuleBindingsPanel from "./module-bindings-panel";

/* ---------- Component ---------- */

export default function LlmFacilityPage() {
  const queryClient = useQueryClient();
  const [openBindingSelectKey, setOpenBindingSelectKey] = useState("");

  /* ---- Data fetching with 2s polling ---- */
  const { data, isLoading } = useQuery({
    queryKey: ["llm-settings"],
    queryFn: async () => {
      const response = await getLlmSettings();
      return response.data as { channels: LlmChannel[]; modules: LlmModule[] };
    },
    refetchInterval: getLlmSettingsRefetchInterval(openBindingSelectKey),
  });

  const channels: LlmChannel[] = useMemo(() => data?.channels ?? [], [data?.channels]);
  const modules: LlmModule[] = useMemo(() => data?.modules ?? [], [data?.modules]);

  const modelCount = channels.reduce(
    (sum, ch) => sum + (ch.models?.length || 0),
    0,
  );
  const boundModuleCount = modules.filter((m) => m.binding).length;

  /* ---- Busy-state keys ---- */
  const [submittingChannelKey, setSubmittingChannelKey] = useState("");
  const [syncingChannelKey, setSyncingChannelKey] = useState("");
  const [deletingChannelKey, setDeletingChannelKey] = useState("");
  const [savingModuleKey, setSavingModuleKey] = useState("");
  const [removingModuleKey, setRemovingModuleKey] = useState("");
  const [unbindDialogOpen, setUnbindDialogOpen] = useState(false);
  const [unbindTargetKey, setUnbindTargetKey] = useState("");

  const channelBusy = !!submittingChannelKey;

  const reload = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["llm-settings"] });
  }, [queryClient]);

  /* ---- Channel handlers ---- */

  const handleCreateChannel = useCallback(
    async (payload: Record<string, unknown>, resetForm: () => void) => {
      try {
        setSubmittingChannelKey("creating");
        await createLlmChannel(payload);
        resetForm();
        toast.success("渠道已创建");
        reload();
      } catch (err) {
        toast.error((err as Error).message || "创建失败");
      } finally {
        setSubmittingChannelKey("");
      }
    },
    [reload],
  );

  const handleUpdateChannel = useCallback(
    async (
      channelKey: string,
      payload: Record<string, unknown>,
      resetForm: () => void,
    ) => {
      try {
        setSubmittingChannelKey(channelKey);
        await updateLlmChannel(channelKey, payload);
        resetForm();
        toast.success("渠道已更新");
        reload();
      } catch (err) {
        toast.error((err as Error).message || "更新失败");
      } finally {
        setSubmittingChannelKey("");
      }
    },
    [reload],
  );

  const handleDeleteChannel = useCallback(
    async (channelKey: string) => {
      try {
        setDeletingChannelKey(channelKey);
        await deleteLlmChannel(channelKey);
        toast.success("渠道已删除");
        reload();
      } catch (err) {
        toast.error((err as Error).message || "删除失败");
      } finally {
        setDeletingChannelKey("");
      }
    },
    [reload],
  );

  const handleSyncChannel = useCallback(
    async (channelKey: string) => {
      try {
        setSyncingChannelKey(channelKey);
        await syncLlmChannelModels(channelKey);
        toast.success("已同步");
        reload();
      } catch (err) {
        toast.error((err as Error).message || "同步失败");
      } finally {
        setSyncingChannelKey("");
      }
    },
    [reload],
  );

  /* ---- Module binding handlers ---- */

  const [batchSaving, setBatchSaving] = useState(false);

  const handleSaveBinding = useCallback(
    async (
      moduleKey: string,
      payload: { channel_key: string; model_id: string },
    ) => {
      try {
        setSavingModuleKey(moduleKey);
        await updateLlmModuleBinding(moduleKey, payload);
        toast.success("绑定已保存");
        reload();
      } catch (err) {
        toast.error((err as Error).message || "保存失败");
      } finally {
        setSavingModuleKey("");
      }
    },
    [reload],
  );

  const handleRemoveBinding = useCallback(
    (moduleKey: string) => {
      setUnbindTargetKey(moduleKey);
      setUnbindDialogOpen(true);
    },
    [],
  );

  const confirmRemoveBinding = useCallback(async () => {
    const moduleKey = unbindTargetKey;
    setUnbindDialogOpen(false);
    setUnbindTargetKey("");
    if (!moduleKey) return;
    try {
      setRemovingModuleKey(moduleKey);
      await deleteLlmModuleBinding(moduleKey);
      toast.success("绑定已解绑");
      reload();
    } catch (err) {
      toast.error((err as Error).message || "解绑失败");
    } finally {
      setRemovingModuleKey("");
    }
  }, [unbindTargetKey, reload]);

  const handleBatchSaveBindings = useCallback(
    async (payload: { channel_key: string; model_id: string }) => {
      try {
        setBatchSaving(true);
        const results = await Promise.allSettled(
          modules.map((m) => updateLlmModuleBinding(m.module_key, payload)),
        );
        const failed = results.filter((r) => r.status === "rejected").length;
        if (failed === 0) {
          toast.success(`已绑定全部 ${modules.length} 个模块`);
        } else {
          toast.warning(`${modules.length - failed} 个成功，${failed} 个失败`);
        }
        reload();
      } catch (err) {
        toast.error((err as Error).message || "批量绑定失败");
      } finally {
        setBatchSaving(false);
      }
    },
    [modules, reload],
  );

  /* ---- Render ---- */

  if (isLoading && !data) {
    return (
      <div className="mx-auto max-w-[1200px] space-y-4">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-40" />
          </CardHeader>
          <CardContent>
            <div className="flex gap-8 border-t border-border pt-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex flex-col gap-1.5">
                  <Skeleton className="h-3 w-12" />
                  <Skeleton className="h-6 w-16" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[7fr_5fr]">
          <Skeleton className="h-80 rounded-lg" />
          <Skeleton className="h-80 rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-4">
      {/* Header: Stats & Refresh */}
      <Card>
        <CardHeader>
          <CardTitle>全局设施面板</CardTitle>
          <Button
            variant="ghost"
            size="sm"
            disabled={isLoading}
            onClick={reload}
          >
            <RefreshCw
              className={`size-3.5 ${isLoading ? "animate-spin" : ""}`}
            />
            {isLoading ? "同步中..." : "刷新状态"}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex gap-8 border-t border-border pt-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
                渠道
              </span>
              <span className="flex items-center gap-1.5 text-base font-semibold tabular-nums">
                <Radio className="size-3.5 text-muted-foreground" />
                {channels.length}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
                模型
              </span>
              <span className="flex items-center gap-1.5 text-base font-semibold tabular-nums">
                <Cpu className="size-3.5 text-muted-foreground" />
                {modelCount}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
                绑定
              </span>
              <span className="flex items-center gap-1.5 text-base font-semibold tabular-nums">
                <Link2 className="size-3.5 text-muted-foreground" />
                {boundModuleCount}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Two-column layout: Channels + Bindings */}
      <div className="grid grid-cols-1 gap-4 items-start lg:grid-cols-[7fr_5fr]">
        <ChannelPanel
          channels={channels}
          submitting={channelBusy}
          syncingKey={syncingChannelKey}
          deletingKey={deletingChannelKey}
          onCreateChannel={handleCreateChannel}
          onUpdateChannel={handleUpdateChannel}
          onSyncChannel={handleSyncChannel}
          onDeleteChannel={handleDeleteChannel}
        />
            <ModuleBindingsPanel
              modules={modules}
              channels={channels}
              savingKey={savingModuleKey}
              removingKey={removingModuleKey}
              batchSaving={batchSaving}
              onOpenSelectKeyChange={setOpenBindingSelectKey}
              onSaveBinding={handleSaveBinding}
              onBatchSaveBindings={handleBatchSaveBindings}
              onRemoveBinding={handleRemoveBinding}
            />
      </div>

      {/* Unbind confirmation dialog */}
      <Dialog
        open={unbindDialogOpen}
        onOpenChange={(open) => {
          setUnbindDialogOpen(open);
          if (!open) setUnbindTargetKey("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认解绑</DialogTitle>
            <DialogDescription>
              确认解除此模块的绑定？
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setUnbindDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={confirmRemoveBinding}
            >
              解绑
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
