import { redirect } from "next/navigation";
import { StoryGraphShell } from "../../../../../../components/story-graph-shell";
import { storyGraphBondStatus, storyGraphBuildStatus } from "../../../../../../components/story-graph-status";
import {
  adoptStoryGraphCandidate,
  getProjectAnalysisRuns,
  getProjectAssets,
  getProjectSourceFiles,
  getWorkflowRunEvents,
  getWorkflowRunSummary,
  getStoryGraphClusters,
  getStoryGraphCurrent,
  getStoryGraphEvidence,
  getStoryGraphLayout,
  getStoryGraphView,
  startStoryGraphBondGeneration,
  startStoryGraphBuild,
  type AnalysisRunsSummary,
  type AssetListSummary,
  type SourceFilesSummary,
  type StoryGraphCandidateAdoptionSummary,
  type StoryGraphEvidenceSummary,
} from "../../../../../../lib/api";
import { tx } from "../../../../../../lib/locale";
import { currentRequestLocale } from "../../../../../../lib/request-locale";
import { webApiContext, webReadApiContext } from "../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";

export default async function StoryGraphPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    buildCode?: string;
    buildMessage?: string;
    buildStatus?: string;
    bondCode?: string;
    bondMessage?: string;
    bondStatus?: string;
    bondRunId?: string;
    mode?: string;
    runId?: string;
    storyGraphAdoptionCode?: string;
    storyGraphAdoptionMessage?: string;
    storyGraphAdoptionStatus?: string;
    storyGraphAdoptionTargetId?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const apiContext = webReadApiContext({ tenantId: tenantSlug, projectId });
  const selectedRunId = query.bondRunId || query.runId || "";
  const workflowContext = selectedRunId ? webReadApiContext({ tenantId: tenantSlug }) : null;
  const [
    current,
    view,
    layout,
    clusters,
    projectAssets,
    analysisRuns,
    sourceFiles,
    workflowRun,
    workflowEvents,
  ] = await Promise.all([
    getStoryGraphCurrent(apiContext),
    getStoryGraphView({
      ...apiContext,
      viewId: "world",
      limit: 300,
      includeEdges: true,
    }),
    getStoryGraphLayout({
      ...apiContext,
      viewId: "world",
    }),
    getStoryGraphClusters({
      ...apiContext,
      limit: 50,
    }),
    getProjectAssets(apiContext),
    getProjectAnalysisRuns(apiContext),
    getProjectSourceFiles(apiContext),
    selectedRunId && workflowContext
      ? getWorkflowRunSummary({ ...workflowContext, runId: selectedRunId })
      : Promise.resolve(null),
    selectedRunId && workflowContext
      ? getWorkflowRunEvents({ ...workflowContext, runId: selectedRunId })
      : Promise.resolve(null),
  ]);
  const evidence = await firstEvidenceSummary(apiContext, view, locale);
  const graphCandidates = graphCandidatesFromAssets(projectAssets);
  const analysisBuildOptions = analysisBuildOptionsFromRuns(analysisRuns, sourceFiles, locale);
  const initialWorkspaceMode = resolveInitialWorkspaceMode(query);

  async function buildAction(formData: FormData) {
    "use server";

    const source = stringFromFormData(formData, "source") || "assets";
    const analysisRunId = stringFromFormData(formData, "analysisRunId");
    const result = await startStoryGraphBuild({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      mode: stringFromFormData(formData, "mode") || "full",
      options: {
        source,
        ...(analysisRunId ? { analysis_run_id: analysisRunId } : {}),
      },
    });
    const status = storyGraphBuildStatus(result, locale);
    redirect(storyGraphRoute({
      tenantSlug,
      projectId,
      mode: "build",
      buildStatus: status.status,
      buildCode: status.code,
      buildMessage: status.message,
      runId: status.runId,
      bondStatus: query.bondStatus ?? "",
      bondCode: query.bondCode ?? "",
      bondMessage: query.bondMessage ?? "",
      bondRunId: query.bondRunId ?? "",
    }));
  }

  async function bondAction(formData: FormData) {
    "use server";

    const result = await startStoryGraphBondGeneration({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      graphId: stringFromFormData(formData, "graphId"),
      nodeIds: stringListFromFormData(formData, "nodeIds"),
      focus: stringFromFormData(formData, "focus"),
      options: {
        mode: stringFromFormData(formData, "mode") || "bonds_and_threads",
      },
    });
    const status = storyGraphBondStatus(result, locale);
    redirect(storyGraphRoute({
      tenantSlug,
      projectId,
      mode: "compose",
      buildStatus: query.buildStatus ?? "",
      buildCode: query.buildCode ?? "",
      buildMessage: query.buildMessage ?? "",
      runId: query.runId ?? "",
      bondStatus: status.status,
      bondCode: status.code,
      bondMessage: status.message,
      bondRunId: status.runId,
    }));
  }

  async function adoptStoryGraphCandidateAction(formData: FormData) {
    "use server";

    const targetKind = targetKindFromFormData(formData);
    if (!targetKind) {
      redirect(storyGraphRoute({
        tenantSlug,
        projectId,
        mode: "curate",
        buildStatus: query.buildStatus ?? "",
        buildCode: query.buildCode ?? "",
        buildMessage: query.buildMessage ?? "",
        runId: query.runId ?? "",
        bondStatus: query.bondStatus ?? "",
        bondCode: query.bondCode ?? "",
        bondMessage: query.bondMessage ?? "",
        bondRunId: query.bondRunId ?? "",
        storyGraphAdoptionStatus: "error",
        storyGraphAdoptionCode: "STORY_GRAPH_CANDIDATE_ADOPTION_VALIDATION_FAILED",
        storyGraphAdoptionMessage: tx(locale, "请选择采用类型", "Choose an adoption type"),
        storyGraphAdoptionTargetId: "",
      }));
    }
    const result = await adoptStoryGraphCandidate({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      assetId: stringFromFormData(formData, "assetId"),
      targetKind,
    });
    const status = storyGraphAdoptionStatus(result, locale);
    redirect(storyGraphRoute({
      tenantSlug,
      projectId,
      mode: "curate",
      buildStatus: query.buildStatus ?? "",
      buildCode: query.buildCode ?? "",
      buildMessage: query.buildMessage ?? "",
      runId: query.runId ?? "",
      bondStatus: query.bondStatus ?? "",
      bondCode: query.bondCode ?? "",
      bondMessage: query.bondMessage ?? "",
      bondRunId: query.bondRunId ?? "",
      storyGraphAdoptionStatus: status.status,
      storyGraphAdoptionCode: status.code,
      storyGraphAdoptionMessage: status.message,
      storyGraphAdoptionTargetId: status.targetId,
    }));
  }

  return (
    <StoryGraphShell
      locale={locale}
      tenantSlug={tenantSlug}
      projectId={projectId}
      current={current}
      view={view}
      evidence={evidence}
      layout={layout}
      clusters={clusters}
      graphCandidates={graphCandidates}
      analysisBuildOptions={analysisBuildOptions}
      initialWorkspaceMode={initialWorkspaceMode}
      buildStatus={query.buildStatus ?? ""}
      buildCode={query.buildCode ?? ""}
      buildMessage={query.buildMessage ?? ""}
      bondStatus={query.bondStatus ?? ""}
      bondCode={query.bondCode ?? ""}
      bondMessage={query.bondMessage ?? ""}
      adoptionStatus={query.storyGraphAdoptionStatus ?? ""}
      adoptionCode={query.storyGraphAdoptionCode ?? ""}
      adoptionMessage={query.storyGraphAdoptionMessage ?? ""}
      adoptionTargetId={query.storyGraphAdoptionTargetId ?? ""}
      selectedRunId={selectedRunId}
      selectedBuildRunId={query.runId ?? ""}
      selectedBondRunId={query.bondRunId ?? ""}
      workflowRun={workflowRun}
      workflowEvents={workflowEvents}
      buildAction={buildAction}
      bondAction={bondAction}
      adoptStoryGraphCandidateAction={adoptStoryGraphCandidateAction}
    />
  );
}

