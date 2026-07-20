import { WriterWorkbenchShell } from "../../../../../../components/writer-workbench-shell";
import { ProjectWorkspaceLoading } from "../../../../../../components/project-workspace-loading";
import { WriterDraftBlock } from "../../../../../../components/writer-draft-block";
import {
  WriterProductWorkspace,
  WriterProductWorkspaceLoading,
  type WriterProductWorkspaceProps,
} from "../../../../../../components/writer-product-workspace";
import {
  decideWriterApproval,
  exportAgentTrace,
  getAgentTraceEvents,
  getProjectManuscript,
  getProjectAssets,
  getStoryGraphView,
  getWorldlineSavedPaths,
  getAllWriterRunEvents,
  getWriterRunSummary,
  listWriterThreadMessages,
  listWriterThreads,
  adoptWriterDraft,
  startWriterRun,
} from "../../../../../../lib/api";
import { tx } from "../../../../../../lib/locale";
import { currentRequestLocale } from "../../../../../../lib/request-locale";
import { webApiContext, webReadApiContext } from "../../../../../../lib/server-auth";
import { humanizeFailure } from "../../../../../../lib/user-facing-copy";
import {
  createBookPlan, createChapter, createManuscriptBlock, createOutline, createScene, createWorkspaceExport, decideAssetProposal, decideDedupPattern,
  deleteBookPlan, deleteChapter, deleteLexicon, deleteManuscriptBlock, deletePreset, deleteScene,
  getAssetDistillationSettings, getManuscriptCommand, getPrivateBlock, listAssetProposals, listBookPlans, listChapterVersions, listChapters,
  listDedupPatterns, listDraftReviews, listLexicon, listManuscriptBlocks, listManuscriptVersions,
  listOutlines, listPresets, listSceneVersions, listScenes, listWorkspaceExports, moveManuscriptBlock,
  patchAssetDistillationSettings, reorderChapters, reorderManuscriptBlocks, reorderScenes, restoreManuscriptVersion, restoreOutline,
  getWriterPlanningRun, startBookPlanGeneration, startDedupExtraction, startDraftReview, startManuscriptAssetDistillation, startManuscriptCommand, tagManuscriptBlock, updateBookPlan, updateChapter,
  updateManuscriptBlock, updateReviewIssue, updateScene, upsertLexicon, upsertProjectPreset,
  upsertTenantPreset, type ManuscriptBlock, type PrivateManuscriptBlock, type WriterWebContext, type WriterWebResult, type WritingVersion,
} from "../../../../../../lib/writer-workspace-api";
import { manuscriptCommandKeyFromChoice } from "../../../../../../lib/writer-command-labels";
import { decodeLocalDraft, encodeLocalDraft } from "../../../../../../lib/writer-local-draft";
import { pendingRevisionFromWriterEvents } from "../../../../../../lib/writer-revision";
import { redirect } from "next/navigation";
import { Suspense } from "react";

export const dynamic = "force-dynamic";

type WriterPageProps = {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    afterEventId?: string;
    after_event_id?: string;
    draftAdoptionCode?: string;
    draftAdoptionStatus?: string;
    draftId?: string;
    runId?: string;
    runtime_run_id?: string;
    traceExportCode?: string;
    traceExportMessage?: string;
    traceExportStatus?: string;
    traceId?: string;
    writerRunCode?: string;
    writerRunMessage?: string;
    writerRunStatus?: string;
    writerControlCode?: string;
    writerControlStatus?: string;
    workspaceStatus?: string;
    workspaceCode?: string;
    localDraft?: string;
    chapterId?: string;
    sceneId?: string;
    blockId?: string;
    commandId?: string;
    reviewActionCode?: string;
    reviewActionStatus?: string;
    planningRunId?: string;
  }>;
};

export default function WriterPage(props: WriterPageProps) {
  return (
    <Suspense fallback={<ProjectWorkspaceLoading />}>
      <WriterPageData {...props} />
    </Suspense>
  );
}

