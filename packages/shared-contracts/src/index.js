export const WRITER_WORKFLOW_TYPE = "writer_run";
export const PI_WRITER_WORKFLOW_NAME = "PiWriterRunWorkflow";
export const WRITER_TASK_QUEUE = "writer-streaming";

export const WRITER_MODES = Object.freeze(["draft", "continue", "outline", "revise"]);
export const WRITER_MODULE_KEYS = Object.freeze(["writer_composer", "writer_orchestrator"]);
export const WRITER_RUNTIME_EVENT_TYPES = Object.freeze([
  "writer.run.started",
  "writer.token",
  "writer.tool.started",
  "writer.tool.completed",
  "writer.draft.saved",
  "writer.retrieval_plan.completed",
  "writer.retrieval_plan.degraded",
  "writer.retrieval_plan.skipped",
  "writer.always_on.injected",
  "writer.worldline_timeline.injected",
  "writer.context_budget.trimmed",
  "writer.consistency.violations",
  "writer.consistency.clean",
  "writer.consistency.skipped",
  "writer.consistency.degraded",
  "writer.revision.proposed",
  "writer.approval.required",
  "writer.approval.resolved",
  "writer.run.failed",
  "writer.run.completed",
  "writer.run.cancelled"
]);
export const WRITER_PUBLIC_EVENT_TYPES = Object.freeze([
  "workflow.queued",
  ...WRITER_RUNTIME_EVENT_TYPES
]);

export const WRITER_TOOL_NAMES = Object.freeze([
  "query_project_context",
  "query_chapter_scene",
  "query_assets",
  "search_assets",
  "search_manuscript",
  "fuse_recall",
  "query_world_rules",
  "query_character_profile",
  "query_graph_neighbors",
  "query_asset_relationships",
  "query_worldline_paths",
  "query_manuscript_context"
]);
