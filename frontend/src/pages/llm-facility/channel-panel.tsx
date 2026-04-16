/**
 * LLM Channel management panel.
 *
 * Displays a list of channels with CRUD operations, model sync,
 * and an inline create/edit form.
 */

import { useCallback, useState } from "react";
import {
  RefreshCw,
  Pencil,
  Trash2,
  Plus,
  X,
  Eye,
  EyeOff,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle, CardAction } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import type { LlmChannel } from "@/types/llm";

/* ---------- Constants ---------- */

const MAX_PREVIEW_MODELS = 8;

/* ---------- Props ---------- */

interface ChannelPanelProps {
  channels: LlmChannel[];
  submitting: boolean;
  syncingKey: string;
  deletingKey: string;
  onCreateChannel: (
    payload: Record<string, unknown>,
    resetForm: () => void,
  ) => void;
  onUpdateChannel: (
    channelKey: string,
    payload: Record<string, unknown>,
    resetForm: () => void,
  ) => void;
  onSyncChannel: (channelKey: string) => void;
  onDeleteChannel: (channelKey: string) => void;
}

/* ---------- Form state ---------- */

interface ChannelFormState {
  name: string;
  baseUrl: string;
  apiKey: string;
  maxConcurrency: string;
  isEnabled: boolean;
}

const INITIAL_FORM: ChannelFormState = {
  name: "",
  baseUrl: "",
  apiKey: "",
  maxConcurrency: "4",
  isEnabled: true,
};

/* ---------- Component ---------- */