async function WriterPageData({ params, searchParams }: WriterPageProps) {
  const { tenantSlug, projectId } = await params;
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const afterEventId = query.after_event_id ?? query.afterEventId ?? "";
  const selectedRunId = query.runId ?? query.runtime_run_id ?? "";
  const selectedTraceId = query.traceId ?? "";
  const selectedDraftId = query.draftId ?? "";
  const selectedChapterId = query.chapterId ?? "";
  const selectedSceneId = query.sceneId ?? "";
  const selectedBlockId = query.blockId ?? "";
  const selectedCommandId = query.commandId ?? "";
  const selectedPlanningRunId = query.planningRunId ?? "";
  const apiContext = webReadApiContext({ tenantId: tenantSlug });
  const runSummary = selectedRunId
    ? await getWriterRunSummary({
        ...apiContext,
        runId: selectedRunId,
      })
    : null;
  const workflowEvents = runSummary !== null && runSummary.ok === true
    ? await getAllWriterRunEvents({
        ...apiContext,
        runId: runSummary.run_id,
        afterEventId: afterEventId,
      })
    : null;
  const traceId = selectedTraceId || (runSummary !== null && runSummary.ok === true ? runSummary.trace_id : "");
  const traceEvents = traceId
    ? await getAgentTraceEvents({
        ...apiContext,
        projectId,
        traceId,
      })
    : null;
  const workspaceContext: WriterWebContext = { ...apiContext, projectId };
  const recoveredDraftId = draftIdFromWriterEvents(selectedDraftId, workflowEvents);
  const [assets, graphView, worldlineSavedPaths, manuscript, writerThreads] =
    await Promise.all([
      getProjectAssets({
        ...apiContext,
        projectId,
      }),
      getStoryGraphView({
        ...apiContext,
        projectId,
        viewId: "world",
        limit: 12,
        includeEdges: false,
      }),
      getWorldlineSavedPaths({
        ...apiContext,
        projectId,
      }),
      getProjectManuscript({
        ...apiContext,
        projectId,
      }),
      listWriterThreads({
        ...apiContext,
        projectId,
      }),
    ]);
  const activeWriterThread =
    writerThreads.ok === true && writerThreads.threads.length > 0 ? writerThreads.threads[0] : null;
  const writerThreadMessages = activeWriterThread
    ? await listWriterThreadMessages({
        ...apiContext,
        projectId,
        threadId: activeWriterThread.thread_id,
      })
    : null;
  const threadMessages =
    writerThreadMessages?.ok === true
      ? writerThreadMessages.messages.map((message) => ({
          role: message.role,
          body: message.message_text,
          created_at: message.created_at,
          run_id: message.run_id,
        }))
      : [];

  async function startWriterRunAction(formData: FormData): Promise<{
    ok: boolean;
    code: string;
    message: string;
    runId?: string;
    traceId?: string;
  }> {
    "use server";

    const selectedAssetIds = stringListFromFormData(formData, "selectedAssetIds");
    const selectedGraphNodes = graphNodeSelectionsFromFormData(formData, "selectedGraphNodeIds");
    const worldlinePathIds = stringListFromFormData(formData, "worldlinePathIds");
    const instruction = stringFromFormData(formData, "instruction");
    const mode = writerModeFromFormData(formData);
    const revise = reviseOptionsFromFormData(formData);
    if (mode === "revise" && !revise) {
      return {
        ok: false,
        code: "VALIDATION_FAILED",
        message: tx(locale, "修订需要选区。", "Revise requires a selection."),
      };
    }
    const chapterId = stringFromFormData(formData, "chapterId") || query.chapterId || "";
    const sceneId = stringFromFormData(formData, "sceneId") || query.sceneId || "";
    const result = await startWriterRun({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      mode,
      instruction,
      chapterId,
      sceneId,
      idempotencyKey: crypto.randomUUID(),
      options: {
        module_key: "writer_composer",
        chapter_id: chapterId,
        scene_id: sceneId,
        selected_asset_ids: selectedAssetIds,
        graph_node_ids: selectedGraphNodes.ids,
        graph_node_names: selectedGraphNodes.names,
        worldline_path_ids: worldlinePathIds,
        ...(revise ? { revise } : {}),
      },
    });
    if (result.ok) {
      return {
        ok: true,
        code: "WRITER_RUN_QUEUED",
        message: "",
        runId: result.run_id,
        traceId: result.trace_id,
      };
    }
    return {
      ok: false,
      code: result.code,
      message: humanizeFailure(locale, result.code, result.message),
    };
  }

  async function reviseSelectionAction(formData: FormData) {
    "use server";
    // Selection-driven revise reuses the writer run admission channel with mode=revise.
    formData.set("mode", "revise");
    if (!stringFromFormData(formData, "instruction")) {
      formData.set("instruction", tx(locale, "修订选中段落。", "Revise the selection."));
    }
    // Product workspace may still expect void; surface result via soft URL only on success path.
    const result = await startWriterRunAction(formData);
    if (result.ok && result.runId) {
      const nextQuery = new URLSearchParams({
        runId: result.runId,
        ...(result.traceId ? { traceId: result.traceId } : {}),
      });
      redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
    }
    if (!result.ok) {
      const nextQuery = new URLSearchParams({
        writerRunStatus: "error",
        writerRunCode: result.code,
        writerRunMessage: result.message,
      });
      redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
    }
  }

  async function exportTraceAction(formData: FormData) {
    "use server";

    const nextTraceId = stringFromFormData(formData, "traceId");
    const result = await exportAgentTrace({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      traceId: nextTraceId,
      includeFull: false,
    });
    const nextQuery = new URLSearchParams({
      traceExportStatus: result.ok ? "success" : "error",
      traceExportCode: result.ok ? "TRACE_EXPORT_READY" : result.code,
      traceExportMessage: result.ok
        ? tx(
            locale,
            `追踪记录已准备好（${result.items.length} 条）`,
            `Trace export ready (${result.items.length} events)`,
          )
        : result.message,
    });
    if (query.runId) {
      nextQuery.set("runId", query.runId);
    }
    if (nextTraceId) {
      nextQuery.set("traceId", nextTraceId);
    }
    const cursor = query.after_event_id ?? query.afterEventId;
    if (cursor) {
      nextQuery.set("after_event_id", cursor);
    }
    redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
  }

  async function adoptDraftAction(formData: FormData): Promise<{
    ok: boolean;
    code: string;
    message: string;
    blockId?: string;
  }> {
    "use server";

    const draftId = stringFromFormData(formData, "draftId");
    if (!draftId) {
      return {
        ok: false,
        code: "VALIDATION_FAILED",
        message: tx(locale, "缺少候选稿。", "Candidate draft is required."),
      };
    }
    const chapterId = stringFromFormData(formData, "chapterId") || query.chapterId || "";
    const result = await adoptWriterDraft({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      draftId,
      ...(chapterId ? { chapterId } : {}),
    });
    if (result.ok) {
      return {
        ok: true,
        code: "DRAFT_ADOPTED",
        message: "",
        blockId: result.block_id,
      };
    }
    return {
      ok: false,
      code: result.code,
      message: humanizeFailure(locale, result.code, result.message),
    };
  }

  async function undoDraftAdoptionAction(formData: FormData): Promise<{
    ok: boolean;
    code: string;
    message: string;
  }> {
    "use server";

    const blockId = stringFromFormData(formData, "blockId");
    if (!blockId) {
      return {
        ok: false,
        code: "VALIDATION_FAILED",
        message: tx(locale, "缺少手稿块。", "Manuscript block is required."),
      };
    }
    const context = await writerWorkspaceContext(tenantSlug, projectId);
    const block = await getPrivateBlock(context, blockId);
    if (!block.ok || !block.value) {
      const code = block.ok ? "NOT_FOUND" : block.code;
      return { ok: false, code, message: humanizeFailure(locale, code, undefined) };
    }
    const result = await deleteManuscriptBlock(context, blockId, block.value.version);
    if (result.ok) {
      return { ok: true, code: "DRAFT_ADOPTION_UNDONE", message: "" };
    }
    return {
      ok: false,
      code: result.code,
      message: humanizeFailure(locale, result.code, result.message),
    };
  }

  async function cancelWriterRunAction(formData: FormData) {
    "use server";

    const runId = stringFromFormData(formData, "runId");
    const context = await webApiContext({ tenantId: tenantSlug, projectId });
    let ok = false;
    let code = "WRITER_CANCEL_FAILED";
    if (runId) {
      try {
        const response = await fetch(
          `${process.env.MIROFISH_API_BASE_URL ?? "http://127.0.0.1:3888"}/v1/writer-runs/${encodeURIComponent(runId)}/cancel`,
          { method: "POST", headers: writerActionHeaders(context), body: "{}", cache: "no-store" },
        );
        ok = response.ok;
        if (!ok) {
          const payload = await response.json().catch(() => null) as { error?: { code?: unknown } } | null;
          const responseCode = payload?.error?.code;
          if (typeof responseCode === "string" && /^[A-Z][A-Z0-9_]+$/.test(responseCode)) code = responseCode;
        }
      } catch {
        code = "WRITER_CANCEL_FAILED";
      }
    } else {
      code = "VALIDATION_FAILED";
    }
    const nextQuery = writerSelectionQuery(query, selectedDraftId);
    if (runId) nextQuery.set("runId", runId);
    nextQuery.set("writerControlStatus", ok ? "success" : "error");
    nextQuery.set("writerControlCode", ok ? "WRITER_RUN_CANCELLED" : code);
    redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
  }

  async function startDraftReviewAction(formData: FormData) {
    "use server";

    const draftId = stringFromFormData(formData, "draftId");
    const result = await startDraftReview(
      await webApiContext({ tenantId: tenantSlug, projectId }),
      draftId,
      { project_id: projectId, run_id: stringFromFormData(formData, "runId") },
    );
    workspaceRedirect(result, tenantSlug, projectId, query, { draftId });
  }

  async function updateReviewIssueAction(formData: FormData) {
    "use server";

    const draftId = stringFromFormData(formData, "draftId");
    const result = await updateReviewIssue(
      await webApiContext({ tenantId: tenantSlug, projectId }),
      stringFromFormData(formData, "issueId"),
      stringFromFormData(formData, "status"),
      stringFromFormData(formData, "version"),
    );
    workspaceRedirect(result, tenantSlug, projectId, query, { draftId });
  }

  async function createChapterAction(formData: FormData) {
    "use server";
    const result = await createChapter(await writerWorkspaceContext(tenantSlug, projectId), { title: stringFromFormData(formData, "title"), status: "planned" });
    workspaceRedirect(result, tenantSlug, projectId, query, result.ok ? { chapterId: result.value.chapter_id } : {});
  }
  async function updateChapterAction(formData: FormData) {
    "use server";
    const chapterId = stringFromFormData(formData, "chapterId");
    const result = await updateChapter(await writerWorkspaceContext(tenantSlug, projectId), chapterId, { expected_version: numberFromFormData(formData, "expectedVersion"), title: stringFromFormData(formData, "title"), outline: stringFromFormData(formData, "outline") });
    workspaceRedirect(result, tenantSlug, projectId, query, { chapterId });
  }
  async function deleteChapterAction(formData: FormData) { "use server"; workspaceRedirect(await deleteChapter(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "chapterId"), numberFromFormData(formData, "expectedVersion")), tenantSlug, projectId, query, { chapterId: "", sceneId: "" }); }
  async function reorderChaptersAction(formData: FormData) { "use server"; workspaceRedirect(await reorderChapters(await writerWorkspaceContext(tenantSlug, projectId), stringListFromFormData(formData, "orderedIds")), tenantSlug, projectId, query); }
  async function createSceneAction(formData: FormData) {
    "use server";
    const chapterId = stringFromFormData(formData, "chapterId");
    const result = await createScene(await writerWorkspaceContext(tenantSlug, projectId), chapterId, { title: stringFromFormData(formData, "title"), status: "planned" });
    workspaceRedirect(result, tenantSlug, projectId, query, { chapterId, sceneId: result.ok ? result.value.scene_id : "" });
  }
  async function updateSceneAction(formData: FormData) { "use server"; const sceneId = stringFromFormData(formData, "sceneId"); workspaceRedirect(await updateScene(await writerWorkspaceContext(tenantSlug, projectId), sceneId, { expected_version: numberFromFormData(formData, "expectedVersion"), title: stringFromFormData(formData, "title"), outline: stringFromFormData(formData, "outline") }), tenantSlug, projectId, query, { sceneId }); }
  async function createBlockAction(formData: FormData) {
    "use server";
    const contentText =
      rawStringFromFormData(formData, "contentText") || rawStringFromFormData(formData, "content") || "";
    // Prefer explicit form chapter/scene; empty means unattached free block (API allows this).
    let chapterId = stringFromFormData(formData, "chapterId");
    let sceneId = stringFromFormData(formData, "sceneId");
    // Stale selection (deleted chapter/scene) must not block creating a blank block.
    if (sceneId && !chapterId) {
      sceneId = "";
    }
    const context = await writerWorkspaceContext(tenantSlug, projectId);
    let result = await createManuscriptBlock(context, {
      chapter_id: chapterId,
      scene_id: sceneId,
      content_text: contentText,
    });
    // If chapter/scene no longer exist, fall back to an unattached blank block once.
    if (
      !result.ok &&
      (chapterId || sceneId) &&
      (result.code === "NOT_FOUND" || result.code === "HTTP_404" || result.code === "VALIDATION_FAILED")
    ) {
      result = await createManuscriptBlock(context, {
        chapter_id: "",
        scene_id: "",
        content_text: contentText,
      });
    }
    workspaceRedirect(result, tenantSlug, projectId, query, {
      blockId: result.ok ? result.value.block_id : "",
      // Clear conflict draft after save-as-new succeeds.
      ...(result.ok ? { localDraft: "" } : {}),
    });
  }
  async function deleteSceneAction(formData: FormData) { "use server"; workspaceRedirect(await deleteScene(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "sceneId"), numberFromFormData(formData, "expectedVersion")), tenantSlug, projectId, query, { sceneId: "" }); }
  async function reorderScenesAction(formData: FormData) { "use server"; const chapterId = stringFromFormData(formData, "chapterId"); workspaceRedirect(await reorderScenes(await writerWorkspaceContext(tenantSlug, projectId), chapterId, stringListFromFormData(formData, "orderedIds")), tenantSlug, projectId, query, { chapterId }); }
  async function createOutlineAction(formData: FormData) { "use server"; workspaceRedirect(await createOutline(await writerWorkspaceContext(tenantSlug, projectId), { scope_type: stringFromFormData(formData, "scopeType") || "project", scope_id: "", lifecycle: "active", title: stringFromFormData(formData, "title"), outline_text: stringFromFormData(formData, "outlineText") }), tenantSlug, projectId, query); }
  async function restoreOutlineAction(formData: FormData) { "use server"; workspaceRedirect(await restoreOutline(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "outlineVersionId")), tenantSlug, projectId, query); }
  async function createBookPlanAction(formData: FormData) { "use server"; workspaceRedirect(await createBookPlan(await writerWorkspaceContext(tenantSlug, projectId), { title: stringFromFormData(formData, "title"), status: "draft", premise: stringFromFormData(formData, "premise"), planning: "{}", target_chapter_count: optionalNumberFromFormData(formData, "targetCount") }), tenantSlug, projectId, query); }
  async function updateBookPlanAction(formData: FormData) { "use server"; workspaceRedirect(await updateBookPlan(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "bookPlanId"), { expected_version: numberFromFormData(formData, "expectedVersion"), title: stringFromFormData(formData, "title") }), tenantSlug, projectId, query); }
  async function deleteBookPlanAction(formData: FormData) { "use server"; workspaceRedirect(await deleteBookPlan(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "bookPlanId"), numberFromFormData(formData, "expectedVersion")), tenantSlug, projectId, query); }
  async function generateBookPlanAction(formData: FormData) { "use server"; const result = await startBookPlanGeneration(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "bookPlanId"), numberFromFormData(formData, "expectedVersion")); workspaceRedirect(result, tenantSlug, projectId, query, result.ok ? { planningRunId: result.value.run_id } : {}); }
  async function createPresetAction(formData: FormData) { "use server"; const context = await writerWorkspaceContext(tenantSlug, projectId); const input = { name: stringFromFormData(formData, "name"), description: "", settings: stringFromFormData(formData, "settings"), enabled: true }; workspaceRedirect(stringFromFormData(formData, "scope") === "tenant" ? await upsertTenantPreset(context, input) : await upsertProjectPreset(context, input), tenantSlug, projectId, query); }
  async function deletePresetAction(formData: FormData) { "use server"; workspaceRedirect(await deletePreset(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "presetId")), tenantSlug, projectId, query); }
  async function createLexiconAction(formData: FormData) { "use server"; workspaceRedirect(await upsertLexicon(await writerWorkspaceContext(tenantSlug, projectId), { term: stringFromFormData(formData, "term"), category: "style", severity: stringFromFormData(formData, "severity"), replacement_guidance: stringFromFormData(formData, "guidance"), enabled: true }), tenantSlug, projectId, query); }
  async function deleteLexiconAction(formData: FormData) { "use server"; workspaceRedirect(await deleteLexicon(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "entryId")), tenantSlug, projectId, query); }
  async function updateBlockAction(formData: FormData) {
    "use server";
    const blockId = stringFromFormData(formData, "blockId");
    // Do not trim manuscript body — trailing newlines are author content.
    const contentText = rawStringFromFormData(formData, "content");
    // Prefer explicit localDraft field so OPTIMISTIC_CONFLICT can restore the author's text.
    const localDraft = rawStringFromFormData(formData, "localDraft") || contentText;
    const result = await updateManuscriptBlock(await writerWorkspaceContext(tenantSlug, projectId), blockId, {
      expected_version: numberFromFormData(formData, "expectedVersion"),
      content_text: contentText,
      status: stringFromFormData(formData, "status"),
    });
    workspaceRedirect(result, tenantSlug, projectId, query, {
      blockId,
      ...(result.ok ? { localDraft: "" } : { localDraft }),
    });
  }
  async function deleteBlockAction(formData: FormData) { "use server"; workspaceRedirect(await deleteManuscriptBlock(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "blockId"), numberFromFormData(formData, "expectedVersion")), tenantSlug, projectId, query, { blockId: "" }); }
  async function tagBlockAction(formData: FormData) { "use server"; const blockId = stringFromFormData(formData, "blockId"); workspaceRedirect(await tagManuscriptBlock(await writerWorkspaceContext(tenantSlug, projectId), blockId, numberFromFormData(formData, "expectedVersion"), splitList(stringFromFormData(formData, "tags"))), tenantSlug, projectId, query, { blockId }); }
  async function reorderBlocksAction(formData: FormData) { "use server"; const items = versionedItemsFromFormData(formData, "orderedBlockItems"); workspaceRedirect(await reorderManuscriptBlocks(await writerWorkspaceContext(tenantSlug, projectId), items.length ? items : versionedItemsFromFormData(formData, "items")), tenantSlug, projectId, query); }
  async function moveBlockAction(formData: FormData) {
    "use server";
    const blockId = stringFromFormData(formData, "blockId");
    const context = await writerWorkspaceContext(tenantSlug, projectId);
    const currentBlocks = await listManuscriptBlocks(context, true);
    const items = currentBlocks.ok
      ? currentBlocks.value
          .filter((block) => block.status !== "deleted")
          .map((block) => ({ block_id: block.block_id, expected_version: block.version }))
      : [];
    workspaceRedirect(await moveManuscriptBlock(context, blockId, { expected_version: numberFromFormData(formData, "expectedVersion"), chapter_id: stringFromFormData(formData, "chapterId"), scene_id: stringFromFormData(formData, "sceneId"), items }), tenantSlug, projectId, query, { blockId });
  }
  async function restoreBlockAction(formData: FormData) { "use server"; const blockId = stringFromFormData(formData, "blockId"); workspaceRedirect(await restoreManuscriptVersion(await writerWorkspaceContext(tenantSlug, projectId), blockId, stringFromFormData(formData, "versionId"), numberFromFormData(formData, "expectedVersion")), tenantSlug, projectId, query, { blockId }); }
  async function decideDedupAction(formData: FormData) { "use server"; const decision = stringFromFormData(formData, "decision") === "reject" ? "reject" : "accept"; workspaceRedirect(await decideDedupPattern(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "patternId"), decision), tenantSlug, projectId, query); }
  async function startDistillationAction(formData: FormData) {
    "use server";
    const blockId = stringFromFormData(formData, "blockId");
    const context = await writerWorkspaceContext(tenantSlug, projectId);
    const blocks = await listManuscriptBlocks(context, true);
    const expected: Record<string, number> = {};
    if (blocks.ok) {
      for (const block of blocks.value) {
        if (!blockId || block.block_id === blockId) expected[block.block_id] = block.version;
      }
    }
    workspaceRedirect(await startManuscriptAssetDistillation(context, {
      block_ids: blockId ? [blockId] : Object.keys(expected),
      expected_versions: expected,
    }), tenantSlug, projectId, query);
  }
  async function decideProposalAction(formData: FormData) {
    "use server";
    workspaceRedirect(await decideAssetProposal(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "candidateAssetId"), {
      decision: stringFromFormData(formData, "decision"),
      target_lifecycle: stringFromFormData(formData, "targetLifecycle") || "canon",
      target_asset_id: stringFromFormData(formData, "targetAssetId"),
      expected_target_version: Number(stringFromFormData(formData, "expectedTargetVersion") || "0"),
      note: stringFromFormData(formData, "note"),
    }), tenantSlug, projectId, query);
  }
  async function patchDistillationSettingsAction(formData: FormData) {
    "use server";
    workspaceRedirect(await patchAssetDistillationSettings(await writerWorkspaceContext(tenantSlug, projectId), {
      trigger_mode: stringFromFormData(formData, "triggerMode") || "manual",
    }), tenantSlug, projectId, query);
  }
  async function startDedupAction(formData: FormData) { "use server"; const sourceKind = stringFromFormData(formData, "sourceKind"); const blockId = stringFromFormData(formData, "blockId"); const chapterId = stringFromFormData(formData, "chapterId"); const result = await startDedupExtraction(await writerWorkspaceContext(tenantSlug, projectId), { block_ids: sourceKind === "block" && blockId ? [blockId] : [], chapter_id: sourceKind === "chapter" ? chapterId : "" }); workspaceRedirect(result, tenantSlug, projectId, query, result.ok ? { planningRunId: result.value.run_id } : {}); }
  async function startCommandAction(formData: FormData) { "use server"; const result = await startManuscriptCommand(await writerWorkspaceContext(tenantSlug, projectId), { command_type: manuscriptCommandKeyFromChoice(stringFromFormData(formData, "commandChoice")), target_chapter_id: stringFromFormData(formData, "targetChapterId"), target_scene_id: stringFromFormData(formData, "targetSceneId"), target_block_id: stringFromFormData(formData, "targetBlockId"), options: {} }); workspaceRedirect(result, tenantSlug, projectId, query, result.ok ? { commandId: result.value.run.command_run_id } : {}); }
  async function createExportAction(formData: FormData) { "use server"; workspaceRedirect(await createWorkspaceExport(await writerWorkspaceContext(tenantSlug, projectId), stringFromFormData(formData, "format") || "txt"), tenantSlug, projectId, query); }

  async function decideApprovalAction(formData: FormData) {
    "use server";
    const approvalId = stringFromFormData(formData, "approvalId");
    const decisionRaw = stringFromFormData(formData, "decision");
    const decision = decisionRaw === "approve" || decisionRaw === "reject" ? decisionRaw : "";
    if (!approvalId || !decision) {
      const nextQuery = new URLSearchParams({
        writerControlStatus: "error",
        writerControlCode: "VALIDATION_FAILED",
      });
      if (query.runId) {
        nextQuery.set("runId", query.runId);
      }
      redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
    }
    const result = await decideWriterApproval({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      approvalId,
      decision,
    });
    const nextQuery = new URLSearchParams({
      writerControlStatus: result.ok ? "success" : "error",
      writerControlCode: result.ok ? "WRITER_APPROVAL_DECIDED" : result.code,
    });
    if (query.runId) {
      nextQuery.set("runId", query.runId);
    }
    if (query.traceId) {
      nextQuery.set("traceId", query.traceId);
    }
    redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
  }

  const adoptedDraftBlock = manuscript.ok
    ? manuscript.blocks.find(
        (block) => block.source_draft_id === recoveredDraftId && block.status !== "deleted",
      )
    : undefined;

  return (
    <WriterWorkbenchShell
      locale={locale}
      tenantSlug={tenantSlug}
      projectId={projectId}
      runSummary={runSummary}
      workflowEvents={workflowEvents}
      traceEvents={traceEvents}
      assets={assets}
      graphView={graphView}
      worldlineSavedPaths={worldlineSavedPaths}
      manuscript={manuscript}
      afterEventId={afterEventId}
      selectedRunId={selectedRunId}
      selectedTraceId={selectedTraceId}
      selectedDraftId={selectedDraftId}
      selectedChapterId={selectedChapterId}
      selectedSceneId={selectedSceneId}
      threadMessages={threadMessages}
      decideApprovalAction={decideApprovalAction}
      draftAdoptionStatus={
        query.draftAdoptionStatus
          ? { status: query.draftAdoptionStatus, code: query.draftAdoptionCode ?? "", message: "" }
          : null
      }
      writerControlStatus={
        query.writerControlStatus
          ? { status: query.writerControlStatus, code: query.writerControlCode ?? "", message: "" }
          : null
      }
      writerRunStatus={
        query.writerRunStatus
          ? {
              status: query.writerRunStatus,
              code: query.writerRunCode ?? "",
              message: query.writerRunMessage ?? "",
            }
          : null
      }
      traceExportStatus={
        query.traceExportStatus
          ? {
              status: query.traceExportStatus,
              code: query.traceExportCode ?? "",
              message: query.traceExportMessage ?? "",
            }
          : null
      }
      writerRunAction={startWriterRunAction}
      exportTraceAction={exportTraceAction}
      cancelWriterRunAction={cancelWriterRunAction}
      productWorkspace={
        <Suspense fallback={<WriterProductWorkspaceLoading />}>
          <WriterProductWorkspaceData
            actionStatus={query.workspaceStatus ? { status: query.workspaceStatus, code: query.workspaceCode ?? "" } : null}
            actions={{ createChapter: createChapterAction, updateChapter: updateChapterAction, deleteChapter: deleteChapterAction,
              reorderChapters: reorderChaptersAction, createScene: createSceneAction, updateScene: updateSceneAction,
              deleteScene: deleteSceneAction, reorderScenes: reorderScenesAction, createOutline: createOutlineAction,
              restoreOutline: restoreOutlineAction, createBookPlan: createBookPlanAction, updateBookPlan: updateBookPlanAction,
              deleteBookPlan: deleteBookPlanAction, generateBookPlan: generateBookPlanAction, createPreset: createPresetAction, deletePreset: deletePresetAction,
              createLexicon: createLexiconAction, deleteLexicon: deleteLexiconAction, startReview: startDraftReviewAction,
              updateReviewIssue: updateReviewIssueAction, createBlock: createBlockAction, updateBlock: updateBlockAction, deleteBlock: deleteBlockAction,
              reorderBlocks: reorderBlocksAction, moveBlock: moveBlockAction, tagBlock: tagBlockAction,
              restoreBlock: restoreBlockAction, startDedup: startDedupAction, decideDedup: decideDedupAction, startCommand: startCommandAction,
              createExport: createExportAction, startDistillation: startDistillationAction, decideProposal: decideProposalAction,
              patchDistillationSettings: patchDistillationSettingsAction, reviseSelection: reviseSelectionAction }}
            locale={locale}
            localDraft={decodeLocalDraft(query.localDraft)}
            projectId={projectId}
            draftBlock={
              <WriterDraftBlock
                adoptDraftAction={adoptDraftAction}
                adopted={Boolean(adoptedDraftBlock)}
                adoptedBlockId={adoptedDraftBlock?.block_id ?? ""}
                chapterId={selectedChapterId}
                draftId={recoveredDraftId}
                initialEvents={workflowEvents?.ok === true ? workflowEvents.items : []}
                locale={locale}
                undoAdoptionAction={undoDraftAdoptionAction}
              />
            }
            selectedBlockId={selectedBlockId}
            selectedChapterId={selectedChapterId}
            selectedCommandId={selectedCommandId}
            selectedDraftId={recoveredDraftId}
            selectedPlanningRunId={selectedPlanningRunId}
            selectedSceneId={selectedSceneId}
            tenantSlug={tenantSlug}
            workflowEvents={workflowEvents}
            workspaceContext={workspaceContext}
          />
        </Suspense>
      }
    />
  );
}

