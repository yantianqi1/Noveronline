export interface WorldlineSession {
  session_id: string;
  project_id: string;
  status: string;
  created_at: string;
  config?: Record<string, unknown>;
}

export interface WorldlineAgent {
  agent_id: string;
  name: string;
  entity_type: string;
  importance_tier?: string;
  status: string;
}

export interface WorldlineAgentDetail extends WorldlineAgent {
  baseline?: Record<string, unknown>;
  current_state?: Record<string, unknown>;
  memory?: unknown[];
  action_history?: AgentAction[];
  dialogue_history?: AgentDialogue[];
  relationship_timeline?: RelationEvent[];
}

export interface AgentAction {
  id: string;
  agent_id: string;
  action_type: string;
  description: string;
  timestamp: string;
  step: number;
}

export interface AgentDialogue {
  id: string;
  agent_id: string;
  target_agent_id?: string;
  content: string;
  mode: string;
  timestamp: string;
  step: number;
}

export interface RelationEvent {
  id: string;
  source_agent: string;
  target_agent: string;
  relation_type: string;
  change: string;
  timestamp: string;
  step: number;
}

export interface TimelineEvent {
  step: number;
  events: WorldEvent[];
  timestamp: string;
}

export interface WorldEvent {
  event_id: string;
  type: string;
  description: string;
  agents_involved: string[];
  status: string;  // canon | candidate | experiment
  metadata?: Record<string, unknown>;
}

export interface CandidateEvent extends WorldEvent {
  proposal_reasoning?: string;
  director_notes?: string;
}

export interface PrepareRun {
  prepare_id: string;
  project_id: string;
  status: string;
  progress: number;
  agents: PreparedAgent[];
  created_at: string;
}

export interface PreparedAgent {
  agent_id: string;
  name: string;
  entity_type: string;
  dossier?: Record<string, unknown>;
  ready: boolean;
}
