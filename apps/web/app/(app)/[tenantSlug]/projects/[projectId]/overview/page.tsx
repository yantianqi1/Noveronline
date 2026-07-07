import { redirect } from "next/navigation";
import {
  OverviewSeedShell,
  seedRunActionStatus,
  seedRunControlStatus,
  sourceFileActionStatus,
  sourceFileObjectActionStatus,
} from "../../../../../../components/overview-seed-shell";
import {
  cancelSeedRun,
  completeSourceFileUpload,
  createSourceFileUpload,
  getProjectOverview,
  getProjectReadinessSnapshot,
  getProjectSeedRuns,
  getProjectSourceFiles,
  getSeedRunEvents,
  getSeedRunSummary,
  retrySeedRun,
  startSeedRun,
  uploadSourceFileObject,
} from "../../../../../../lib/api";

export const dynamic = "force-dynamic";

export default async function OverviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    afterEventId?: string;
    after_event_id?: string;
    runId?: string;
    seedCode?: string;
    seedMessage?: string;
    seedStatus?: string;
    sourceCode?: string;
    sourceMessage?: string;
    sourceStatus?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const apiContext = {
    tenantId: tenantSlug,
    actorUserId: "web-shell",
    projectId,
  };
  const projectOverview = await getProjectOverview(apiContext);
  const sourceFiles = await getProjectSourceFiles(apiContext);
  const projectReadiness = await getProjectReadinessSnapshot(apiContext);
  const seedRuns = await getProjectSeedRuns(apiContext);
  const selectedRunId = query.runId ?? latestSeedRunId(seedRuns);
  const afterEventId = query.after_event_id ?? query.afterEventId ?? "";
  const selectedSeedRun = selectedRunId
    ? await getSeedRunSummary({
        tenantId: tenantSlug,
        actorUserId: "web-shell",
        runId: selectedRunId,
      })
    : null;
  const seedEvents = selectedRunId
    ? await getSeedRunEvents({
        tenantId: tenantSlug,
        actorUserId: "web-shell",
        runId: selectedRunId,
        afterEventId,
      })
    : null;

  async function admitSourceFileAction(formData: FormData) {
    "use server";

    const result = await createSourceFileUpload({
      tenantId: tenantSlug,
      actorUserId: "web-shell",
      projectId,
      filename: stringFromFormData(formData, "filename"),
      mimeType: stringFromFormData(formData, "mimeType"),
      sizeBytes: positiveNumberFromFormData(formData, "sizeBytes"),
      sha256: stringFromFormData(formData, "sha256"),
      purpose: stringFromFormData(formData, "purpose") || "seed",
    });
    const status = sourceFileActionStatus(result);
    redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: status.status,
      sourceCode: status.code,
      sourceMessage: status.message,
      seedStatus: query.seedStatus ?? "",
      seedCode: query.seedCode ?? "",
      seedMessage: query.seedMessage ?? "",
      runId: query.runId ?? "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  async function completeUploadAction(formData: FormData) {
    "use server";

    const result = await completeSourceFileUpload({
      tenantId: tenantSlug,
      actorUserId: "web-shell",
      uploadId: stringFromFormData(formData, "uploadId"),
    });
    const status = sourceFileActionStatus(result);
    redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: status.status,
      sourceCode: status.code,
      sourceMessage: status.message,
      seedStatus: query.seedStatus ?? "",
      seedCode: query.seedCode ?? "",
      seedMessage: query.seedMessage ?? "",
      runId: query.runId ?? "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  async function uploadSourceObjectAction(formData: FormData) {
    "use server";

    const uploadId = stringFromFormData(formData, "uploadId");
    const file = fileFromFormData(formData, "file");
    const result = file
      ? await uploadSourceFileObject({
          tenantId: tenantSlug,
          actorUserId: "web-shell",
          uploadId,
          file,
        })
      : sourceFileObjectRequired();
    const status = sourceFileObjectActionStatus(result);
    redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: status.status,
      sourceCode: status.code,
      sourceMessage: status.message,
      seedStatus: query.seedStatus ?? "",
      seedCode: query.seedCode ?? "",
      seedMessage: query.seedMessage ?? "",
      runId: query.runId ?? "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  async function startSeedRunAction(formData: FormData) {
    "use server";

    const result = await startSeedRun({
      tenantId: tenantSlug,
      actorUserId: "web-shell",
      projectId,
      uploadId: stringFromFormData(formData, "uploadId"),
      options: {
        mode: stringFromFormData(formData, "mode") || "full",
      },
    });
    const status = seedRunActionStatus(result);
    redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: query.sourceStatus ?? "",
      sourceCode: query.sourceCode ?? "",
      sourceMessage: query.sourceMessage ?? "",
      seedStatus: status.status,
      seedCode: status.code,
      seedMessage: status.message,
      runId: status.runId || query.runId || "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  async function cancelSeedRunAction(formData: FormData) {
    "use server";

    const runId = stringFromFormData(formData, "runId");
    const result = await cancelSeedRun({
      tenantId: tenantSlug,
      actorUserId: "web-shell",
      runId,
    });
    const status = seedRunControlStatus(result, "cancel");
    redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: query.sourceStatus ?? "",
      sourceCode: query.sourceCode ?? "",
      sourceMessage: query.sourceMessage ?? "",
      seedStatus: status.status,
      seedCode: status.code,
      seedMessage: status.message,
      runId: status.runId || runId || query.runId || "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  async function retrySeedRunAction(formData: FormData) {
    "use server";

    const runId = stringFromFormData(formData, "runId");
    const result = await retrySeedRun({
      tenantId: tenantSlug,
      actorUserId: "web-shell",
      runId,
    });
    const status = seedRunControlStatus(result, "retry");
    redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: query.sourceStatus ?? "",
      sourceCode: query.sourceCode ?? "",
      sourceMessage: query.sourceMessage ?? "",
      seedStatus: status.status,
      seedCode: status.code,
      seedMessage: status.message,
      runId: status.runId || runId || query.runId || "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  return (
    <OverviewSeedShell
      tenantSlug={tenantSlug}
      projectId={projectId}
      projectOverview={projectOverview}
      projectReadiness={projectReadiness}
      sourceFiles={sourceFiles}
      seedRuns={seedRuns}
      selectedRunId={selectedRunId}
      afterEventId={afterEventId}
      selectedSeedRun={selectedSeedRun}
      seedEvents={seedEvents}
      sourceStatus={
        query.sourceStatus
          ? {
              status: query.sourceStatus,
              code: query.sourceCode ?? "",
              message: query.sourceMessage ?? "",
            }
          : null
      }
      seedStatus={
        query.seedStatus
          ? {
              status: query.seedStatus,
              code: query.seedCode ?? "",
              message: query.seedMessage ?? "",
            }
          : null
      }
      admitSourceFileAction={admitSourceFileAction}
      uploadSourceObjectAction={uploadSourceObjectAction}
      completeUploadAction={completeUploadAction}
      startSeedRunAction={startSeedRunAction}
      cancelSeedRunAction={cancelSeedRunAction}
      retrySeedRunAction={retrySeedRunAction}
    />
  );
}