type WriterProductWorkspaceDataProps = Pick<
  WriterProductWorkspaceProps,
  | "actionStatus"
  | "actions"
  | "draftBlock"
  | "locale"
  | "localDraft"
  | "projectId"
  | "selectedBlockId"
  | "selectedChapterId"
  | "selectedCommandId"
  | "selectedDraftId"
  | "selectedSceneId"
  | "tenantSlug"
> & {
  selectedPlanningRunId: string;
  workflowEvents: Awaited<ReturnType<typeof getAllWriterRunEvents>> | null;
  workspaceContext: WriterWebContext;
};

const MANUSCRIPT_FLOW_CONTENT_LIMIT = 20;

async function WriterProductWorkspaceData({
  selectedPlanningRunId,
  workflowEvents,
  workspaceContext,
  ...props
}: WriterProductWorkspaceDataProps) {
  const [chapters, blocks, outlines, bookPlans, presets, lexicon, reviews, dedupPatterns, command, exports, planningRun, proposals, distillationSettings] = await Promise.all([
    listChapters(workspaceContext),
    listManuscriptBlocks(workspaceContext, true),
    listOutlines(workspaceContext), listBookPlans(workspaceContext), listPresets(workspaceContext), listLexicon(workspaceContext),
    listDraftReviews(workspaceContext, props.selectedDraftId),
    listDedupPatterns(workspaceContext), getManuscriptCommand(workspaceContext, props.selectedCommandId), listWorkspaceExports(workspaceContext), getWriterPlanningRun(workspaceContext, selectedPlanningRunId),
    listAssetProposals(workspaceContext, "pending"), getAssetDistillationSettings(workspaceContext),
  ]);

  const effectiveChapterId =
    props.selectedChapterId
    || (chapters.ok && chapters.value[0] ? chapters.value[0].chapter_id : "");

  const chapterBlocks = pickChapterFlowBlocks(blocks, effectiveChapterId);
  const effectiveBlockId =
    props.selectedBlockId
    || (chapterBlocks[0]?.block_id ?? "");

  const [scenes, chapterVersions, sceneVersions, selectedBlock, blockVersions, privateResults] = await Promise.all([
    listScenes(workspaceContext, effectiveChapterId),
    effectiveChapterId ? listChapterVersions(workspaceContext, effectiveChapterId) : emptyResult<WritingVersion>(),
    props.selectedSceneId ? listSceneVersions(workspaceContext, props.selectedSceneId) : emptyResult<WritingVersion>(),
    getPrivateBlock(workspaceContext, effectiveBlockId),
    listManuscriptVersions(workspaceContext, effectiveBlockId),
    Promise.all(chapterBlocks.map((block) => getPrivateBlock(workspaceContext, block.block_id))),
  ]);

  const blockContents: PrivateManuscriptBlock[] = chapterBlocks.map((meta, index) => {
    const priv = privateResults[index];
    if (priv?.ok && priv.value) return priv.value;
    return { ...meta, content_text: "" };
  });

  const pendingRevision =
    selectedBlock.ok && selectedBlock.value
      ? pendingRevisionFromWriterEvents(workflowEvents, {
          blockId: selectedBlock.value.block_id,
          contentText: selectedBlock.value.content_text,
          expectedVersion: selectedBlock.value.version,
        })
      : null;

  return (
    <WriterProductWorkspace
      {...props}
      blockContents={blockContents}
      blocks={blocks}
      blockVersions={blockVersions}
      bookPlans={bookPlans}
      chapters={chapters}
      chapterVersions={chapterVersions}
      command={command}
      dedupPatterns={dedupPatterns}
      distillationSettings={distillationSettings}
      exports={exports}
      lexicon={lexicon}
      outlines={outlines}
      pendingRevision={pendingRevision}
      planningRun={planningRun}
      presets={presets}
      proposals={proposals}
      reviews={reviews}
      scenes={scenes}
      sceneVersions={sceneVersions}
      selectedBlock={selectedBlock}
      selectedBlockId={effectiveBlockId}
      selectedChapterId={effectiveChapterId}
    />
  );
}