export default function ChannelPanel({
  channels,
  submitting,
  syncingKey,
  deletingKey,
  onCreateChannel,
  onUpdateChannel,
  onSyncChannel,
  onDeleteChannel,
}: ChannelPanelProps) {
  const [editingChannelKey, setEditingChannelKey] = useState("");
  const [form, setForm] = useState<ChannelFormState>({ ...INITIAL_FORM });
  const [showApiKey, setShowApiKey] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTargetKey, setDeleteTargetKey] = useState("");

  const submitLabel = submitting
    ? editingChannelKey
      ? "保存中..."
      : "创建中..."
    : editingChannelKey
      ? "保存渠道"
      : "创建渠道";

  const resetForm = useCallback(() => {
    setEditingChannelKey("");
    setForm({ ...INITIAL_FORM });
    setShowApiKey(false);
  }, []);

  function startEdit(channel: LlmChannel) {
    setEditingChannelKey(channel.channel_key);
    setForm({
      name: channel.name,
      baseUrl: channel.base_url,
      apiKey: "",
      maxConcurrency: String(channel.max_concurrency || 4),
      isEnabled: !!channel.is_enabled,
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      name: form.name.trim(),
      base_url: form.baseUrl.trim(),
      api_key: form.apiKey.trim(),
      max_concurrency: Math.max(1, Number(form.maxConcurrency || 4)),
      is_enabled: form.isEnabled,
    };
    if (editingChannelKey) {
      onUpdateChannel(editingChannelKey, payload, resetForm);
    } else {
      onCreateChannel(payload, resetForm);
    }
  }

  function patchForm(patch: Partial<ChannelFormState>) {
    setForm((prev) => ({ ...prev, ...patch }));
  }

  function confirmDelete() {
    if (deleteTargetKey) {
      onDeleteChannel(deleteTargetKey);
    }
    setDeleteDialogOpen(false);
    setDeleteTargetKey("");
  }

  function previewModels(models: LlmChannel["models"]) {
    return (models || []).slice(0, MAX_PREVIEW_MODELS);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>渠道管理</CardTitle>
        <CardAction>
          <Button
            variant="outline"
            size="sm"
            disabled={submitting}
            onClick={resetForm}
          >
            <Plus className="size-3.5" />
            新建渠道
          </Button>
        </CardAction>
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          维护 OpenAI 兼容渠道，保存 base_url、密钥与同步状态。
        </p>

        {/* ---------- Create / Edit form ---------- */}
        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-border bg-muted/30 p-3 space-y-3"
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ch-name" className="text-xs">渠道名称</Label>
              <Input
                id="ch-name"
                value={form.name}
                onChange={(e) => patchForm({ name: e.target.value })}
                placeholder="例如：OpenAI Main"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ch-base" className="text-xs">Base URL</Label>
              <Input
                id="ch-base"
                value={form.baseUrl}
                onChange={(e) => patchForm({ baseUrl: e.target.value })}
                placeholder="https://api.openai.com/v1"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ch-concurrency" className="text-xs">并发上限</Label>
              <Input
                id="ch-concurrency"
                value={form.maxConcurrency}
                onChange={(e) => patchForm({ maxConcurrency: e.target.value })}
                placeholder="4"
                type="number"
                min={1}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="ch-key" className="text-xs">API Key</Label>
              <div className="relative">
                <Input
                  id="ch-key"
                  value={form.apiKey}
                  onChange={(e) => patchForm({ apiKey: e.target.value })}
                  placeholder={
                    editingChannelKey
                      ? "留空表示保留现有密钥"
                      : "请输入渠道密钥"
                  }
                  type={showApiKey ? "text" : "password"}
                  className="pr-9"
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setShowApiKey((v) => !v)}
                  tabIndex={-1}
                >
                  {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={form.isEnabled}
                onCheckedChange={(checked) =>
                  patchForm({ isEnabled: checked === true })
                }
              />
              启用该渠道
            </label>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={submitting}>
                {submitLabel}
              </Button>
              {editingChannelKey && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={submitting}
                  onClick={resetForm}
                >
                  <X className="size-3.5" />
                  取消编辑
                </Button>
              )}
            </div>
          </div>
        </form>

        {/* ---------- Channel list ---------- */}
        <div className="space-y-2">
          {channels.map((channel) => (
            <section
              key={channel.channel_key}
              className="rounded-lg border border-border p-3 space-y-2"
            >
              {/* Top row: name + actions */}
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <strong className="text-sm font-semibold">{channel.name}</strong>
                  <div className="font-mono text-xs text-muted-foreground mt-0.5 truncate">
                    {channel.base_url}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant={channel.is_enabled ? "default" : "outline"}>
                    {channel.is_enabled ? "启用中" : "已停用"}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="xs"
                    disabled={submitting}
                    onClick={() => startEdit(channel)}
                  >
                    <Pencil className="size-3" />
                    编辑
                  </Button>
                  <Button
                    variant="ghost"
                    size="xs"
                    disabled={
                      syncingKey === channel.channel_key || submitting
                    }
                    onClick={() => onSyncChannel(channel.channel_key)}
                  >
                    <RefreshCw
                      className={`size-3 ${
                        syncingKey === channel.channel_key ? "animate-spin" : ""
                      }`}
                    />
                    {syncingKey === channel.channel_key
                      ? "同步中..."
                      : "同步模型"}
                  </Button>

                  <Dialog
                    open={deleteDialogOpen && deleteTargetKey === channel.channel_key}
                    onOpenChange={(open) => {
                      setDeleteDialogOpen(open);
                      if (!open) setDeleteTargetKey("");
                    }}
                  >
                    <DialogTrigger
                      render={
                        <Button
                          variant="destructive"
                          size="xs"
                          disabled={
                            deletingKey === channel.channel_key || submitting
                          }
                          onClick={() => {
                            setDeleteTargetKey(channel.channel_key);
                            setDeleteDialogOpen(true);
                          }}
                        />
                      }
                    >
                      <Trash2 className="size-3" />
                      {deletingKey === channel.channel_key
                        ? "删除中..."
                        : "删除"}
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>确认删除</DialogTitle>
                        <DialogDescription>
                          确认删除此渠道？该操作不可撤销。
                        </DialogDescription>
                      </DialogHeader>
                      <DialogFooter>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDeleteDialogOpen(false)}
                        >
                          取消
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={confirmDelete}
                        >
                          删除
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                </div>
              </div>

              {/* Meta tags row */}
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="secondary">{channel.api_key_masked}</Badge>
                <Badge variant="secondary">
                  状态：{channel.last_sync_status || "idle"}
                </Badge>
                <Badge variant="secondary">
                  上次同步：{channel.last_sync_at || "未同步"}
                </Badge>
                <Badge variant="secondary">
                  模型：{channel.models?.length || 0}
                </Badge>
                <Badge variant="secondary">
                  并发上限：{channel.max_concurrency || 4}
                </Badge>
                <Badge variant="secondary">
                  当前占用：{channel.runtime?.inflight || 0}
                </Badge>
                <Badge variant="secondary">
                  排队数：{channel.runtime?.waiting || 0}
                </Badge>
              </div>

              {/* Sync error */}
              {channel.last_sync_error && (
                <p className="text-xs text-destructive">
                  {channel.last_sync_error}
                </p>
              )}

              {/* Model cloud */}
              <div className="flex flex-wrap gap-1">
                {previewModels(channel.models).map((model) => (
                  <Badge key={model.model_id} variant="outline">
                    {model.model_id}
                  </Badge>
                ))}
                {(channel.models?.length || 0) > MAX_PREVIEW_MODELS && (
                  <Badge variant="secondary">
                    +{channel.models.length - MAX_PREVIEW_MODELS}
                  </Badge>
                )}
              </div>
            </section>
          ))}

          {channels.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              还没有配置任何渠道，可先新增一条 OpenAI 兼容渠道。
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
