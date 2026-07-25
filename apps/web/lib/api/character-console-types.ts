/**
 * Wire types mirroring the Go control plane's characterconsole package
 * (apps/api/internal/characterconsole/characterconsole.go). Field names are
 * snake_case as they appear on the wire. Character Console is the 第一人称舞台:
 * descend into a worldline session as one POV agent, then drive turns
 * (我说/我做/我内心/我想影响) and review the proposals the simulation offers.
 *
 * Safety contract:互动只产候选; proposals become canon only via an explicit
 * adopt call. The UI never fabricates character memory — when the backend is
 * unconfigured it surfaces the coded error instead.
 */

export type CharacterInteraction = {
  interaction_id: string;
  project_id: string;
  worldline_session_id: string;
  anchor_type: string;
  anchor_id: string;
  pov_agent_id: string;
  mode: string;
  status: string;
  title: string;
  summary: string;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type CharacterTurn = {
  turn_id: string;
  interaction_id: string;
  project_id: string;
  turn_order: number;
  actor_type: string;
  actor_id: string;
  turn_kind: string;
  summary: string;
  action: Record<string, unknown>;
  world_state_delta: Record<string, unknown>;
  trace_id: string;
  created_by: string;
  created_at: string;
};

export type CharacterEvent = {
  event_id: string;
  interaction_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

/**
 * A proposal the simulation offers for adoption into character memory /
 * relations / world state. Proposals surface as candidate assets (gold) and
 * are adopted through the top-level adoption route.
 */
export type CharacterProposal = {
  asset_id: string;
  interaction_id: string;
  category: string;
  title: string;
  summary: string;
  lifecycle: string;
  created_at: string;
  [key: string]: unknown;
};

/** Turn kinds the composer offers; map onto `turn.turn_kind`. */
export const TURN_KINDS = ["say", "do", "think", "influence"] as const;
export type TurnKind = (typeof TURN_KINDS)[number];

/** Interaction modes (第一人称 / 导演辅助 / 对话 / 回放). */
export const INTERACTION_MODES = ["first_person", "director_assist", "dialogue", "replay"] as const;
export type InteractionMode = (typeof INTERACTION_MODES)[number];
