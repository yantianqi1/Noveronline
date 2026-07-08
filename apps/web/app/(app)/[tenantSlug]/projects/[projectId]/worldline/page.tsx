import { redirect } from "next/navigation";
import { WorldlineShell } from "../../../../../../components/worldline-shell";
import {
  adoptWorldlineEvent,
  createWorldlineSavedPath,
  createWorldlinePreparation,
  getWorldlineEvents,
  getWorldlinePreparation,
  getWorldlinePreparedAgents,
  getWorldlineSavedPaths,
  getWorldlineSessions,
  getWorldlineTimeline,
  injectWorldlineVariable,
  startWorldlineSession,
  startWorldlineStep,
  updateWorldlineEvent,
} from "../../../../../../lib/api";
import { webApiContext } from "../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";

export default async function WorldlinePage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    worldlineSessionCode?: string;
    worldlineSessionMessage?: string;
    worldlineSessionRunId?: string;
    worldlineSessionStatus?: string;
    worldlineStepCode?: string;
    worldlineStepMessage?: string;
    worldlineStepRunId?: string;
    worldlineStepStatus?: string;
    worldlinePreparationCode?: string;
    worldlinePreparationMessage?: string;
    worldlinePreparationPrepareId?: string;
    worldlinePreparationStatus?: string;
    worldlineVariableCode?: string;
    worldlineVariableMessage?: string;
    worldlineVariableStatus?: string;
    worldlineVariableId?: string;
    worldlineSavedPathCode?: string;
    worldlineSavedPathMessage?: string;
    worldlineSavedPathStatus?: string;
    worldlineSavedPathId?: string;
    worldlineEventAdoptionCode?: string;
    worldlineEventAdoptionMessage?: string;
    worldlineEventAdoptionStatus?: string;
    worldlineEventAdoptionId?: string;
    worldlineEventMutationCode?: string;
    worldlineEventMutationMessage?: string;
    worldlineEventMutationStatus?: string;
    worldlineEventMutationId?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const selectedPrepareId = query.worldlinePreparationPrepareId ?? "";
  const apiContext = await webApiContext({ tenantId: tenantSlug, projectId });
  const [savedPaths, sessions, preparation, preparedAgents] = await Promise.all([
    getWorldlineSavedPaths(apiContext),
    getWorldlineSessions(apiContext),
    selectedPrepareId
      ? getWorldlinePreparation({
          ...(await webApiContext({ tenantId: tenantSlug })),
          prepareId: selectedPrepareId,
        })
      : Promise.resolve({
          ok: false as const,
          code: "WORLDLINE_PREPARATION_NOT_SELECTED",
          message: "No worldline preparation is selected.",
          request_id: "",
        }),
    selectedPrepareId
      ? getWorldlinePreparedAgents({
          ...(await webApiContext({ tenantId: tenantSlug })),
          prepareId: selectedPrepareId,
        })
      : Promise.resolve({
          ok: false as const,
          code: "WORLDLINE_PREPARATION_NOT_SELECTED",
          message: "No worldline preparation is selected.",
          request_id: "",
      }),
  ]);
  const selectedSessionId = sessions.ok && sessions.items.length > 0 ? sessions.items[0].session_id : "";
  const [timeline, events] = selectedSessionId
    ? await Promise.all([
        getWorldlineTimeline({
          ...(await webApiContext({ tenantId: tenantSlug })),
          sessionId: selectedSessionId,
        }),
        getWorldlineEvents({
          ...(await webApiContext({ tenantId: tenantSlug })),
          sessionId: selectedSessionId,
          status: "candidate",
        }),
      ])
    : [
        {
          ok: false as const,
          code: "WORLDLINE_SESSION_NOT_SELECTED",
          message: "No worldline session is selected.",
          request_id: "",
        },
        {
          ok: false as const,
          code: "WORLDLINE_SESSION_NOT_SELECTED",
          message: "No worldline session is selected.",
          request_id: "",
        },
      ];

  async function startWorldlineSessionAction(formData: FormData) {
    "use server";

    const result = await startWorldlineSession({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      goal: stringFromFormData(formData, "goal"),
      anchorPathId: stringFromFormData(formData, "anchorPathId"),
    });

    const nextQuery = new URLSearchParams();
    nextQuery.set("worldlineSessionStatus", result.ok ? "success" : "error");
    nextQuery.set("worldlineSessionCode", result.ok ? "WORLDLINE_SESSION_STARTED" : result.code);
    nextQuery.set(
      "worldlineSessionMessage",
      result.ok ? `${result.workflow_type} ${result.status}` : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlineSessionRunId", result.run_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function startWorldlineStepAction(formData: FormData) {
    "use server";

    const sessionId = stringFromFormData(formData, "sessionId");
    const nextQuery = new URLSearchParams();
    if (!sessionId) {
      nextQuery.set("worldlineStepStatus", "error");
      nextQuery.set("worldlineStepCode", "WORLDLINE_SESSION_NOT_SELECTED");
      nextQuery.set("worldlineStepMessage", "No admitted worldline session is available.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await startWorldlineStep({
      ...(await webApiContext({ tenantId: tenantSlug })),
      sessionId,
      mode: stringFromFormData(formData, "stepMode") || "director",
      options: {
        source: "worldline_shell",
      },
    });

    nextQuery.set("worldlineStepStatus", result.ok ? "success" : "error");
    nextQuery.set("worldlineStepCode", result.ok ? "WORLDLINE_STEP_QUEUED" : result.code);
    nextQuery.set(
      "worldlineStepMessage",
      result.ok ? `${result.workflow_type} ${result.status}` : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlineStepRunId", result.run_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function createWorldlinePreparationAction(formData: FormData) {
    "use server";

    const result = await createWorldlinePreparation({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      goal: stringFromFormData(formData, "preparationGoal"),
      anchorPathId: stringFromFormData(formData, "preparationAnchorPathId"),
    });

    const nextQuery = new URLSearchParams();
    nextQuery.set("worldlinePreparationStatus", result.ok ? "success" : "error");
    nextQuery.set(
      "worldlinePreparationCode",
      result.ok ? "WORLDLINE_PREPARATION_QUEUED" : result.code,
    );
    nextQuery.set(
      "worldlinePreparationMessage",
      result.ok ? `${result.workflow_type} ${result.status}` : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlinePreparationPrepareId", result.prepare_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function injectWorldlineVariableAction(formData: FormData) {
    "use server";

    const sessionId = stringFromFormData(formData, "sessionId");
    const nextQuery = new URLSearchParams();
    if (!sessionId) {
      nextQuery.set("worldlineVariableStatus", "error");
      nextQuery.set("worldlineVariableCode", "WORLDLINE_SESSION_NOT_SELECTED");
      nextQuery.set("worldlineVariableMessage", "No admitted worldline session is available.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await injectWorldlineVariable({
      ...(await webApiContext({ tenantId: tenantSlug })),
      sessionId,
      name: stringFromFormData(formData, "variableName"),
      description: stringFromFormData(formData, "variableDescription"),
      impactAxis: stringFromFormData(formData, "impactAxis"),
      locked: formData.get("locked") === "on",
      source: "author",
    });

    nextQuery.set("worldlineVariableStatus", result.ok ? "success" : "error");
    nextQuery.set(
      "worldlineVariableCode",
      result.ok ? "WORLDLINE_VARIABLE_INJECTED" : result.code,
    );
    nextQuery.set(
      "worldlineVariableMessage",
      result.ok ? `${result.name} ${result.impact_axis}`.trim() : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlineVariableId", result.variable_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function createWorldlineSavedPathAction(formData: FormData) {
    "use server";

    const sessionId = stringFromFormData(formData, "sessionId");
    const selectedEventIds = stringListFromFormData(formData, "selectedEventIds", "manualEventIds");
    const nextQuery = new URLSearchParams();
    if (!sessionId) {
      nextQuery.set("worldlineSavedPathStatus", "error");
      nextQuery.set("worldlineSavedPathCode", "WORLDLINE_SESSION_NOT_SELECTED");
      nextQuery.set("worldlineSavedPathMessage", "No admitted worldline session is available.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }
    if (selectedEventIds.length === 0) {
      nextQuery.set("worldlineSavedPathStatus", "error");
      nextQuery.set("worldlineSavedPathCode", "WORLDLINE_EVENT_NOT_SELECTED");
      nextQuery.set("worldlineSavedPathMessage", "Select at least one candidate event.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await createWorldlineSavedPath({
      ...(await webApiContext({ tenantId: tenantSlug })),
      sessionId,
      title: stringFromFormData(formData, "savedPathTitle"),
      summary: stringFromFormData(formData, "savedPathSummary"),
      selectedEventIds,
      writerInstruction: stringFromFormData(formData, "writerInstruction"),
    });

    nextQuery.set("worldlineSavedPathStatus", result.ok ? "success" : "error");
    nextQuery.set(
      "worldlineSavedPathCode",
      result.ok ? "WORLDLINE_SAVED_PATH_CREATED" : result.code,
    );
    nextQuery.set(
      "worldlineSavedPathMessage",
      result.ok ? `${result.title} ${result.selected_event_ids.length} events` : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlineSavedPathId", result.path_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function adoptWorldlineEventAction(formData: FormData) {
    "use server";

    const eventId = stringFromFormData(formData, "eventId");
    const nextQuery = new URLSearchParams();
    if (!eventId) {
      nextQuery.set("worldlineEventAdoptionStatus", "error");
      nextQuery.set("worldlineEventAdoptionCode", "WORLDLINE_EVENT_NOT_SELECTED");
      nextQuery.set("worldlineEventAdoptionMessage", "Select one candidate event.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await adoptWorldlineEvent({
      ...(await webApiContext({ tenantId: tenantSlug })),
      eventId,
      note: stringFromFormData(formData, "adoptionNote"),
    });

    nextQuery.set("worldlineEventAdoptionStatus", result.ok ? "success" : "error");
    nextQuery.set(
      "worldlineEventAdoptionCode",
      result.ok ? "WORLDLINE_EVENT_ADOPTED" : result.code,
    );
    nextQuery.set(
      "worldlineEventAdoptionMessage",
      result.ok ? `${result.title} ${result.status}`.trim() : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlineEventAdoptionId", result.event_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function updateWorldlineEventAction(formData: FormData) {
    "use server";

    const eventId = stringFromFormData(formData, "eventId");
    const nextQuery = new URLSearchParams();
    if (!eventId) {
      nextQuery.set("worldlineEventMutationStatus", "error");
      nextQuery.set("worldlineEventMutationCode", "WORLDLINE_EVENT_NOT_SELECTED");
      nextQuery.set("worldlineEventMutationMessage", "Select one candidate event.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await updateWorldlineEvent({
      ...(await webApiContext({ tenantId: tenantSlug })),
      eventId,
      title: stringFromFormData(formData, "eventTitle"),
      summary: stringFromFormData(formData, "eventSummary"),
      kind: stringFromFormData(formData, "eventKind"),
    });

    nextQuery.set("worldlineEventMutationStatus", result.ok ? "success" : "error");
    nextQuery.set(
      "worldlineEventMutationCode",
      result.ok ? "WORLDLINE_EVENT_UPDATED" : result.code,
    );
    nextQuery.set(
      "worldlineEventMutationMessage",
      result.ok ? `${result.title} ${result.status}`.trim() : result.message,
    );
    if (result.ok) {
      nextQuery.set("worldlineEventMutationId", result.event_id);
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  return (
    <WorldlineShell
      adoptWorldlineEventAction={adoptWorldlineEventAction}
      createWorldlinePreparationAction={createWorldlinePreparationAction}
      createWorldlineSavedPathAction={createWorldlineSavedPathAction}
      injectWorldlineVariableAction={injectWorldlineVariableAction}
      updateWorldlineEventAction={updateWorldlineEventAction}
      preparation={preparation}
      preparedAgents={preparedAgents}
      events={events}
      projectId={projectId}
      savedPaths={savedPaths}
      sessions={sessions}
      startWorldlineSessionAction={startWorldlineSessionAction}
      startWorldlineStepAction={startWorldlineStepAction}
      tenantSlug={tenantSlug}
      timeline={timeline}
      worldlineSessionStatus={{
        code: query.worldlineSessionCode ?? "",
        message: query.worldlineSessionMessage ?? "",
        runId: query.worldlineSessionRunId ?? "",
        status: query.worldlineSessionStatus ?? "",
      }}
      worldlineStepStatus={{
        code: query.worldlineStepCode ?? "",
        message: query.worldlineStepMessage ?? "",
        runId: query.worldlineStepRunId ?? "",
        status: query.worldlineStepStatus ?? "",
      }}
      worldlinePreparationStatus={{
        code: query.worldlinePreparationCode ?? "",
        message: query.worldlinePreparationMessage ?? "",
        prepareId: query.worldlinePreparationPrepareId ?? "",
        status: query.worldlinePreparationStatus ?? "",
      }}
      worldlineVariableStatus={{
        code: query.worldlineVariableCode ?? "",
        message: query.worldlineVariableMessage ?? "",
        status: query.worldlineVariableStatus ?? "",
        variableId: query.worldlineVariableId ?? "",
      }}
      worldlineSavedPathStatus={{
        code: query.worldlineSavedPathCode ?? "",
        message: query.worldlineSavedPathMessage ?? "",
        pathId: query.worldlineSavedPathId ?? "",
        status: query.worldlineSavedPathStatus ?? "",
      }}
      worldlineEventAdoptionStatus={{
        code: query.worldlineEventAdoptionCode ?? "",
        eventId: query.worldlineEventAdoptionId ?? "",
        message: query.worldlineEventAdoptionMessage ?? "",
        status: query.worldlineEventAdoptionStatus ?? "",
      }}
      worldlineEventMutationStatus={{
        code: query.worldlineEventMutationCode ?? "",
        eventId: query.worldlineEventMutationId ?? "",
        message: query.worldlineEventMutationMessage ?? "",
        status: query.worldlineEventMutationStatus ?? "",
      }}
    />
  );
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function stringListFromFormData(formData: FormData, repeatedKey: string, manualKey: string) {
  const values = formData
    .getAll(repeatedKey)
    .filter((value): value is string => typeof value === "string")
    .flatMap((value) => value.split(/[\n,]/g));
  const manualValue = stringFromFormData(formData, manualKey);
  if (manualValue) {
    values.push(...manualValue.split(/[\n,]/g));
  }
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function worldlineRoute(tenantSlug: string, projectId: string, query: URLSearchParams) {
  const suffix = query.toString();
  return `/${tenantSlug}/projects/${projectId}/worldline${suffix ? `?${suffix}` : ""}`;
}