function pickChapterFlowBlocks(
  blocks: WriterWebResult<ManuscriptBlock[]>,
  chapterId: string,
): ManuscriptBlock[] {
  if (!blocks.ok) return [];
  return blocks.value
    .filter((block) => block.status !== "deleted")
    .filter((block) => {
      if (chapterId) return (block.chapter_id ?? "") === chapterId;
      return !block.chapter_id;
    })
    .slice()
    .sort((a, b) => a.block_order - b.block_order)
    .slice(0, MANUSCRIPT_FLOW_CONTENT_LIMIT);
}

function writerActionHeaders(context: Awaited<ReturnType<typeof webApiContext>>) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Tenant-Id": context.tenantId,
  };
  if (context.actorUserId) headers["X-User-Id"] = context.actorUserId;
  if (context.sessionCookie) headers.Cookie = `mirofish_session=${context.sessionCookie}`;
  if (context.csrfToken) headers["X-CSRF-Token"] = context.csrfToken;
  return headers;
}

function writerSelectionQuery(query: Record<string, string | undefined>, draftId: string) {
  const next = new URLSearchParams();
  for (const key of ["runId", "traceId", "after_event_id"] as const) {
    const value = query[key];
    if (value) next.set(key, value);
  }
  if (draftId) next.set("draftId", draftId);
  return next;
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function rawStringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value : "";
}

