import { redirect } from "next/navigation";
import { WorldlineShell } from "../../../../../../components/worldline-shell";
import {
  adoptWorldlineEvent,
  createWorldlineGoalStart,
  createWorldlineSavedPath,
  createWorldlinePreparation,
  getProjectAssets,
  getStoryGraphView,
  getWorldlineEvents,
  getWorldlineGoalStart,
  getWorldlinePreparation,
  getWorldlinePreparedAgents,
  getWorldlineSavedPaths,
  getWorldlineSessions,
  getWorldlineTimeline,
  injectWorldlineVariable,
  startWorldlineAutoEvolution,
  startWorldlineStep,
  updateWorldlineEvent,
} from "../../../../../../lib/api";
import {
  agentRefsFromFormData,
  encodeJourneyRef,
  journeyRefsFromFormData,
  positiveBoundedInteger,
  selectCurrentWorldSession,
} from "../../../../../../lib/worldline-character-journey";
import { currentRequestLocale } from "../../../../../../lib/request-locale";
import { webApiContext, webReadApiContext } from "../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";

export default async function WorldlinePage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    worldlineGoalStartCode?: string;
    worldlineGoalStartMessage?: string;
    worldlineGoalStartRunId?: string;
    worldlineGoalStartStatus?: string;
    goal_start_run_id?: string;
    worldlineStepCode?: string;
    worldlineStepMessage?: string;
    worldlineStepRunId?: string;
    worldlineStepStatus?: string;
    worldlineAutoCode?: string;
    worldlineAutoMessage?: string;
    worldlineAutoRunId?: string;
    worldlineAutoStatus?: string;
    selectedSessionId?: string;
    selectedAgentRefs?: string;
    selectedSourceRefs?: string;
    worldlinePreparationCode?: string;
    worldlinePreparationMessage?: string;
    prepare_id?: string;
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
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const selectedPrepareId = query.prepare_id?.trim() || query.worldlinePreparationPrepareId?.trim() || "";
  const selectedGoalStartRunId =
    query.goal_start_run_id?.trim() || query.worldlineGoalStartRunId?.trim() || "";
  const apiContext = webReadApiContext({ tenantId: tenantSlug, projectId });
  const [savedPaths, sessions, assets, graphView, preparation, preparedAgents, goalStart] = await Promise.all([
    getWorldlineSavedPaths(apiContext),
    getWorldlineSessions(apiContext),
    getProjectAssets(apiContext),
    getStoryGraphView({
      ...apiContext,
      viewId: "current",
      types: ["character", "organization", "location"],
      includeEdges: false,
    }),
    selectedPrepareId
      ? getWorldlinePreparation({
          ...apiContext,
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
          ...apiContext,
          prepareId: selectedPrepareId,
        })
      : Promise.resolve({
          ok: false as const,
          code: "WORLDLINE_PREPARATION_NOT_SELECTED",
          message: "No worldline preparation is selected.",
          request_id: "",
      }),
    selectedGoalStartRunId
      ? getWorldlineGoalStart({
          ...apiContext,
          runId: selectedGoalStartRunId,
        })
      : Promise.resolve({
          ok: false as const,
          code: "WORLDLINE_GOAL_START_NOT_SELECTED",
          message: "No worldline goal-start is selected.",
          request_id: "",
        }),
  ]);
  const goalStartSessionId = goalStart.ok && goalStart.status === "ready" ? goalStart.session_id?.trim() ?? "" : "";
  const goalStartPrepareId = goalStart.ok ? goalStart.prepare_id?.trim() ?? "" : "";
  const effectivePrepareId = selectedPrepareId || goalStartPrepareId;
  const selectedSession = selectCurrentWorldSession(
    sessions,
    query.selectedSessionId?.trim() || goalStartSessionId,
  );
  const selectedSessionId = selectedSession?.session_id ?? goalStartSessionId;
  const [timeline, events, pathEvents] = selectedSessionId
    ? await Promise.all([
        getWorldlineTimeline({
          ...apiContext,
          sessionId: selectedSessionId,
        }),
        getWorldlineEvents({
          ...apiContext,
          sessionId: selectedSessionId,
          status: "candidate",
        }),
        getWorldlineEvents({
          ...apiContext,
          sessionId: selectedSessionId,
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
        {
          ok: false as const,
          code: "WORLDLINE_SESSION_NOT_SELECTED",
          message: "No worldline session is selected.",
          request_id: "",
        },
      ];

  async function createWorldlineGoalStartAction(formData: FormData) {
    "use server";

    const result = await createWorldlineGoalStart({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      goal: stringFromFormData(formData, "goal"),
      anchorPathId: stringFromFormData(formData, "anchorPathId"),
      options: { source: "worldline_shell" },
    });

    const nextQuery = new URLSearchParams();
    nextQuery.set("worldlineGoalStartStatus", result.ok ? "success" : "error");
    nextQuery.set("worldlineGoalStartCode", result.ok ? "WORLDLINE_GOAL_START_QUEUED" : result.code);
    nextQuery.set(
      "worldlineGoalStartMessage",
      result.ok ? `${result.workflow_type} ${result.status}` : result.message,
    );
    if (result.ok) {
      nextQuery.set("goal_start_run_id", result.run_id);
      nextQuery.set("worldlineGoalStartRunId", result.run_id);
      if (result.session_id) {
        nextQuery.set("selectedSessionId", result.session_id);
      }
      if (result.prepare_id) {
        nextQuery.set("prepare_id", result.prepare_id);
      }
    }
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function refreshWorldlineGoalStartAction(formData: FormData) {
    "use server";
    const nextQuery = new URLSearchParams();
    const runId = stringFromFormData(formData, "goalStartRunId") || selectedGoalStartRunId;
    if (runId) {
      nextQuery.set("goal_start_run_id", runId);
      nextQuery.set("worldlineGoalStartRunId", runId);
      const latest = await getWorldlineGoalStart({
        ...(await webApiContext({ tenantId: tenantSlug, projectId })),
        runId,
      });
      if (latest.ok && latest.session_id) {
        nextQuery.set("selectedSessionId", latest.session_id);
      }
      if (latest.ok && latest.prepare_id) {
        nextQuery.set("prepare_id", latest.prepare_id);
      }
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

    const prepareId = stringFromFormData(formData, "prepareId") || effectivePrepareId;
    const result = await startWorldlineStep({
      ...(await webApiContext({ tenantId: tenantSlug })),
      sessionId,
      mode: stringFromFormData(formData, "stepMode") || "director",
      options: {
        source: "worldline_shell",
        ...(prepareId ? { prepare_id: prepareId } : {}),
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
    nextQuery.set("selectedSessionId", sessionId);
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function startWorldlineAutoEvolutionAction(formData: FormData) {
    "use server";

    const sessionId = stringFromFormData(formData, "sessionId");
    const nextQuery = new URLSearchParams();
    if (!sessionId) {
      nextQuery.set("worldlineAutoStatus", "error");
      nextQuery.set("worldlineAutoCode", "WORLDLINE_SESSION_NOT_SELECTED");
      nextQuery.set("worldlineAutoMessage", "Select the active current_world session.");
      redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
    }
    const result = await startWorldlineAutoEvolution({
      ...(await webApiContext({ tenantId: tenantSlug })),
      sessionId,
      maxSteps: positiveBoundedInteger(formData.get("maxSteps"), 3, 50),
      options: { source: "worldline_character_journey" },
    });
    nextQuery.set("worldlineAutoStatus", result.ok ? "success" : "error");
    nextQuery.set("worldlineAutoCode", result.ok ? "WORLDLINE_AUTO_EVOLUTION_QUEUED" : result.code);
    nextQuery.set("worldlineAutoMessage", result.ok ? `${result.max_steps} steps ${result.status}` : result.message);
    nextQuery.set("selectedSessionId", sessionId);
    if (result.ok) nextQuery.set("worldlineAutoRunId", result.run_id);
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function createWorldlinePreparationAction(formData: FormData) {
    "use server";

    const agentRefs = agentRefsFromFormData(formData, "agentRefs");
    const sourceRefs = journeyRefsFromFormData(formData, "sourceRefs");
    const result = await createWorldlinePreparation({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      goal: stringFromFormData(formData, "preparationGoal"),
      anchorPathId: stringFromFormData(formData, "preparationAnchorPathId"),
      agentRefs,
      sourceRefs,
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
      nextQuery.set("prepare_id", result.prepare_id);
    }
    nextQuery.set("selectedAgentRefs", agentRefs.map(encodeJourneyRef).join(","));
    nextQuery.set("selectedSourceRefs", sourceRefs.map(encodeJourneyRef).join(","));
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function refreshWorldlinePreparationAction(formData: FormData) {
    "use server";
    const nextQuery = new URLSearchParams();
    const prepareId = stringFromFormData(formData, "prepareId");
    if (prepareId) nextQuery.set("prepare_id", prepareId);
    nextQuery.set("selectedAgentRefs", stringFromFormData(formData, "selectedAgentRefs"));
    nextQuery.set("selectedSourceRefs", stringFromFormData(formData, "selectedSourceRefs"));
    redirect(worldlineRoute(tenantSlug, projectId, nextQuery));
  }

  async function selectWorldlineSessionAction(formData: FormData) {
    "use server";
    const nextQuery = new URLSearchParams();
    const sessionId = stringFromFormData(formData, "selectedSessionId");
    if (sessionId) nextQuery.set("selectedSessionId", sessionId);
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
      assets={assets}
      createWorldlinePreparationAction={createWorldlinePreparationAction}
      createWorldlineSavedPathAction={createWorldlineSavedPathAction}
      injectWorldlineVariableAction={injectWorldlineVariableAction}
      updateWorldlineEventAction={updateWorldlineEventAction}
      preparation={preparation}
      preparedAgents={preparedAgents}
      goalStart={goalStart}
      events={events}
      pathEvents={pathEvents}
      graphView={graphView}
      locale={locale}
      projectId={projectId}
      savedPaths={savedPaths}
      selectedAgentRefs={
        goalStart.ok && goalStart.agent_refs?.length
          ? goalStart.agent_refs.map((ref) => `${ref.source_kind}:${ref.source_id}`)
          : (query.selectedAgentRefs ?? "").split(",").filter(Boolean)
      }
      selectedSessionId={selectedSessionId}
      selectedSourceRefs={
        goalStart.ok && goalStart.source_refs?.length
          ? goalStart.source_refs.map((ref) => `${ref.source_kind}:${ref.source_id}`)
          : (query.selectedSourceRefs ?? "").split(",").filter(Boolean)
      }
      selectWorldlineSessionAction={selectWorldlineSessionAction}
      sessions={sessions}
      createWorldlineGoalStartAction={createWorldlineGoalStartAction}
      refreshWorldlineGoalStartAction={refreshWorldlineGoalStartAction}
      startWorldlineStepAction={startWorldlineStepAction}
      startWorldlineAutoEvolutionAction={startWorldlineAutoEvolutionAction}
      refreshWorldlinePreparationAction={refreshWorldlinePreparationAction}
      tenantSlug={tenantSlug}
      timeline={timeline}
      worldlineGoalStartStatus={{
        code: query.worldlineGoalStartCode ?? "",
        message: query.worldlineGoalStartMessage ?? "",
        runId: query.worldlineGoalStartRunId ?? query.goal_start_run_id ?? "",
        status: query.worldlineGoalStartStatus ?? "",
      }}
      worldlineStepStatus={{
        code: query.worldlineStepCode ?? "",
        message: query.worldlineStepMessage ?? "",
        runId: query.worldlineStepRunId ?? "",
        status: query.worldlineStepStatus ?? "",
      }}
      worldlineAutoStatus={{
        code: query.worldlineAutoCode ?? "",
        message: query.worldlineAutoMessage ?? "",
        runId: query.worldlineAutoRunId ?? "",
        status: query.worldlineAutoStatus ?? "",
      }}
      worldlinePreparationStatus={{
        code: query.worldlinePreparationCode ?? "",
        message: query.worldlinePreparationMessage ?? "",
        prepareId: query.prepare_id ?? query.worldlinePreparationPrepareId ?? "",
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
