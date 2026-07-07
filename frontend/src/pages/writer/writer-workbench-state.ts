/**
 * Writer workbench pure-logic helpers.
 * Ported from src-vue/views/writer/writerWorkbenchState.js.
 */

export interface ChapterOption {
  chapter_id: string;
  order: number;
  title: string;
}

export interface WriterDefaults {
  chapterOrder: number;
  chapterId: string;
  povCharacter: string;
}

export function deriveWriterDefaults(
  options: { chapters?: ChapterOption[]; pov_characters?: string[] } = {},
): WriterDefaults {
  const firstChapter = options.chapters?.[0];
  return {
    chapterOrder: firstChapter?.order ?? 0,
    chapterId: firstChapter?.chapter_id ?? "",
    povCharacter: options.pov_characters?.[0] ?? "",
  };
}

export interface WriterFormState {
  scopeType: string;
  projectId: string;
  povCharacter: string;
  writingGoal: string;
  sceneFocus: string;
  includeCandidates: boolean;
  sessionId: string;
  branchId: string;
  chapterId: string;
  chapterOrder: number;
}

export type SaasWriterTaskType = "write_scene" | "continue" | "outline";

export interface SaasWriterRunFormState {
  taskType: SaasWriterTaskType;
  chapterId: string;
  selectedSceneId: string;
  authorInstruction: string;
  sceneFocus: string;
  moduleKey: string;
  selectedAssetIds: string[];
  worldlinePathIds: string[];
  characterNames: string[];
  graphNodeNames: string[];
  assetQuery: string;
  worldRuleQuery: string;
}

export function parseWriterReferenceInput(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[\n,，]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ];
}

function assignNonEmptyArray(
  target: Record<string, unknown>,
  key: string,
  items: string[] = [],
) {
  const cleaned = [...new Set(items.map((item) => item.trim()).filter(Boolean))];
  if (cleaned.length) {
    target[key] = cleaned;
  }
}

export function buildSaasWriterRunPayload(
  form: SaasWriterRunFormState,
): Record<string, unknown> {
  const options: Record<string, unknown> = {
    module_key: form.moduleKey,
  };
  assignNonEmptyArray(options, "selected_asset_ids", form.selectedAssetIds);
  assignNonEmptyArray(options, "worldline_path_ids", form.worldlinePathIds);
  assignNonEmptyArray(options, "character_names", form.characterNames);
  assignNonEmptyArray(options, "graph_node_names", form.graphNodeNames);
  const assetQuery = form.assetQuery.trim();
  const worldRuleQuery = form.worldRuleQuery.trim();
  if (assetQuery) options.asset_query = assetQuery;
  if (worldRuleQuery) options.world_rule_query = worldRuleQuery;

  const payload: Record<string, unknown> = {
    mode: form.taskType === "continue" ? "continue" : "draft",
    instruction: form.authorInstruction.trim() || form.sceneFocus.trim(),
    options,
  };
  if (form.chapterId) {
    payload.chapter_id = form.chapterId;
  }
  if (form.selectedSceneId) {
    payload.scene_id = form.selectedSceneId;
  }
  return payload;
}

export function buildWriterRequestPayload(form: Partial<WriterFormState> = {}): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    scope_type: form.scopeType,
    project_id: form.projectId,
    pov_character: form.povCharacter,
    writing_goal: form.writingGoal,
    scene_focus: form.sceneFocus,
    include_candidates: Boolean(form.includeCandidates),
  };
  if (form.scopeType === "worldline_branch") {
    payload.session_id = form.sessionId;
    payload.branch_id = form.branchId || "main";
    return payload;
  }
  if (form.chapterId) {
    payload.chapter_id = form.chapterId;
  }
  if (form.chapterOrder) {
    payload.chapter_order = Number(form.chapterOrder);
  }
  return payload;
}

export interface WorldlineAgent {
  display_name: string;
  agent_kind: string;
}

export function resolveWriterPovOptions(
  scopeType: string,
  projectPovs: string[] = [],
  worldlineAgents: WorldlineAgent[] = [],
): string[] {
  if (scopeType === "worldline_branch" && worldlineAgents.length) {
    return [
      ...new Set(
        worldlineAgents
          .filter((item) => item.agent_kind !== "relationship")
          .map((item) => item.display_name)
          .filter(Boolean),
      ),
    ];
  }
  return [...new Set(projectPovs.filter(Boolean))];
}

export interface ContextItem {
  item_id: string;
  category?: string;
  summary?: string;
  memory_layer?: string;
  archive_id?: string;
  normalized_subject?: string;
  source_kind?: string;
  source_ref?: string;
  why_it_matters?: string;
}

export interface ContextPack {
  must_know: ContextItem[];
  should_know?: ContextItem[];
  warnings: ContextItem[];
  history_recall?: {
    recent_anchors?: HistoryAnchor[];
    selection_trace?: SelectionTrace[];
  };
}

export interface HistoryAnchor {
  chapter_id?: string;
  chapter_order: number;
  title?: string;
  summary_text: string;
}

export interface SelectionTrace {
  item_type?: string;
  chapter_order: number;
  summary_text: string;
  source_ref?: string;
  selected_because?: string[];
}

export function findContextItem(
  pack: ContextPack | null,
  selectedItem: ContextItem | null,
): ContextItem | null {
  if (!pack || !selectedItem?.item_id) {
    return null;
  }
  const items = [
    ...(pack.must_know || []),
    ...(pack.should_know || []),
    ...(pack.warnings || []),
  ];
  return items.find((item) => item.item_id === selectedItem.item_id) ?? null;
}
