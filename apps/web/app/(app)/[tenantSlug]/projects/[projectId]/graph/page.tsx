import { redirect } from "next/navigation";
import { StoryGraphShell, storyGraphBondStatus, storyGraphBuildStatus } from "../../../../../../components/story-graph-shell";
import {
  getWorkflowRunEvents,
  getWorkflowRunSummary,
  getStoryGraphClusters,
  getStoryGraphCurrent,
  getStoryGraphEvidence,
  getStoryGraphLayout,
  getStoryGraphView,
  startStoryGraphBondGeneration,
  startStoryGraphBuild,
  type StoryGraphEvidenceSummary,
} from "../../../../../../lib/api";

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
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const apiContext = {
    tenantId: tenantSlug,
    actorUserId: "web-shell",
    projectId,
  };
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
  const selectedRunId = query.bondRunId || query.runId || "";
  const workflowRun = selectedRunId ? await getWorkflowRunSummary({
    tenantId: tenantSlug,
    actorUserId: "web-shell",
    runId: selectedRunId,
  }) : null;
  const workflowEvents = selectedRunId ? await getWorkflowRunEvents({
    tenantId: tenantSlug,
    actorUserId: "web-shell",
    runId: selectedRunId,
  }) : null;

  async function buildAction(formData: FormData) {
    "use server";

    const result = await startStoryGraphBuild({
      tenantId: tenantSlug,
      actorUserId: "web-shell",
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
      tenantId: tenantSlug,
      actorUserId: "web-shell",
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

  return (
    <StoryGraphShell
      tenantSlug={tenantSlug}
      projectId={projectId}
      current={current}
      view={view}
      evidence={evidence}
      layout={layout}
      clusters={clusters}
      buildStatus={query.buildStatus ?? ""}
      buildCode={query.buildCode ?? ""}
      buildMessage={query.buildMessage ?? ""}
      bondStatus={query.bondStatus ?? ""}
      bondCode={query.bondCode ?? ""}
      bondMessage={query.bondMessage ?? ""}
      selectedRunId={selectedRunId}
      selectedBuildRunId={query.runId ?? ""}
      selectedBondRunId={query.bondRunId ?? ""}
      workflowRun={workflowRun}
      workflowEvents={workflowEvents}
      buildAction={buildAction}
      bondAction={bondAction}
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

function setQueryIfPresent(query: URLSearchParams, key: string, value: string) {
  if (value) {
    query.set(key, value);
  }
}

async function firstEvidenceSummary(
  apiContext: { tenantId: string; actorUserId: string; projectId: string },
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
