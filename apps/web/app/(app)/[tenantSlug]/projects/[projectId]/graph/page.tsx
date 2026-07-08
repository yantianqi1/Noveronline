import { redirect } from "next/navigation";
import { StoryGraphShell, storyGraphBondStatus, storyGraphBuildStatus } from "../../../../../../components/story-graph-shell";
import {
  adoptStoryGraphCandidate,
  getProjectAssets,
  getWorkflowRunEvents,
  getWorkflowRunSummary,
  getStoryGraphClusters,
  getStoryGraphCurrent,
  getStoryGraphEvidence,
  getStoryGraphLayout,
  getStoryGraphView,
  startStoryGraphBondGeneration,
  startStoryGraphBuild,
  type AssetListSummary,
  type StoryGraphCandidateAdoptionSummary,
  type StoryGraphEvidenceSummary,
} from "../../../../../../lib/api";
import { webApiContext } from "../../../../../../lib/server-auth";

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
    runId?: string;
    storyGraphAdoptionCode?: string;
    storyGraphAdoptionMessage?: string;
    storyGraphAdoptionStatus?: string;
    storyGraphAdoptionTargetId?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const apiContext = await webApiContext({ tenantId: tenantSlug, projectId });
  const current = await getStoryGraphCurrent(apiContext);
  const view = await getStoryGraphView({
    ...apiContext,
    viewId: "world",
    limit: 300,
    includeEdges: true,
  });
  const evidence = await firstEvidenceSummary(apiContext, view);
  const layout = await getStoryGraphLayout({
    ...apiContext,
    viewId: "world",
  });
  const clusters = await getStoryGraphClusters({
    ...apiContext,
    limit: 50,
  });
  const graphCandidates = graphCandidatesFromAssets(await getProjectAssets(apiContext));
  const selectedRunId = query.bondRunId || query.runId || "";
  const workflowRun = selectedRunId ? await getWorkflowRunSummary({
    ...(await webApiContext({ tenantId: tenantSlug })),
    runId: selectedRunId,
  }) : null;
  const workflowEvents = selectedRunId ? await getWorkflowRunEvents({
    ...(await webApiContext({ tenantId: tenantSlug })),
    runId: selectedRunId,
  }) : null;

  async function buildAction(formData: FormData) {
    "use server";

    const result = await startStoryGraphBuild({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      mode: stringFromFormData(formData, "mode") || "full",
      options: {
        source: stringFromFormData(formData, "source") || "seed_canon",
      },
    });
    const status = storyGraphBuildStatus(result);
    redirect(storyGraphRoute({
      tenantSlug,
      projectId,
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
    const status = storyGraphBondStatus(result);
    redirect(storyGraphRoute({
      tenantSlug,
      projectId,
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
        storyGraphAdoptionMessage: "invalid story graph candidate adoption target",
        storyGraphAdoptionTargetId: "",
      }));
    }
    const result = await adoptStoryGraphCandidate({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      assetId: stringFromFormData(formData, "assetId"),
      targetKind,
    });
    const status = storyGraphAdoptionStatus(result);
    redirect(storyGraphRoute({
      tenantSlug,
      projectId,
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
      tenantSlug={tenantSlug}
      projectId={projectId}
      current={current}
      view={view}
      evidence={evidence}
      layout={layout}
      clusters={clusters}
      graphCandidates={graphCandidates}
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

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function stringListFromFormData(formData: FormData, key: string) {
  return stringFromFormData(formData, key)
    .split(/[\n,]/)
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

function storyGraphAdoptionStatus(result: StoryGraphCandidateAdoptionSummary) {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
      targetId: "",
    };
  }
  return {
    status: "success",
    code: "STORY_GRAPH_CANDIDATE_ADOPTED",
    message: `${result.asset_id} adopted as ${result.target_kind}`,
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
      message: "story graph evidence requires a node or edge selection",
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
