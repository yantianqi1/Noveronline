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
import { tx } from "../../../../../../lib/locale";
import { currentRequestLocale } from "../../../../../../lib/request-locale";
import { webApiContext, webReadApiContext } from "../../../../../../lib/server-auth";
import { createBookPlan, createChapter, createScene } from "../../../../../../lib/writer-workspace-api";

export const dynamic = "force-dynamic";

export default async function OverviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    afterEventId?: string;
    after_event_id?: string;
    bootstrapCode?: string;
    bootstrapMessage?: string;
    bootstrapStatus?: string;
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
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const apiContext = webReadApiContext({ tenantId: tenantSlug, projectId });
  const [projectOverview, sourceFiles, projectReadiness, seedRuns] = await Promise.all([
    getProjectOverview(apiContext),
    getProjectSourceFiles(apiContext),
    getProjectReadinessSnapshot(apiContext),
    getProjectSeedRuns(apiContext),
  ]);
  const selectedRunId = query.runId ?? latestSeedRunId(seedRuns);
  const afterEventId = query.after_event_id ?? query.afterEventId ?? "";
  const [selectedSeedRun, seedEvents] = selectedRunId
    ? await Promise.all([
        getSeedRunSummary({ ...apiContext, runId: selectedRunId }),
        getSeedRunEvents({ ...apiContext, runId: selectedRunId, afterEventId }),
      ])
    : [null, null];

  async function uploadAndStartSeedAction(formData: FormData) {
    "use server";

    const file = fileFromFormData(formData, "file");
    if (!file) {
      const status = sourceFileObjectActionStatus(sourceFileObjectRequired(locale), locale);
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
      const status = unsupportedSourceFileType(locale);
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
      const status = sourceFileActionStatus(admitted, locale);
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
      const status = sourceFileObjectActionStatus(uploaded, locale);
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
      const status = sourceFileActionStatus(completed, locale);
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
    const sourceStatus = sourceFileActionStatus(completed, locale);
    const status = seedRunActionStatus(result, locale);
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

  async function bootstrapIdeaAction(formData: FormData) {
    "use server";

    const premise = stringFromFormData(formData, "premise");
    const titleInput = stringFromFormData(formData, "title");
    const chapterTitle = stringFromFormData(formData, "chapterTitle") || tx(locale, "第一章", "Chapter 1");
    if (!premise) {
      return redirect(overviewRoute({
        tenantSlug,
        projectId,
        sourceStatus: query.sourceStatus ?? "",
        sourceCode: query.sourceCode ?? "",
        sourceMessage: query.sourceMessage ?? "",
        seedStatus: query.seedStatus ?? "",
        seedCode: query.seedCode ?? "",
        seedMessage: query.seedMessage ?? "",
        bootstrapStatus: "error",
        bootstrapCode: "VALIDATION_FAILED",
        bootstrapMessage: tx(locale, "请填写故事前提。", "Story premise is required."),
        runId: query.runId ?? "",
        afterEventId: query.after_event_id ?? query.afterEventId ?? "",
      }));
    }

    const context = {
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
    };
    const planTitle = titleInput || premise.slice(0, 48);
    const plan = await createBookPlan(context, {
      title: planTitle,
      premise,
      status: "draft",
      planning: JSON.stringify({ bootstrap: true, entry: "idea_first" }),
      target_chapter_count: 12,
    });
    if (!plan.ok) {
      return redirect(overviewRoute({
        tenantSlug,
        projectId,
        sourceStatus: query.sourceStatus ?? "",
        sourceCode: query.sourceCode ?? "",
        sourceMessage: query.sourceMessage ?? "",
        seedStatus: query.seedStatus ?? "",
        seedCode: query.seedCode ?? "",
        seedMessage: query.seedMessage ?? "",
        bootstrapStatus: "error",
        bootstrapCode: plan.code,
        bootstrapMessage: plan.message || tx(locale, "创建书籍计划失败。", "Could not create the book plan."),
        runId: query.runId ?? "",
        afterEventId: query.after_event_id ?? query.afterEventId ?? "",
      }));
    }

    const chapter = await createChapter(context, {
      title: chapterTitle,
      status: "draft",
      brief: premise,
    });
    if (!chapter.ok) {
      return redirect(overviewRoute({
        tenantSlug,
        projectId,
        sourceStatus: query.sourceStatus ?? "",
        sourceCode: query.sourceCode ?? "",
        sourceMessage: query.sourceMessage ?? "",
        seedStatus: query.seedStatus ?? "",
        seedCode: query.seedCode ?? "",
        seedMessage: query.seedMessage ?? "",
        bootstrapStatus: "error",
        bootstrapCode: chapter.code,
        bootstrapMessage: chapter.message || tx(locale, "创建章节失败。", "Could not create the chapter."),
        runId: query.runId ?? "",
        afterEventId: query.after_event_id ?? query.afterEventId ?? "",
      }));
    }

    const scene = await createScene(context, chapter.value.chapter_id, {
      title: tx(locale, "开场", "Opening"),
      status: "draft",
      brief: premise,
    });
    if (!scene.ok) {
      return redirect(overviewRoute({
        tenantSlug,
        projectId,
        sourceStatus: query.sourceStatus ?? "",
        sourceCode: query.sourceCode ?? "",
        sourceMessage: query.sourceMessage ?? "",
        seedStatus: query.seedStatus ?? "",
        seedCode: query.seedCode ?? "",
        seedMessage: query.seedMessage ?? "",
        bootstrapStatus: "error",
        bootstrapCode: scene.code,
        bootstrapMessage: scene.message || tx(locale, "创建场景失败。", "Could not create the scene."),
        runId: query.runId ?? "",
        afterEventId: query.after_event_id ?? query.afterEventId ?? "",
      }));
    }

    const writerQuery = new URLSearchParams({
      chapterId: chapter.value.chapter_id,
      sceneId: scene.value.scene_id,
      workspaceStatus: "success",
      workspaceCode: "IDEA_BOOTSTRAP_READY",
    });
    return redirect(`/${tenantSlug}/projects/${projectId}/writer?${writerQuery.toString()}`);
  }

  async function completeUploadAction(formData: FormData) {
    "use server";

    const result = await completeSourceFileUpload({
      ...(await webApiContext({ tenantId: tenantSlug })),
      uploadId: stringFromFormData(formData, "uploadId"),
    });
    const status = sourceFileActionStatus(result, locale);
    return redirect(overviewRoute({
      tenantSlug,
      projectId,
      sourceStatus: status.status,
      sourceCode: status.code,
      sourceMessage: status.message,
      seedStatus: query.seedStatus ?? "",
      seedCode: query.seedCode ?? "",
      seedMessage: query.seedMessage ?? "",
      bootstrapStatus: query.bootstrapStatus ?? "",
      bootstrapCode: query.bootstrapCode ?? "",
      bootstrapMessage: query.bootstrapMessage ?? "",
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
    const status = seedRunActionStatus(result, locale);
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
    const status = seedRunControlStatus(result, "cancel", locale);
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
    const status = seedRunControlStatus(result, "retry", locale);
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
      locale={locale}
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
      bootstrapStatus={
        query.bootstrapStatus
          ? {
              status: query.bootstrapStatus,
              code: query.bootstrapCode ?? "",
              message: query.bootstrapMessage ?? "",
            }
          : null
      }
      bootstrapIdeaAction={bootstrapIdeaAction}
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
  bootstrapStatus?: string;
  bootstrapCode?: string;
  bootstrapMessage?: string;
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
  setQueryIfPresent(query, "bootstrapStatus", input.bootstrapStatus ?? "");
  setQueryIfPresent(query, "bootstrapCode", input.bootstrapCode ?? "");
  setQueryIfPresent(query, "bootstrapMessage", input.bootstrapMessage ?? "");
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

function sourceFileObjectRequired(locale: "zh-CN" | "en") {
  return {
    ok: false as const,
    code: "SOURCE_FILE_OBJECT_REQUIRED",
    message: tx(locale, "请选择源文件", "Choose a source file"),
    request_id: "",
  };
}

function unsupportedSourceFileType(locale: "zh-CN" | "en") {
  return {
    status: "error",
    code: "SOURCE_FILE_TYPE_UNSUPPORTED",
    message: tx(locale, "不支持此文件类型", "Unsupported file type"),
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
