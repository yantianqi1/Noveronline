import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";
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
import { webApiContext } from "../../../../../../lib/server-auth";

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
  const apiContext = await webApiContext({ tenantId: tenantSlug, projectId });
  const projectOverview = await getProjectOverview(apiContext);
  const sourceFiles = await getProjectSourceFiles(apiContext);
  const projectReadiness = await getProjectReadinessSnapshot(apiContext);
  const seedRuns = await getProjectSeedRuns(apiContext);
  const selectedRunId = query.runId ?? latestSeedRunId(seedRuns);
  const afterEventId = query.after_event_id ?? query.afterEventId ?? "";
  const selectedSeedRun = selectedRunId
    ? await getSeedRunSummary({
        ...(await webApiContext({ tenantId: tenantSlug })),
        runId: selectedRunId,
      })
    : null;
  const seedEvents = selectedRunId
    ? await getSeedRunEvents({
        ...(await webApiContext({ tenantId: tenantSlug })),
        runId: selectedRunId,
        afterEventId,
      })
    : null;

  async function uploadAndStartSeedAction(formData: FormData) {
    "use server";

    const file = fileFromFormData(formData, "file");
    if (!file) {
      const status = sourceFileObjectActionStatus(sourceFileObjectRequired());
      return redirect(overviewRoute({
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

    const mimeType = supportedSourceMimeType(file);
    if (!mimeType) {
      const status = unsupportedSourceFileType();
      return redirect(overviewRoute({
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

    const fileBytes = await file.arrayBuffer();
    const sha256 = createHash("sha256").update(Buffer.from(fileBytes)).digest("hex");
    const admitted = await createSourceFileUpload({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      filename: fileNameFromUpload(file),
      mimeType,
      sizeBytes: file.size,
      sha256,
      purpose: "seed",
    });
    if (!admitted.ok) {
      const status = sourceFileActionStatus(admitted);
      return redirect(overviewRoute({
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

    const uploaded = await uploadSourceFileObject({
      ...(await webApiContext({ tenantId: tenantSlug })),
      uploadId: admitted.upload_id,
      file,
      mimeType,
    });
    if (!uploaded.ok) {
      const status = sourceFileObjectActionStatus(uploaded);
      return redirect(overviewRoute({
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

    const completed = await completeSourceFileUpload({
      ...(await webApiContext({ tenantId: tenantSlug })),
      uploadId: admitted.upload_id,
    });
    if (!completed.ok) {
      const status = sourceFileActionStatus(completed);
      return redirect(overviewRoute({
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

    const result = await startSeedRun({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      uploadId: admitted.upload_id,
      options: {
        mode: stringFromFormData(formData, "mode") || "full",
      },
    });
    const sourceStatus = sourceFileActionStatus(completed);
    const status = seedRunActionStatus(result);
    return redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: sourceStatus.status,
      sourceCode: sourceStatus.code,
      sourceMessage: sourceStatus.message,
      seedStatus: status.status,
      seedCode: status.code,
      seedMessage: status.message,
      runId: status.runId || query.runId || "",
      afterEventId: query.after_event_id ?? query.afterEventId ?? "",
    }));
  }

  async function completeUploadAction(formData: FormData) {
    "use server";

    const result = await completeSourceFileUpload({
      ...(await webApiContext({ tenantId: tenantSlug })),
      uploadId: stringFromFormData(formData, "uploadId"),
    });
    const status = sourceFileActionStatus(result);
    return redirect(overviewRoute({
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
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      uploadId: stringFromFormData(formData, "uploadId"),
      options: {
        mode: stringFromFormData(formData, "mode") || "full",
      },
    });
    const status = seedRunActionStatus(result);
    return redirect(overviewRoute({
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
      ...(await webApiContext({ tenantId: tenantSlug })),
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
      ...(await webApiContext({ tenantId: tenantSlug })),
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
      afterEventId: result.ok ? "" : (query.after_event_id ?? query.afterEventId ?? ""),
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
      uploadAndStartSeedAction={uploadAndStartSeedAction}
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

type UploadedSourceFile = Blob & {
  name?: string;
};

function fileFromFormData(formData: FormData, key: string): UploadedSourceFile | null {
  const value = formData.get(key);
  if (
    value &&
    typeof value === "object" &&
    "arrayBuffer" in value &&
    "size" in value &&
    typeof value.size === "number" &&
    value.size > 0
  ) {
    return value as UploadedSourceFile;
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

function unsupportedSourceFileType() {
  return {
    status: "error",
    code: "SOURCE_FILE_TYPE_UNSUPPORTED",
    message: "source file type is unsupported",
  };
}

function fileNameFromUpload(file: UploadedSourceFile) {
  const name = typeof file.name === "string" ? file.name.trim() : "";
  return name || "source-file";
}

function supportedSourceMimeType(file: UploadedSourceFile) {
  const explicit = sanitizeSupportedSourceMime(file.type);
  if (explicit) {
    return explicit;
  }
  const filename = fileNameFromUpload(file).toLowerCase();
  if (filename.endsWith(".txt")) {
    return "text/plain";
  }
  if (filename.endsWith(".md") || filename.endsWith(".markdown")) {
    return "text/markdown";
  }
  if (filename.endsWith(".pdf")) {
    return "application/pdf";
  }
  return "";
}

function sanitizeSupportedSourceMime(mimeType: string) {
  const normalized = mimeType.split(";")[0]?.trim().toLowerCase() ?? "";
  if (
    normalized === "text/plain" ||
    normalized === "text/markdown" ||
    normalized === "text/x-markdown" ||
    normalized === "application/x-markdown" ||
    normalized === "application/pdf"
  ) {
    return normalized;
  }
  return "";
}

function setQueryIfPresent(query: URLSearchParams, key: string, value: string) {
  if (value) {
    query.set(key, value);
  }
}
