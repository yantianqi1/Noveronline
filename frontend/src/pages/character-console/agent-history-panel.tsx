import * as React from "react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

import type { AgentData } from "./agent-detail-presentation";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface SnapshotItem {
  snapshot_id: string;
  state_version: number;
  status: string;
  reason: string;
  created_at?: string;
}

interface ActionItem {
  action_event_id: string;
  status: string;
  action: string;
  created_at?: string;
}

interface DialogueItem {
  dialogue_id: string;
  generator_mode: string;
  message: string;
  reply: string;
  created_at?: string;
}

interface MemoryItem {
  memory_id: string;
  memory_type: string;
  summary: string;
  updated_at?: string;
}

interface AgentHistoryPanelProps {
  sessionId: string;
  selectedAgent: AgentData | null;
  snapshots: SnapshotItem[];
  actions: ActionItem[];
  dialogues: DialogueItem[];
  sessionMemories: MemoryItem[];
  longTermMemories: MemoryItem[];
  error: string;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatTime(value: unknown): string {
  if (!value) return "--";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function AgentHistoryPanel({
  sessionId,
  selectedAgent,
  snapshots,
  actions,
  dialogues,
  sessionMemories,
  longTermMemories,
  error,
}: AgentHistoryPanelProps) {
  if (!sessionId || !selectedAgent) {
    return (
      <Card className="flex min-h-[120px] flex-col items-center justify-center gap-1 p-2.5">
        <h2 className="text-sm font-semibold">对象历史</h2>
        <p className="text-xs text-muted-foreground">选择对象后自动加载历史。</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-2.5">
        <h2 className="text-sm font-semibold">对象历史</h2>
        <Badge variant="destructive" className="mt-2">{error}</Badge>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-1.5 p-2.5">
      <h2 className="text-sm font-semibold">对象历史</h2>
      <p className="text-xs text-muted-foreground">
        展示对象在当前分支的快照、动作与对话历史。
      </p>

      <Tabs defaultValue="snapshots">
        <TabsList variant="line">
          <TabsTrigger value="snapshots">快照 · {snapshots.length}</TabsTrigger>
          <TabsTrigger value="actions">动作 · {actions.length}</TabsTrigger>
          <TabsTrigger value="dialogues">对话 · {dialogues.length}</TabsTrigger>
          <TabsTrigger value="memories">
            记忆 · {sessionMemories.length + longTermMemories.length}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="snapshots">
          <ScrollArea className="max-h-[320px]">
            {!snapshots.length ? (
              <p className="py-3 text-center text-xs text-muted-foreground">暂无快照</p>
            ) : (
              <div className="flex flex-col gap-2 py-1">
                {snapshots.map((item) => (
                  <div
                    key={item.snapshot_id}
                    className="border-b border-dashed border-border/40 pb-2 last:border-b-0"
                  >
                    <div className="font-mono text-[10px] text-muted-foreground">
                      v{item.state_version} · {formatTime(item.created_at)}
                    </div>
                    <div className="text-xs">{item.status} · {item.reason}</div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="actions">
          <ScrollArea className="max-h-[320px]">
            {!actions.length ? (
              <p className="py-3 text-center text-xs text-muted-foreground">暂无动作</p>
            ) : (
              <div className="flex flex-col gap-2 py-1">
                {actions.map((item) => (
                  <div
                    key={item.action_event_id}
                    className="border-b border-dashed border-border/40 pb-2 last:border-b-0"
                  >
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {item.status} · {formatTime(item.created_at)}
                    </div>
                    <div className="text-xs">{item.action}</div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="dialogues">
          <ScrollArea className="max-h-[320px]">
            {!dialogues.length ? (
              <p className="py-3 text-center text-xs text-muted-foreground">暂无对话</p>
            ) : (
              <div className="flex flex-col gap-2 py-1">
                {dialogues.map((item) => (
                  <div
                    key={item.dialogue_id}
                    className="border-b border-dashed border-border/40 pb-2 last:border-b-0"
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
          </ScrollArea>
        </TabsContent>

        <TabsContent value="memories">
          <ScrollArea className="max-h-[320px]">
            {!sessionMemories.length && !longTermMemories.length ? (
              <p className="py-3 text-center text-xs text-muted-foreground">暂无记忆</p>
            ) : (
              <div className="flex flex-col gap-2 py-1">
                {sessionMemories.map((item) => (
                  <div
                    key={item.memory_id}
                    className="border-b border-dashed border-border/40 pb-2 last:border-b-0"
                  >
                    <div className="font-mono text-[10px] text-muted-foreground">
                      session · {item.memory_type} · {formatTime(item.updated_at)}
                    </div>
                    <div className="text-xs">{item.summary}</div>
                  </div>
                ))}
                {longTermMemories.map((item) => (
                  <div
                    key={item.memory_id}
                    className="border-b border-dashed border-border/40 pb-2 last:border-b-0"
                  >
                    <div className="font-mono text-[10px] text-muted-foreground">
                      long_term · {item.memory_type} · {formatTime(item.updated_at)}
                    </div>
                    <div className="text-xs">{item.summary}</div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </Card>
  );
}
