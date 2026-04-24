/**
 * ArchiveMemoryPanel — tabbed memory management for a single archive:
 * list by layer (canon/candidate/experiment), timeline, and adopt/reject
 * actions on candidate memories.
 *
 * Extracted from the former `/archive-library` page so the unified asset
 * library DetailSheet can render it inline when the selected UnifiedItem
 * has `source === "archive"`.
 */

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Clock, CheckCircle2, XCircle } from "lucide-react";

import type { ApiResponse } from "@/api/http";
import type { ArchiveMemory, MemoryTimeline } from "@/types/archive";
import {
  listArchiveMemory,
  getArchiveMemoryTimeline,
  adoptArchiveMemory,
  rejectArchiveMemory,
} from "@/api/assets";
import { useNotification } from "@/hooks/use-notification";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const MEMORY_LAYER_LABELS: Record<string, string> = {
  canon: "正典",
  candidate: "候选",
  experiment: "实验",
};

export function ArchiveMemoryPanel({ archiveId }: { archiveId: string }) {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotification();
  const [memoryTab, setMemoryTab] = React.useState("all");

  const memoryQuery = useQuery({
    queryKey: ["archiveMemory", archiveId, memoryTab],
    queryFn: () =>
      listArchiveMemory(archiveId, {
        includeCandidates: true,
        layer: memoryTab === "all" ? undefined : memoryTab,
      }),
    enabled: !!archiveId,
  });

  const timelineQuery = useQuery({
    queryKey: ["archiveMemoryTimeline", archiveId],
    queryFn: () => getArchiveMemoryTimeline(archiveId),
    enabled: !!archiveId,
  });

  const adoptMutation = useMutation({
    mutationFn: (memoryId: string) => adoptArchiveMemory(archiveId, memoryId),
    onSuccess: () => {
      notifySuccess("记忆已采纳为正典");
      queryClient.invalidateQueries({ queryKey: ["archiveMemory", archiveId] });
      queryClient.invalidateQueries({ queryKey: ["archiveMemoryTimeline", archiveId] });
    },
    onError: (err: Error) => notifyError(err.message || "采纳失败"),
  });

  const rejectMutation = useMutation({
    mutationFn: (memoryId: string) => rejectArchiveMemory(archiveId, memoryId),
    onSuccess: () => {
      notifySuccess("记忆已拒绝");
      queryClient.invalidateQueries({ queryKey: ["archiveMemory", archiveId] });
      queryClient.invalidateQueries({ queryKey: ["archiveMemoryTimeline", archiveId] });
    },
    onError: (err: Error) => notifyError(err.message || "拒绝失败"),
  });

  const memories = (memoryQuery.data as ApiResponse | undefined)?.data as ArchiveMemory[] | undefined;
  const timelineData = (timelineQuery.data as ApiResponse | undefined)?.data as MemoryTimeline[] | undefined;

  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-sm font-semibold">记忆管理</h4>

      <Tabs defaultValue="all" onValueChange={setMemoryTab}>
        <TabsList variant="line">
          <TabsTrigger value="all">全部</TabsTrigger>
          <TabsTrigger value="canon">正典</TabsTrigger>
          <TabsTrigger value="candidate">候选</TabsTrigger>
          <TabsTrigger value="experiment">实验</TabsTrigger>
          <TabsTrigger value="timeline">时间线</TabsTrigger>
        </TabsList>

        {/* Memory list tabs */}
        {["all", "canon", "candidate", "experiment"].map((tab) => (
          <TabsContent key={tab} value={tab}>
            {memoryQuery.isLoading ? (
              <div className="space-y-2 py-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : !memories?.length ? (
              <p className="py-4 text-center text-sm text-muted-foreground">暂无记忆记录</p>
            ) : (
              <div className="flex flex-col gap-2 py-2">
                {memories.map((mem) => (
                  <Card key={mem.id} className="flex flex-col gap-1.5 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium">{mem.subject || mem.normalized_subject}</span>
                          <Badge
                            variant={mem.layer === "canon" ? "default" : "outline"}
                            className="text-[10px]"
                          >
                            {MEMORY_LAYER_LABELS[mem.layer] || mem.layer}
                          </Badge>
                          <Badge variant="secondary" className="text-[10px]">
                            {mem.memory_type}
                          </Badge>
                        </div>
                        <p className="line-clamp-2 text-xs text-muted-foreground">{mem.content}</p>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-muted-foreground">
                        {mem.source} {mem.created_at ? `-- ${mem.created_at}` : ""}
                      </span>
                      {mem.layer === "candidate" && (
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs"
                            disabled={adoptMutation.isPending}
                            onClick={() => adoptMutation.mutate(mem.id)}
                          >
                            <CheckCircle2 className="mr-1 h-3 w-3" />
                            采纳
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs text-destructive hover:bg-destructive/10"
                            disabled={rejectMutation.isPending}
                            onClick={() => rejectMutation.mutate(mem.id)}
                          >
                            <XCircle className="mr-1 h-3 w-3" />
                            拒绝
                          </Button>
                        </div>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        ))}

        {/* Timeline tab */}
        <TabsContent value="timeline">
          {timelineQuery.isLoading ? (
            <div className="space-y-2 py-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full rounded-lg" />
              ))}
            </div>
          ) : !timelineData?.length ? (
            <p className="py-4 text-center text-sm text-muted-foreground">暂无时间线记录</p>
          ) : (
            <div className="flex flex-col gap-3 py-2">
              {timelineData.map((timeline, ti) => (
                <div key={ti} className="flex flex-col gap-1">
                  <h5 className="text-xs font-semibold text-primary">{timeline.subject}</h5>
                  <div className="relative ml-3 border-l border-border/60 pl-4">
                    {timeline.events?.map((event, ei) => (
                      <div key={ei} className="relative pb-3 last:pb-0">
                        <div className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-primary" />
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-1.5">
                            <Clock className="h-3 w-3 text-muted-foreground" />
                            <span className="text-[11px] text-muted-foreground">{event.timestamp}</span>
                            <Badge variant="outline" className="text-[9px]">{event.event_type}</Badge>
                          </div>
                          <p className="text-xs leading-relaxed">{event.content}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
