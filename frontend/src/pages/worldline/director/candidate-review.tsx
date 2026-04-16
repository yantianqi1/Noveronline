import * as React from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

import { cn } from "@/lib/utils";
import { StatusRibbon } from "./status-ribbon";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface CandidateEvent {
  event_id: string;
  step: number;
  title: string;
  summary: string;
  driving_entities: string[];
  confidence: string;
  confidence_reason: string;
  event_source: string;
  status: string;
}

interface CandidateReviewProps {
  candidateEvents: CandidateEvent[];
  streamPhase: string;
  onAdoptEvent: (payload: { eventId: string }) => void;
  onRejectEvent: (payload: { eventId: string }) => void;
  onEditEvent: (payload: { eventId: string; consequence: string }) => void;
  onAdoptAll: () => void;
  onRejectAll: () => void;
}

/* ================================================================ */
/*  Constants                                                        */
/* ================================================================ */

const SOURCE_LABELS: Record<string, string> = {
  archive_based: "档案驱动",
  goal_driven: "目标驱动",
  variable_reaction: "变量触发",
  agent_initiative: "角色主动",
  system: "系统生成",
};

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function CandidateReview({
  candidateEvents,
  onAdoptEvent,
  onRejectEvent,
  onEditEvent,
  onAdoptAll,
  onRejectAll,
}: CandidateReviewProps) {
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set());
  const [editingEventId, setEditingEventId] = React.useState("");
  const [editText, setEditText] = React.useState("");

  function toggleExpand(eventId: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) next.delete(eventId);
      else next.add(eventId);
      return next;
    });
  }

  function startEdit(event: CandidateEvent) {
    setEditingEventId(event.event_id);
    setEditText(event.summary || "");
  }

  function cancelEdit() {
    setEditingEventId("");
    setEditText("");
  }

  function submitEdit(eventId: string) {
    if (editText.trim()) {
      onEditEvent({ eventId, consequence: editText.trim() });
    }
    setEditingEventId("");
    setEditText("");
  }

  return (
    <section className="mt-3 p-3 rounded-xl bg-gradient-to-b from-amber-50/95 to-orange-50/92 border border-amber-400/35 border-t-[3px] border-t-amber-500/50">
      {/* Top bar */}
      <div className="flex justify-between items-center gap-2 flex-wrap">
        <div className="flex items-center gap-2.5">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-600 animate-pulse" />
          <span className="font-mono text-sm font-semibold text-amber-800 tracking-wide">
            {candidateEvents.length} 个候选事件等待审核
          </span>
        </div>
        {candidateEvents.length > 1 && (
          <div className="flex gap-2">
            <Button size="sm" onClick={onAdoptAll}>
              全部采纳
            </Button>
            <Button size="sm" variant="outline" onClick={onRejectAll}>
              全部拒绝
            </Button>
          </div>
        )}
      </div>

      {/* Card row */}
      <div className="mt-2.5 overflow-x-auto pb-1">
        <div className="flex gap-2">
          {candidateEvents.map((event) => (
            <article
              key={event.event_id}
              className={cn(
                "shrink-0 w-[300px] min-w-[260px] max-w-[360px] border rounded-lg p-2.5 bg-white/88 transition-all hover:shadow-md",
                "border-amber-300/40",
                event.confidence === "high" && "border-l-[3px] border-l-green-600/65",
                event.confidence === "medium" && "border-l-[3px] border-l-amber-500/65",
                event.confidence === "low" && "border-l-[3px] border-l-red-600/55",
              )}
            >
              {/* Card head */}
              <div className="flex justify-between gap-2 items-start">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-xs text-stone-500 tracking-wider">
                    STEP {event.step}
                  </p>
                  <h4 className="mt-0.5 text-sm font-semibold text-stone-800 leading-snug">
                    {event.title || "未命名事件"}
                  </h4>
                </div>
                <div className="flex gap-1 shrink-0 flex-wrap justify-end">
                  {event.confidence && (
                    <StatusRibbon
                      status="candidate"
                      confidence={event.confidence}
                    />
                  )}
                  <Badge variant="outline" className="text-xs">
                    {SOURCE_LABELS[event.event_source] || event.event_source || "未知来源"}
                  </Badge>
                </div>
              </div>

              {/* Summary */}
              <p
                className={cn(
                  "mt-2.5 text-sm text-stone-600 leading-relaxed break-words",
                  !expandedIds.has(event.event_id) && "line-clamp-3",
                )}
              >
                {event.summary}
              </p>
              {event.summary && event.summary.length > 80 && (
                <button
                  className="mt-1 text-xs text-amber-700 underline underline-offset-2 hover:text-amber-900"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExpand(event.event_id);
                  }}
                >
                  {expandedIds.has(event.event_id) ? "收起" : "展开全文"}
                </button>
              )}
              {event.confidence_reason && (
                <p className="mt-1.5 text-xs text-amber-700 italic">
                  {event.confidence_reason}
                </p>
              )}

              {/* Driving entities */}
              {event.driving_entities && event.driving_entities.length > 0 && (
                <div className="flex gap-1.5 items-center flex-wrap mt-2">
                  {event.driving_entities.map((driver) => (
                    <span
                      key={driver}
                      className="w-6 h-6 rounded-full inline-flex items-center justify-center font-bold text-xs bg-amber-400/20 text-amber-900 shrink-0"
                      title={driver}
                    >
                      {driver.charAt(0)}
                    </span>
                  ))}
                  <span className="text-xs text-stone-500">
                    {event.driving_entities.join("、")}
                  </span>
                </div>
              )}

              {/* Actions or inline edit */}
              {editingEventId !== event.event_id ? (
                <div className="flex gap-1.5 mt-3">
                  <Button
                    size="sm"
                    onClick={() => onAdoptEvent({ eventId: event.event_id })}
                  >
                    采纳
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => startEdit(event)}
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onRejectEvent({ eventId: event.event_id })}
                  >
                    拒绝
                  </Button>
                </div>
              ) : (
                <div className="mt-3" onClick={(e) => e.stopPropagation()}>
                  <Textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    rows={3}
                    placeholder="修改事件描述后采纳..."
                  />
                  <div className="flex gap-1.5 mt-2">
                    <Button
                      size="sm"
                      onClick={() => submitEdit(event.event_id)}
                    >
                      确认并采纳
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={cancelEdit}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
