import type {
  AssetProposal,
  AssetProposalDetail,
  ProposalDecision,
  ProposalDecisionResult,
} from "@/lib/api/asset-proposal-types";

/**
 * Browser-side client for manuscript asset-distillation proposals (待审资产).
 * Same-origin BFF routes; the browser supplies X-Tenant-Id and, for decision
 * mutations, a CSRF token + X-Request-Id (idempotency).
 */

export class ProposalError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ProposalError";
  }
}

async function readError(response: Response): Promise<ProposalError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // non-JSON body — keep the generic message
  }
  return new ProposalError(message, code, response.status);
}

function requestId(): string {
  return `proposals-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** List proposals by review status (default: pending). */
export async function fetchAssetProposals(
  projectId: string,
  tenantId: string,
  status = "pending",
): Promise<AssetProposal[]> {
  const response = await fetch(
    `/api/projects/${projectId}/asset-proposals?status=${encodeURIComponent(status)}`,
    { headers: { Accept: "application/json", "X-Tenant-Id": tenantId }, cache: "no-store" },
  );
  if (!response.ok) throw await readError(response);
  const data = (await response.json()) as { items?: AssetProposal[] };
  return data.items ?? [];
}

/** Fetch one proposal's detail, including evidence spans (出处). */
export async function fetchAssetProposalDetail(
  projectId: string,
  tenantId: string,
  candidateAssetId: string,
): Promise<AssetProposalDetail> {
  const response = await fetch(`/api/projects/${projectId}/asset-proposals/${candidateAssetId}`, {
    headers: { Accept: "application/json", "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as AssetProposalDetail;
}

/**
 * Submit a review decision. accept_create adopts the candidate as a new asset;
 * accept_update merges it into an existing target asset (optimistic-locked via
 * expected_target_version); reject archives the candidate.
 */
export async function decideAssetProposal(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  candidateAssetId: string,
  input: {
    decision: ProposalDecision;
    target_lifecycle?: string;
    target_asset_id?: string;
    expected_target_version?: number;
    note?: string;
  },
): Promise<ProposalDecisionResult> {
  const response = await fetch(`/api/projects/${projectId}/asset-proposals/${candidateAssetId}/decisions`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
      "X-Request-Id": requestId(),
    },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as ProposalDecisionResult;
}
