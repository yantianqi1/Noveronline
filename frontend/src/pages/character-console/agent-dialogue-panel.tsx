import * as React from "react";
import { Send, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";

import type { AgentData } from "./agent-detail-presentation";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ChatReply {
  reply?: string;
  generator_mode?: string;
  model_name?: string;
  suggested_actions?: string[];
  [key: string]: unknown;
}

interface DialogueItem {
  dialogue_id: string;
  generator_mode: string;
  message: string;
  reply: string;
  created_at?: string;
}

interface AgentDialoguePanelProps {
  sessionId: string;
  selectedAgent: AgentData | null;
  chatMode: string;
  chatMessage: string;
  chatReply: ChatReply | null;
  dialogues: DialogueItem[];
  chatError: string;
  busy: boolean;
  onUpdateChatMode: (value: string) => void;
  onUpdateChatMessage: (value: string) => void;
  onSubmit: () => void;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatTime(value: unknown): string {
  if (!value) return "--";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

const CHAT_MODE_OPTIONS = [
  { label: "template", value: "template" },
  { label: "llm", value: "llm" },
] as const;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function AgentDialoguePanel({
  sessionId,
  selectedAgent,
  chatMode,
  chatMessage,
  chatReply,
  dialogues,
  chatError,
  busy,
  onUpdateChatMode,
  onUpdateChatMessage,
  onSubmit,
}: AgentDialoguePanelProps) {
  return (
    <Card className="flex flex-col gap-2.5 p-2.5">
      <h2 className="text-sm font-semibold">对象对话入口</h2>
      <p className="text-xs text-muted-foreground">
        从右侧对象名册选中一个对象后，直接向它发送一句话并查看回应。
      </p>

      <div className="grid gap-2.5 md:grid-cols-3">
        {/* Current agent */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">当前对话对象</label>
          <div className="rounded-lg border px-3 py-2 text-sm">
            {selectedAgent?.display_name || "请先从右侧点选对象"}
          </div>
        </div>

        {/* Mode selector */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">生成模式</label>
          <Select value={chatMode} onValueChange={(v) => onUpdateChatMode(v ?? "template")}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CHAT_MODE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Message input */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">你要说的话</label>
          <Textarea
            value={chatMessage}
            onChange={(e) => onUpdateChatMessage(e.target.value)}
            placeholder="例如：你是否愿意在今晚之前公开证据？"
            className="min-h-[50px] text-sm"
          />
        </div>
      </div>

      <Button
        disabled={busy || !sessionId || !selectedAgent}
        onClick={onSubmit}
        className="self-start"
      >
        {busy ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Send className="mr-1.5 h-3.5 w-3.5" />
        )}
        发送对话
      </Button>

      {/* Chat reply */}
      {chatReply && (
        <div className="rounded-lg border p-2.5">
          <div className="text-xs font-bold">对象回复</div>
          <p className="mt-1 text-sm">{chatReply.reply || "暂无回复文本"}</p>
          <Separator className="my-1.5" />
          <div className="text-xs font-bold">生成信息</div>
          <div className="font-mono text-[11px] text-muted-foreground">
            {chatReply.generator_mode || chatMode} · {chatReply.model_name || "无模型"}
          </div>
          {chatReply.suggested_actions && chatReply.suggested_actions.length > 0 && (
            <>
              <Separator className="my-1.5" />
              <div className="text-xs font-bold">建议动作</div>
              {chatReply.suggested_actions.map((item, idx) => (
                <div key={idx} className="border-t border-dashed border-border/40 py-1 text-xs">
                  {idx + 1}. {item}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Dialogue history */}
      {dialogues.length > 0 && (
        <div className="rounded-lg border p-2.5">
          <div className="text-xs font-bold">最近对话历史</div>
          {dialogues.map((item) => (
            <div
              key={item.dialogue_id}
              className="border-t border-dashed border-border/40 py-1.5"
            >
              <div className="font-mono text-[10px] text-muted-foreground">
                {item.generator_mode} · {formatTime(item.created_at)}
              </div>
              <div className="text-xs">Q: {item.message}</div>
              <div className="text-xs">A: {item.reply}</div>
            </div>
          ))}
        </div>
      )}

      {chatError && (
        <Badge variant="destructive" className="self-start">{chatError}</Badge>
      )}
    </Card>
  );
}