function stringListFromFormData(formData: FormData, key: string) {
  return formData
    .getAll(key)
    .flatMap((value) => typeof value === "string" ? splitList(value) : [])
    .filter((value, index, items) => value && items.indexOf(value) === index);
}

function splitList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function graphNodeSelectionsFromFormData(formData: FormData, key: string) {
  const ids: string[] = [];
  const names: string[] = [];
  for (const selection of stringListFromFormData(formData, key)) {
    const [id, title] = selection.split("\t");
    if (id && !ids.includes(id)) {
      ids.push(id);
    }
    if (title && !names.includes(title)) {
      names.push(title);
    }
  }
  return { ids, names };
}

function writerModeFromFormData(formData: FormData): "draft" | "continue" | "outline" | "revise" {
  const mode = stringFromFormData(formData, "mode");
  if (mode === "continue" || mode === "outline" || mode === "revise") return mode;
  return "draft";
}

function reviseOptionsFromFormData(formData: FormData) {
  const blockId = stringFromFormData(formData, "blockId");
  const selectionText = stringFromFormData(formData, "selectionText");
  if (!blockId || !selectionText) return null;
  const action = stringFromFormData(formData, "reviseAction");
  const allowed = new Set(["rewrite", "expand", "condense", "polish", "correct", "custom"]);
  const selectionStart = numberFromFormData(formData, "selectionStart");
  const selectionEnd = numberFromFormData(formData, "selectionEnd");
  const expectedVersion = numberFromFormData(formData, "expectedVersion");
  return {
    block_id: blockId,
    selection_text: selectionText,
    ...(selectionStart > 0 || stringFromFormData(formData, "selectionStart") === "0"
      ? { selection_start: selectionStart }
      : {}),
    ...(selectionEnd > 0 ? { selection_end: selectionEnd } : {}),
    ...(expectedVersion > 0 ? { expected_version: expectedVersion } : {}),
    ...(allowed.has(action) ? { action } : {}),
  };
}

