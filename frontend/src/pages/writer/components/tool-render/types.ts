/**
 * Shared types for the tool-render subsystem. Re-exports canonical types
 * from `@/types/writer` and adds UI-scoped callback shapes used by hosts
 * and cards.
 */

export type {
  ChapterStructureProposalChapter,
  ChapterStructureProposalData,
  EntityCardData,
  EntityCardEvent,
  EntityCardMemory,
  EntityCardRelation,
  EntityCardSection,
  ProseDiffData,
  ProseDiffHunk,
  RelationshipProposalData,
  RelationSubgraphData,
  RelationSubgraphEdge,
  RelationSubgraphNode,
  SceneProposalData,
  SceneTimelineData,
  SceneTimelineEvent,
  ThreadBoardData,
  ThreadBoardThread,
  ToolRenderAction,
  ToolRenderBase,
  ToolRenderPayload,
  ToolRenderType,
  WordBudgetBlock,
  WordBudgetData,
} from "@/types/writer";

export { isRender } from "@/types/writer";

export interface RenderHostContext {
  projectId: string;
  /** Chapter currently focused in the workbench (if any). Cards use it to
   * prefill "target chapter" fields when an action implies a write. */
  chapterId?: string;
  sceneId?: string;
  /** Called after a successful adopt to trigger parent re-fetches. */
  onAdopted?: (payload: { type: string; result?: unknown }) => void;
  /** Called when the user asks a card to hand text back to the input box
   * ("让 Agent 扩写 400 字..."), driving the writer input. */
  onPrependToInput?: (text: string) => void;
  /** Scrolls to a specific manuscript block / scene in the reading pane. */
  onJumpToBlock?: (blockId: string) => void;
  onOpenScene?: (sceneId: string) => void;
  onOpenEntity?: (entityId: string) => void;
}