function latestSeedRunId(seedRuns: Awaited<ReturnType<typeof getProjectSeedRuns>>) {
  if (!seedRuns.ok) {
    return "";
  }
  const latest = seedRuns.items.find((run) => run.ok);
  return latest && latest.ok ? latest.run_id : "";
}

function overviewRoute(input: {
  tenantSlug: string;
  projectId: string;
  sourceStatus: string;
  sourceCode: string;
  sourceMessage: string;
  seedStatus: string;
  seedCode: string;
  seedMessage: string;
  runId: string;
  afterEventId: string;
}) {
  const query = new URLSearchParams();
  setQueryIfPresent(query, "sourceStatus", input.sourceStatus);
  setQueryIfPresent(query, "sourceCode", input.sourceCode);
  setQueryIfPresent(query, "sourceMessage", input.sourceMessage);
  setQueryIfPresent(query, "seedStatus", input.seedStatus);
  setQueryIfPresent(query, "seedCode", input.seedCode);
  setQueryIfPresent(query, "seedMessage", input.seedMessage);
  setQueryIfPresent(query, "runId", input.runId);
  setQueryIfPresent(query, "after_event_id", input.afterEventId);
  return `/${input.tenantSlug}/projects/${input.projectId}/overview?${query.toString()}`;
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function fileFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  if (
    value &&
    typeof value === "object" &&
    "arrayBuffer" in value &&
    "size" in value &&
    typeof value.size === "number" &&
    value.size > 0
  ) {
    return value as Blob;
  }
  return null;
}

function sourceFileObjectRequired() {
  return {
    ok: false as const,
    code: "SOURCE_FILE_OBJECT_REQUIRED",
    message: "source file object is required",
    request_id: "",
  };
}

function positiveNumberFromFormData(formData: FormData, key: string) {
  const value = Number(stringFromFormData(formData, key));
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function setQueryIfPresent(query: URLSearchParams, key: string, value: string) {
  if (value) {
    query.set(key, value);
  }
}
