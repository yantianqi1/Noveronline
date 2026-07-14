"use client";

import { ChevronRight, CircleAlert, CircleCheck, LoaderCircle, Wifi, WifiOff } from "lucide-react";
import { useId, useState } from "react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import {
  summarizeWriterTaskStatus,
  type WriterConnectionHint,
} from "../lib/writer-task-status";
import { Bi } from "./bilingual-text";

type WriterTaskStatusLineProps = {
  locale: Locale;
  events: readonly WriterRunEvent[];
  connection?: WriterConnectionHint;
  /** Opens the technical-details drawer when provided. */
  onOpenTechnicalDetails?: () => void;
};

/**
 * Single collapsed status row for a writer run (docs/refactor-saas/36 §4.3).
 * Expand reveals author-language steps; tool keys / raw payloads stay out.
 */
export function WriterTaskStatusLine({
  locale,
  events,
  connection = "idle",
  onOpenTechnicalDetails,
}: WriterTaskStatusLineProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const summary = summarizeWriterTaskStatus(locale, events, connection);
  const hasSteps = summary.steps.length > 0;
  const phaseState = phaseDataState(summary.phase);

  return (
    <div className="writer-task-status" data-phase={summary.phase} data-open={open ? "true" : "false"}>
      <button
        aria-controls={hasSteps ? panelId : undefined}
        aria-expanded={hasSteps ? open : undefined}
        className="writer-task-status-main"
        data-state={phaseState}
        onClick={() => {
          if (hasSteps) setOpen((value) => !value);
        }}
        type="button"
      >
        <span aria-hidden="true" className="writer-task-status-ico">
          <StatusIcon phase={summary.phase} />
        </span>
        <span className="writer-task-status-text">{summary.line}</span>
        {hasSteps ? (
          <ChevronRight aria-hidden="true" className="writer-task-status-chev" size={14} />
        ) : null}
      </button>

      {hasSteps && open ? (
        <div className="writer-task-status-steps" id={panelId}>
          <ol aria-label={tx(locale, "任务步骤", "Task steps")}>
            {summary.steps.map((step) => (
              <li key={step.id} data-status={step.status}>
                <span aria-hidden="true" className="writer-task-step-ico">
                  <StepIcon status={step.status} />
                </span>
                <span>{step.label}</span>
              </li>
            ))}
          </ol>
          {onOpenTechnicalDetails ? (
            <button className="writer-task-status-tech" onClick={onOpenTechnicalDetails} type="button">
              <Bi zh="查看技术详情" en="View technical details" />
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function StatusIcon({ phase }: { phase: string }) {
  if (phase === "reconnecting") return <Wifi size={15} />;
  if (phase === "interrupted") return <WifiOff size={15} />;
  if (phase === "failed" || phase === "cancelled") return <CircleAlert size={15} />;
  if (phase === "completed" || phase === "revision_ready") return <CircleCheck size={15} />;
  if (phase === "idle") return <CircleCheck size={15} />;
  return <LoaderCircle className="is-spinning" size={15} />;
}

function StepIcon({ status }: { status: string }) {
  if (status === "running") return <LoaderCircle className="is-spinning" size={13} />;
  if (status === "failed") return <CircleAlert size={13} />;
  if (status === "completed") return <CircleCheck size={13} />;
  return <span className="writer-task-step-dot" />;
}

function phaseDataState(phase: string) {
  if (phase === "failed" || phase === "cancelled" || phase === "interrupted") return "error";
  if (phase === "completed" || phase === "revision_ready") return "done";
  if (phase === "idle") return "idle";
  return "active";
}
