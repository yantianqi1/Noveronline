import { WriterWorkbenchShell } from "../../../../../../components/writer-workbench-shell";
import {
  exportAgentTrace,
  getAgentTraceEvents,
  getProjectAssets,
  getStoryGraphView,
  getWorldlineSavedPaths,
  getWriterRunEvents,
  getWriterRunSummary,
  startWriterRun,
} from "../../../../../../lib/api";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function WriterPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    afterEventId?: string;
    after_event_id?: string;
    runId?: string;
    traceExportCode?: string;
    traceExportMessage?: string;
    traceExportStatus?: string;
    traceId?: string;
    writerRunCode?: string;
    writerRunMessage?: string;
    writerRunStatus?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const apiContext = {
    tenantId: tenantSlug,
    actorUserId: "web-shell",
  };
  const runSummary = query.runId
    ? await getWriterRunSummary({
        ...apiContext,
        runId: query.runId,
      })
    : null;
  const workflowEvents = runSummary !== null && runSummary.ok === true
    ? await getWriterRunEvents({
        ...apiContext,
        runId: runSummary.run_id,
        afterEventId: query.after_event_id ?? query.afterEventId,
      })
    : null;
  const traceId = query.traceId ?? (runSummary !== null && runSummary.ok === true ? runSummary.trace_id : "");
  const traceEvents = traceId
    ? await getAgentTraceEvents({
        ...apiContext,
        projectId,
        traceId,
      })
    : null;
  const [assets, graphView, worldlineSavedPaths] = await Promise.all([
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
  ]);

  async function startWriterRunAction(formData: FormData) {
    "use server";

    const selectedAssetIds = stringListFromFormData(formData, "selectedAssetIds");
    const selectedGraphNodes = graphNodeSelectionsFromFormData(formData, "selectedGraphNodeIds");
    const worldlinePathIds = stringListFromFormData(formData, "worldlinePathIds");
    const instruction = stringFromFormData(formData, "instruction");
    const mode = writerModeFromFormData(formData);
    const result = await startWriterRun({
      ...apiContext,
      projectId,
      mode,
      instruction,
      options: {
        module_key: "writer_composer",
        selected_asset_ids: selectedAssetIds,
        graph_node_ids: selectedGraphNodes.ids,
        graph_node_names: selectedGraphNodes.names,
        worldline_path_ids: worldlinePathIds,
      },
    });
    const nextQuery = new URLSearchParams({
      writerRunStatus: result.ok ? "success" : "error",
      writerRunCode: result.ok ? "WRITER_RUN_QUEUED" : result.code,
      writerRunMessage: result.ok ? `${result.run_id} queued` : result.message,
    });
    if (result.ok) {
      nextQuery.set("runId", result.run_id);
      nextQuery.set("traceId", result.trace_id);
    } else if (query.runId) {
      nextQuery.set("runId", query.runId);
    }
    redirect(`/${tenantSlug}/projects/${projectId}/writer?${nextQuery.toString()}`);
  }

  async function exportTraceAction(formData: FormData) {
    "use server";

    const nextTraceId = stringFromFormData(formData, "traceId");
    const result = await exportAgentTrace({
      ...apiContext,
      projectId,
      traceId: nextTraceId,
      includeFull: false,
    });
    const nextQuery = new URLSearchParams({
      traceExportStatus: result.ok ? "success" : "error",
      traceExportCode: result.ok ? "TRACE_EXPORT_READY" : result.code,
      traceExportMessage: result.ok
        ? `Redacted trace export audited with ${result.items.length} events`
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

  return (
    <WriterWorkbenchShell
      tenantSlug={tenantSlug}
      projectId={projectId}
      runSummary={runSummary}
      workflowEvents={workflowEvents}
      traceEvents={traceEvents}
      assets={assets}
      graphView={graphView}
      worldlineSavedPaths={worldlineSavedPaths}
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
    />
  );
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
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

function writerModeFromFormData(formData: FormData): "draft" | "continue" | "outline" | "review" {
  const mode = stringFromFormData(formData, "mode");
  return mode === "continue" || mode === "outline" || mode === "review" ? mode : "draft";
}
