/**
 * Wire types for the manuscript asset-distillation review surface, mirroring
 * apps/api/internal/assetdistillation/types.go. Field names are snake_case
 * exactly as they appear on the wire.
 */

export type AssetProposal = {
  candidate_asset_id: string;
  project_id: string;
  request_id: string;
  operation: string; // create | update
  review_status: string; // pending | conflict | accepted | rejected | stale
  normalized_identity: string;
  title: string;
  asset_type: string;
  summary: string;
  target_asset_id: string;
  expected_target_version?: number;
  confidence?: number;
  evidence_count: number;
  created_at: string;
};

export type ProposalEvidence = {
  evidence_id: string;
  block_id: string;
  block_version: number;
  start_offset: number;
  end_offset: number;
  current: boolean;
};

export type ProposalEvidencePrivate = {
  evidence_id: string;
  evidence_text: string;
};

export type AssetProposalDetail = AssetProposal & {
  accepted_asset_id?: string;
  decision_note?: string;
  evidence: ProposalEvidence[];
  evidence_private?: ProposalEvidencePrivate[];
  payload?: Record<string, unknown>;
};

export type ProposalDecision = "accept_create" | "accept_update" | "reject";

export type ProposalDecisionResult = {
  candidate_asset_id: string;
  review_status: string;
  accepted_asset_id?: string;
  replay?: boolean;
};