function storyGraphRoute(input: {
  tenantSlug: string;
  projectId: string;
  mode?: string;
  buildStatus: string;
  buildCode: string;
  buildMessage: string;
  runId: string;
  bondStatus: string;
  bondCode: string;
  bondMessage: string;
  bondRunId: string;
  storyGraphAdoptionStatus?: string;
  storyGraphAdoptionCode?: string;
  storyGraphAdoptionMessage?: string;
  storyGraphAdoptionTargetId?: string;
}) {
  const query = new URLSearchParams();
  setQueryIfPresent(query, "mode", input.mode ?? "");
  setQueryIfPresent(query, "buildStatus", input.buildStatus);
  setQueryIfPresent(query, "buildCode", input.buildCode);
  setQueryIfPresent(query, "buildMessage", input.buildMessage);
  if (input.runId) {
    query.set("runId", input.runId);
  }
  setQueryIfPresent(query, "bondStatus", input.bondStatus);
  setQueryIfPresent(query, "bondCode", input.bondCode);
  setQueryIfPresent(query, "bondMessage", input.bondMessage);
  if (input.bondRunId) {
    query.set("bondRunId", input.bondRunId);
  }
  setQueryIfPresent(query, "storyGraphAdoptionStatus", input.storyGraphAdoptionStatus ?? "");
  setQueryIfPresent(query, "storyGraphAdoptionCode", input.storyGraphAdoptionCode ?? "");
  setQueryIfPresent(query, "storyGraphAdoptionMessage", input.storyGraphAdoptionMessage ?? "");
  setQueryIfPresent(query, "storyGraphAdoptionTargetId", input.storyGraphAdoptionTargetId ?? "");
  return `/${input.tenantSlug}/projects/${input.projectId}/graph?${query.toString()}`;
}