function draftIdFromWriterEvents(selectedDraftId: string, events: Awaited<ReturnType<typeof getAllWriterRunEvents>> | null) {
  if (selectedDraftId) return selectedDraftId;
  if (!events?.ok) return "";
  for (let index = events.items.length - 1; index >= 0; index -= 1) {
    const draftId = events.items[index]?.payload.draft_id;
    if (typeof draftId === "string" && draftId.trim()) return draftId.trim();
  }
  return "";
}

async function writerWorkspaceContext(tenantId: string, projectId: string): Promise<WriterWebContext> {
  return { ...(await webApiContext({ tenantId, projectId })), projectId };
}

function workspaceRedirect(
  result: WriterWebResult<unknown>,
  tenantSlug: string,
  projectId: string,
  query: Record<string, string | undefined>,
  selections: Record<string, string> = {},
): never {
  const next = workspaceSelectionQuery(query, selections);
  next.set("workspaceStatus", result.ok ? "success" : "error");
  next.set("workspaceCode", result.ok ? "WORKSPACE_ACTION_COMPLETED" : result.code);
  if (result.ok) {
    // Successful save clears any prior conflict draft from the URL.
    next.delete("localDraft");
  } else if (result.code === "OPTIMISTIC_CONFLICT") {
    // Preserve local draft so the manuscript panel can offer compare / overwrite / save-as.
    // Cap query size: the client also mirrors drafts in sessionStorage before submit.
    const rawLocalDraft = selections.localDraft ?? "";
    const decodedQueryDraft = decodeLocalDraft(query.localDraft);
    const draftText = rawLocalDraft || decodedQueryDraft;
    const encoded = draftText ? encodeLocalDraft(draftText) : "";
    if (encoded && encoded.length <= 3500) {
      next.set("localDraft", encoded);
    } else if (draftText) {
      // Marker only — panel recovers full text from sessionStorage for this block.
      next.set("localDraft", "session");
    }
    if (selections.blockId || query.blockId) next.set("blockId", selections.blockId || query.blockId || "");
  }
  redirect(`/${tenantSlug}/projects/${projectId}/writer?${next.toString()}`);
}

