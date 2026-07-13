import type { ReactNode } from "react";

export type WorkflowProgressStage = {
  id: string;
  label: ReactNode;
  state: "pending" | "active" | "done" | "failed";
};

type WorkflowProgressProps = {
  actions?: ReactNode;
  className?: string;
  currentLabel: ReactNode;
  events?: ReactNode;
  progressLabel?: ReactNode;
  stages?: WorkflowProgressStage[];
  title: ReactNode;
};

/**
 * Shared long-running task surface for seed, graph build, worldline, and writer.
 */
export function WorkflowProgress({
  actions,
  className = "",
  currentLabel,
  events,
  progressLabel,
  stages = [],
  title,
}: WorkflowProgressProps) {
  return (
    <section className={["workflow-progress", className].filter(Boolean).join(" ")} aria-live="polite">
      <header className="workflow-progress-header">
        <div>
          <h2>{title}</h2>
          <p className="workflow-progress-current">{currentLabel}</p>
          {progressLabel ? <p className="form-hint">{progressLabel}</p> : null}
        </div>
        {actions ? <div className="workflow-progress-actions">{actions}</div> : null}
      </header>
      {stages.length > 0 ? (
        <ol className="workflow-progress-stages">
          {stages.map((stage) => (
            <li data-state={stage.state} key={stage.id}>
              <span>{stage.label}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {events ? <div className="workflow-progress-events">{events}</div> : null}
    </section>
  );
}
