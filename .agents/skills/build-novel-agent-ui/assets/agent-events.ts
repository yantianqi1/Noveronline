/**
 * Adapt this reference contract to the existing backend. Do not create a
 * competing schema when the project already has a source of truth.
 */
export type RunStatus =
  | "queued"
  | "planning"
  | "running"
  | "waiting_user"
  | "paused"
  | "completed"
  | "failed"
  | "canceled";

export type AgentEventType =
  | "run.created"
  | "run.status"
  | "run.heartbeat"
  | "run.completed"
  | "run.failed"
  | "message.delta"
  | "message.completed"
  | "activity.started"
  | "activity.updated"
  | "activity.completed"
  | "tool.started"
  | "tool.progress"
  | "tool.completed"
  | "tool.failed"
  | "artifact.snapshot"
  | "artifact.patch"
  | "artifact.completed"
  | "approval.requested"
  | "approval.resolved"
  | "usage.updated"
  | "warning.raised";

export interface AgentEvent<TType extends AgentEventType = AgentEventType, TPayload = unknown> {
  eventId: string;
  runId: string;
  threadId: string;
  sequence: number;
  type: TType;
  createdAt: string;
  payload: TPayload;
}

export interface RunSnapshot {
  runId: string;
  threadId: string;
  projectId: string;
  status: RunStatus;
  lastSequence: number;
  startedAt?: string;
  finishedAt?: string;
  activeApprovalId?: string;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
  };
}

export interface ArtifactPatchPayload {
  artifactId: string;
  artifactType: "chapter" | "scene" | "outline" | "story_entity" | "report" | "export";
  baseVersion: string;
  provisionalVersion: string;
  format: "text-diff" | "json-patch" | "snapshot";
  operations: unknown;
  complete: boolean;
}

export interface ApprovalRequestPayload {
  approvalId: string;
  title: string;
  description: string;
  scope: Array<{ type: string; id: string; label: string }>;
  risk: "low" | "medium" | "high";
  reversible: boolean;
  actions: Array<{
    id: string;
    label: string;
    kind: "approve" | "reject" | "edit";
  }>;
}

export interface CreateRunCommand {
  projectId: string;
  threadId?: string;
  idempotencyKey: string;
  intent: string;
  context: Array<{
    type: "selection" | "chapter" | "scene" | "character" | "world" | "source" | "style_guide";
    id: string;
    version?: string;
    label: string;
  }>;
}

export interface CreateRunResult {
  runId: string;
  threadId: string;
  status: RunStatus;
  eventStreamUrl: string;
}