function workspaceSelectionQuery(query: Record<string, string | undefined>, selections: Record<string, string>) {
  const next = new URLSearchParams();
  for (const key of ["runId", "traceId", "after_event_id", "draftId", "chapterId", "sceneId", "blockId", "commandId", "planningRunId"] as const) {
    const value = Object.hasOwn(selections, key) ? selections[key] : query[key];
    if (value) next.set(key, value);
  }
  return next;
}

function numberFromFormData(formData: FormData, key: string) {
  const value = Number(stringFromFormData(formData, key));
  return Number.isSafeInteger(value) && value > 0 ? value : 0;
}

function optionalNumberFromFormData(formData: FormData, key: string) {
  const value = numberFromFormData(formData, key);
  return value > 0 ? value : undefined;
}

function versionedItemsFromFormData(formData: FormData, key: string) {
  return formData
    .getAll(key)
    .flatMap((value) => (typeof value === "string" ? splitList(value) : []))
    .map((item) => {
      const [block_id, rawVersion] = item.split(":");
      return { block_id, expected_version: Number(rawVersion) };
    })
    .filter((item) => item.block_id && Number.isSafeInteger(item.expected_version) && item.expected_version > 0);
}

function emptyResult<T>(): WriterWebResult<T[]> {
  return { ok: true, value: [] };
}
