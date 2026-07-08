import { redirect } from "next/navigation";
import { CharacterConsoleShell } from "../../../../../../components/character-console-shell";
import {
  appendCharacterInteractionTurn,
  convertCharacterInteractionToChapterDraft,
  createCharacterInteraction,
  getCharacterInteraction,
  getCharacterInteractionEvents,
  getStoryGraphView,
  getWorldlineEvents,
  getWorldlinePreparedAgents,
  getWorldlineSavedPaths,
  getWorldlineSessions,
  listCharacterInteractions,
  listCharacterInteractionTurns,
  updateCharacterInteractionStatus,
} from "../../../../../../lib/api";
import { webApiContext } from "../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";

export default async function CharacterConsolePage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    interaction_code?: string;
    interaction_id?: string;
    interaction_message?: string;
    interaction_status?: string;
    anchor_session_id?: string;
    prepare_id?: string;
    runtime_code?: string;
    runtime_message?: string;
    runtime_status?: string;
    selected_interaction_id?: string;
    turns_interaction_id?: string;
    turn_code?: string;
    turn_id?: string;
    turn_message?: string;
    turn_status?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const apiContext = await webApiContext({ tenantId: tenantSlug });
  const selectedInteractionId = query.selected_interaction_id?.trim() || query.interaction_id?.trim() || "";
  const turnsInteractionId = query.turns_interaction_id?.trim() || "";
  const anchorSessionId = query.anchor_session_id?.trim() || "";
  const prepareId = query.prepare_id?.trim() || "";
  const [interactions, worldlineSessions, savedPaths, graphView, worldlineEvents, preparedAgents] = await Promise.all([
    listCharacterInteractions({
      ...apiContext,
      projectId,
    }),
    getWorldlineSessions({
      ...apiContext,
      projectId,
    }),
    getWorldlineSavedPaths({
      ...apiContext,
      projectId,
    }),
    getStoryGraphView({
      ...apiContext,
      projectId,
      viewId: "current",
      types: ["character", "organization", "location", "plot_thread"],
      includeEdges: false,
    }),
    anchorSessionId
      ? getWorldlineEvents({
          ...apiContext,
          sessionId: anchorSessionId,
        })
      : Promise.resolve({
          ok: false as const,
          code: "WORLDLINE_SESSION_NOT_SELECTED",
          message: "Select a worldline session to load event anchors.",
          request_id: "",
        }),
    prepareId
      ? getWorldlinePreparedAgents({
          ...apiContext,
          prepareId,
        })
      : Promise.resolve({
          ok: false as const,
          code: "WORLDLINE_PREPARATION_NOT_SELECTED",
          message: "Select a worldline preparation to load prepared agents.",
          request_id: "",
        }),
  ]);
  const selectedInteraction = selectedInteractionId
    ? await getCharacterInteraction({
        ...apiContext,
        interactionId: selectedInteractionId,
      })
    : {
        ok: false as const,
        code: "CHARACTER_INTERACTION_NOT_SELECTED",
        message: "No interaction is selected.",
        request_id: "",
      };
  const selectedTurns = turnsInteractionId
    ? await listCharacterInteractionTurns({
        ...apiContext,
        interactionId: turnsInteractionId,
      })
    : {
        ok: false as const,
        code: "CHARACTER_INTERACTION_TURNS_NOT_SELECTED",
        message: "No interaction turn list is selected.",
        request_id: "",
      };

  async function createCharacterInteractionAction(formData: FormData) {
    "use server";

    const result = await createCharacterInteraction({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      worldlineSessionId: stringFromFormData(formData, "worldlineSessionId"),
      anchorType: stringFromFormData(formData, "anchorType"),
      anchorId: stringFromFormData(formData, "anchorId"),
      povAgentId: stringFromFormData(formData, "povAgentId"),
      mode: stringFromFormData(formData, "mode") || "first_person",
      title: stringFromFormData(formData, "title"),
      summary: stringFromFormData(formData, "summary"),
      metadata: {
        source: "character_console_shell",
      },
    });

    const nextQuery = new URLSearchParams();
    nextQuery.set("interaction_status", result.ok ? "success" : "error");
    nextQuery.set("interaction_code", result.ok ? "CHARACTER_INTERACTION_CREATED" : result.code);
    nextQuery.set(
      "interaction_message",
      result.ok ? `${result.title || result.interaction_id} ${result.status}`.trim() : result.message,
    );
    if (result.ok) {
      nextQuery.set("interaction_id", result.interaction_id);
      nextQuery.set("selected_interaction_id", result.interaction_id);
    }
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function inspectCharacterInteractionAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const interactionId = stringFromFormData(formData, "selectedInteractionId");
    if (!interactionId) {
      nextQuery.set("interaction_status", "error");
      nextQuery.set("interaction_code", "CHARACTER_INTERACTION_NOT_SELECTED");
      nextQuery.set("interaction_message", "Select a persisted interaction to inspect.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    nextQuery.set("selected_interaction_id", interactionId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function inspectCharacterInteractionTurnsAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const interactionId = stringFromFormData(formData, "turnsInteractionId");
    if (!interactionId) {
      nextQuery.set("turn_status", "error");
      nextQuery.set("turn_code", "CHARACTER_INTERACTION_NOT_SELECTED");
      nextQuery.set("turn_message", "Select a persisted interaction to load public turns.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    nextQuery.set("selected_interaction_id", interactionId);
    nextQuery.set("turns_interaction_id", interactionId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function updateCharacterInteractionStatusAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const interactionId = stringFromFormData(formData, "statusInteractionId");
    const status = characterInteractionStatusFromFormData(formData, "interactionNextStatus");
    if (!interactionId) {
      nextQuery.set("interaction_status", "error");
      nextQuery.set("interaction_code", "CHARACTER_INTERACTION_NOT_SELECTED");
      nextQuery.set("interaction_message", "Select a persisted interaction before changing status.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }
    if (!status) {
      nextQuery.set("selected_interaction_id", interactionId);
      nextQuery.set("interaction_status", "error");
      nextQuery.set("interaction_code", "VALIDATION_FAILED");
      nextQuery.set("interaction_message", "Choose active, saved, or archived.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await updateCharacterInteractionStatus({
      ...(await webApiContext({ tenantId: tenantSlug })),
      interactionId,
      status,
    });

    nextQuery.set("interaction_status", result.ok ? "success" : "error");
    nextQuery.set("interaction_code", result.ok ? "CHARACTER_INTERACTION_STATUS_UPDATED" : result.code);
    nextQuery.set(
      "interaction_message",
      result.ok ? `${result.title || result.interaction_id} ${result.status}`.trim() : result.message,
    );
    nextQuery.set("selected_interaction_id", interactionId);
    if (result.ok) {
      nextQuery.set("interaction_id", result.interaction_id);
    }
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function inspectCharacterInteractionEventsAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const interactionId = stringFromFormData(formData, "runtimeInteractionId");
    if (!interactionId) {
      nextQuery.set("runtime_status", "error");
      nextQuery.set("runtime_code", "CHARACTER_INTERACTION_NOT_SELECTED");
      nextQuery.set("runtime_message", "Select a persisted interaction before checking runtime events.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await getCharacterInteractionEvents({
      ...(await webApiContext({ tenantId: tenantSlug })),
      interactionId,
    });
    nextQuery.set("runtime_status", result.ok ? "success" : "error");
    nextQuery.set("runtime_code", result.ok ? "CHARACTER_INTERACTION_EVENTS_AVAILABLE" : result.code);
    nextQuery.set(
      "runtime_message",
      result.ok ? `${result.items.length} runtime events available.` : result.message,
    );
    nextQuery.set("selected_interaction_id", interactionId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function convertCharacterInteractionToChapterDraftAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const interactionId = stringFromFormData(formData, "convertInteractionId");
    if (!interactionId) {
      nextQuery.set("runtime_status", "error");
      nextQuery.set("runtime_code", "CHARACTER_INTERACTION_NOT_SELECTED");
      nextQuery.set("runtime_message", "Select a persisted interaction before requesting a chapter draft.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await convertCharacterInteractionToChapterDraft({
      ...(await webApiContext({ tenantId: tenantSlug })),
      interactionId,
      targetChapterId: stringFromFormData(formData, "targetChapterId"),
      povMode: stringFromFormData(formData, "povMode") || "keep_first_person",
    });
    nextQuery.set("runtime_status", result.ok ? "success" : "error");
    nextQuery.set("runtime_code", result.ok ? "CHARACTER_INTERACTION_WRITER_RUN_QUEUED" : result.code);
    nextQuery.set(
      "runtime_message",
      result.ok ? `Writer run ${result.run_id} queued for chapter draft handoff.` : result.message,
    );
    nextQuery.set("selected_interaction_id", interactionId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function inspectWorldlineEventAnchorsAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const nextAnchorSessionId = stringFromFormData(formData, "anchorSessionId");
    if (!nextAnchorSessionId) {
      nextQuery.set("interaction_status", "error");
      nextQuery.set("interaction_code", "WORLDLINE_SESSION_NOT_SELECTED");
      nextQuery.set("interaction_message", "Select a persisted worldline session before loading event anchors.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    nextQuery.set("anchor_session_id", nextAnchorSessionId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function inspectWorldlinePreparationAgentsAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const nextPrepareId = stringFromFormData(formData, "prepareId");
    if (!nextPrepareId) {
      nextQuery.set("interaction_status", "error");
      nextQuery.set("interaction_code", "WORLDLINE_PREPARATION_NOT_SELECTED");
      nextQuery.set("interaction_message", "Select a persisted worldline preparation before loading agents.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    nextQuery.set("prepare_id", nextPrepareId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  async function appendCharacterInteractionTurnAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const interactionId = stringFromFormData(formData, "interactionId");
    if (!interactionId) {
      nextQuery.set("turn_status", "error");
      nextQuery.set("turn_code", "CHARACTER_INTERACTION_NOT_SELECTED");
      nextQuery.set("turn_message", "Select a persisted interaction before recording a turn.");
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    const action = optionalJsonObjectFromFormData(formData, "actionJson");
    if (!action.ok) {
      if (interactionId) {
        nextQuery.set("selected_interaction_id", interactionId);
      }
      nextQuery.set("turn_status", "error");
      nextQuery.set("turn_code", action.code);
      nextQuery.set("turn_message", action.message);
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    const worldStateDelta = optionalJsonObjectFromFormData(formData, "worldStateDeltaJson");
    if (!worldStateDelta.ok) {
      if (interactionId) {
        nextQuery.set("selected_interaction_id", interactionId);
      }
      nextQuery.set("turn_status", "error");
      nextQuery.set("turn_code", worldStateDelta.code);
      nextQuery.set("turn_message", worldStateDelta.message);
      redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
    }

    const result = await appendCharacterInteractionTurn({
      ...(await webApiContext({ tenantId: tenantSlug })),
      interactionId,
      actorType: stringFromFormData(formData, "actorType") || "user",
      actorId: stringFromFormData(formData, "actorId"),
      turnKind: stringFromFormData(formData, "turnKind") || "action",
      summary: stringFromFormData(formData, "turnSummary"),
      action: action.value,
      worldStateDelta: worldStateDelta.value,
      traceId: stringFromFormData(formData, "traceId"),
    });

    nextQuery.set("turn_status", result.ok ? "success" : "error");
    nextQuery.set("turn_code", result.ok ? "CHARACTER_INTERACTION_TURN_RECORDED" : result.code);
    nextQuery.set(
      "turn_message",
      result.ok ? `Turn ${result.turn_order} ${result.turn_kind}`.trim() : result.message,
    );
    if (result.ok) {
      nextQuery.set("turn_id", result.turn_id);
    }
    nextQuery.set("selected_interaction_id", interactionId);
    redirect(characterConsoleStatusRoute(tenantSlug, projectId, nextQuery));
  }

  return (
    <CharacterConsoleShell
      appendCharacterInteractionTurnAction={appendCharacterInteractionTurnAction}
      convertCharacterInteractionToChapterDraftAction={convertCharacterInteractionToChapterDraftAction}
      createCharacterInteractionAction={createCharacterInteractionAction}
      inspectCharacterInteractionAction={inspectCharacterInteractionAction}
      inspectCharacterInteractionTurnsAction={inspectCharacterInteractionTurnsAction}
      inspectCharacterInteractionEventsAction={inspectCharacterInteractionEventsAction}
      inspectWorldlineEventAnchorsAction={inspectWorldlineEventAnchorsAction}
      inspectWorldlinePreparationAgentsAction={inspectWorldlinePreparationAgentsAction}
      updateCharacterInteractionStatusAction={updateCharacterInteractionStatusAction}
      anchorSessionId={anchorSessionId}
      graphView={graphView}
      interactions={interactions}
      interactionStatus={{
        code: query.interaction_code ?? "",
        interactionId: query.interaction_id ?? "",
        message: query.interaction_message ?? "",
        status: query.interaction_status ?? "",
      }}
      preparedAgents={preparedAgents}
      prepareId={prepareId}
      projectId={projectId}
      runtimeStatus={{
        code: query.runtime_code ?? "",
        message: query.runtime_message ?? "",
        status: query.runtime_status ?? "",
      }}
      savedPaths={savedPaths}
      selectedInteraction={selectedInteraction}
      selectedTurns={selectedTurns}
      tenantSlug={tenantSlug}
      turnStatus={{
        code: query.turn_code ?? "",
        message: query.turn_message ?? "",
        status: query.turn_status ?? "",
        turnId: query.turn_id ?? "",
      }}
      worldlineEvents={worldlineEvents}
      worldlineSessions={worldlineSessions}
    />
  );
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function characterInteractionStatusFromFormData(
  formData: FormData,
  key: string,
): "active" | "saved" | "archived" | "" {
  const value = stringFromFormData(formData, key);
  if (value === "active" || value === "saved" || value === "archived") {
    return value;
  }
  return "";
}

function characterConsoleStatusRoute(
  tenantSlug: string,
  projectId: string,
  query: URLSearchParams,
) {
  return `/${tenantSlug}/projects/${projectId}/character-console?${query.toString()}`;
}

function optionalJsonObjectFromFormData(formData: FormData, key: string) {
  const raw = stringFromFormData(formData, key);
  if (!raw) {
    return {
      ok: true as const,
      value: {},
    };
  }

  try {
    const value = JSON.parse(raw) as unknown;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return {
        ok: true as const,
        value: value as Record<string, unknown>,
      };
    }
  } catch {
    // Fall through to the stable public error below.
  }

  return {
    ok: false as const,
    code: "INVALID_TURN_PUBLIC_METADATA",
    message: `${key} must be a JSON object.`,
  };
}