type StoryGraphWorkspaceMode = "explore" | "build" | "curate" | "compose";

function resolveInitialWorkspaceMode(query: {
  mode?: string;
  buildStatus?: string;
  bondStatus?: string;
  bondRunId?: string;
  runId?: string;
  storyGraphAdoptionStatus?: string;
}): StoryGraphWorkspaceMode {
  const mode = query.mode?.trim();
  if (mode === "explore" || mode === "build" || mode === "curate" || mode === "compose") {
    return mode;
  }
  if (query.buildStatus || query.runId) {
    return "build";
  }
  if (query.bondStatus || query.bondRunId) {
    return "compose";
  }
  if (query.storyGraphAdoptionStatus) {
    return "curate";
  }
  return "explore";
}

function analysisBuildOptionsFromRuns(
  analysisRuns: AnalysisRunsSummary,
  sourceFiles: SourceFilesSummary,
  locale: "zh-CN" | "en",
) {
  if (!analysisRuns.ok) {
    return {
      ok: false as const,
      code: analysisRuns.code,
      message: analysisRuns.message,
      items: [] as Array<{ runId: string; label: string; status: string }>,
    };
  }
  const filenameByUploadId = new Map<string, string>();
  const filenameByFileId = new Map<string, string>();
  if (sourceFiles.ok) {
    for (const file of sourceFiles.items) {
      filenameByUploadId.set(file.upload_id, file.filename);
      filenameByFileId.set(file.file_id, file.filename);
    }
  }
  const completed = analysisRuns.items
    .filter((run): run is Extract<typeof run, { ok: true }> => run.ok && run.status === "completed")
    .map((run, index, items) => {
      const filename = (run.source_file_id && filenameByFileId.get(run.source_file_id))
        || (run.upload_id && filenameByUploadId.get(run.upload_id))
        || "";
      const ordinal = items.length - index;
      const base = filename
        ? filename
        : tx(locale, `分析 ${ordinal}`, `Analysis ${ordinal}`);
      return {
        runId: run.run_id,
        label: filename
          ? tx(locale, `${filename} · 已完成`, `${filename} · completed`)
          : tx(locale, `${base} · 已完成`, `${base} · completed`),
        status: run.status,
      };
    });
  return {
    ok: true as const,
    items: completed,
  };
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function stringListFromFormData(formData: FormData, key: string) {
  return formData.getAll(key)
    .flatMap((value) => typeof value === "string" ? value.split(/[\n,]/) : [])
    .map((value) => value.trim())
    .filter(Boolean);
}

function targetKindFromFormData(formData: FormData): "relationship" | "plot_thread" | null {
  const targetKind = stringFromFormData(formData, "targetKind");
  if (targetKind === "relationship" || targetKind === "plot_thread") {
    return targetKind;
  }
  return null;
}

function storyGraphAdoptionStatus(result: StoryGraphCandidateAdoptionSummary, locale: "zh-CN" | "en") {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
      targetId: "",
    };
  }
  const targetLabel = result.target_kind === "relationship"
    ? tx(locale, "关系", "a relationship")
    : tx(locale, "剧情线索", "a plot thread");
  return {
    status: "success",
    code: "STORY_GRAPH_CANDIDATE_ADOPTED",
    message: tx(locale, `候选项已采用为${targetLabel}`, `Candidate adopted as ${targetLabel}`),
    targetId: result.target_id,
  };
}

function graphCandidatesFromAssets(assets: AssetListSummary): AssetListSummary {
  if (!assets.ok) {
    return assets;
  }
  return {
    ok: true,
    items: assets.items
      .filter((asset) => asset.source_kind === "graph_bond_generation" && asset.lifecycle === "candidate")
      .map((asset) => ({
        ...asset,
        tags: [],
        payload: {},
      })),
  };
}

function setQueryIfPresent(query: URLSearchParams, key: string, value: string) {
  if (value) {
    query.set(key, value);
  }
}

async function firstEvidenceSummary(
  apiContext: { tenantId: string; actorUserId?: string; sessionCookie?: string; projectId: string },
  view: Awaited<ReturnType<typeof getStoryGraphView>>,
  locale: "zh-CN" | "en",
): Promise<StoryGraphEvidenceSummary> {
  if (!view.ok) {
    return {
      ok: false,
      code: view.code,
      message: view.message,
      request_id: view.request_id,
    };
  }
  const firstNode = view.nodes[0];
  if (!firstNode) {
    return {
      ok: false,
      code: "STORY_GRAPH_SELECTION_UNAVAILABLE",
      message: tx(locale, "请选择故事图谱节点或关系后查看证据", "Select a story graph node or edge to view evidence"),
      request_id: "web-shell",
    };
  }
  return await getStoryGraphEvidence({
    ...apiContext,
    ownerType: "node",
    ownerId: firstNode.node_id,
    limit: 25,
  });
}
