"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import type { AssetProposal, AssetProposalDetail } from "@/lib/api/asset-proposal-types";
import {
  decideAssetProposal,
  fetchAssetProposalDetail,
  fetchAssetProposals,
} from "@/lib/api/asset-proposal-client";
import { Check, ChevronDown, ChevronRight, RefreshCw, X } from "lucide-react";

/**
 * 待审资产 panel — the author's review queue for manuscript asset distillation.
 *
 * After a draft is adopted, the distillation pipeline extracts candidate
 * characters/settings/relationships/rules from the new prose. Nothing enters
 * the asset library (or the Writer agent's recall) until the author accepts it
 * here — candidates stay lifecycle=candidate and invisible to query tools.
 * Each proposal shows its evidence (which manuscript spans it came from) and
 * offers 采纳新建 / 采纳合并 / 拒绝.
 */
export function ProposalRail({
  projectId,
  tenantId,
  csrfToken,
  /** Bump to re-fetch (e.g. after a draft adoption enqueues new candidates). */
  refreshKey,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
  refreshKey: number;
}) {
  const [proposals, setProposals] = useState<AssetProposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    try {
      setError(null);
      const items = await fetchAssetProposals(projectId, tenantId, "pending");
      setProposals(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "待审资产加载失败");
      setProposals([]);
    }
  }, [projectId, tenantId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  async function decide(
    proposal: AssetProposal,
    decision: "accept_create" | "accept_update" | "reject",
  ) {
    if (!csrfToken || busyId) return;
    setBusyId(proposal.candidate_asset_id);
    setError(null);
    try {
      await decideAssetProposal(projectId, tenantId, csrfToken, proposal.candidate_asset_id, {
        decision,
        target_asset_id: decision === "accept_update" ? proposal.target_asset_id : undefined,
        expected_target_version:
          decision === "accept_update" ? proposal.expected_target_version : undefined,
      });
      setProposals((prev) => prev?.filter((p) => p.candidate_asset_id !== proposal.candidate_asset_id) ?? null);
      if (openId === proposal.candidate_asset_id) setOpenId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败，请重试");
    } finally {
      setBusyId(null);
    }
  }

  const count = proposals?.length ?? 0;

  return (
    <section className="flex min-h-0 flex-col border-t border-line">
      <header className="flex shrink-0 items-center justify-between px-4 py-2.5">
        <h3 className="flex items-center gap-2 text-caption font-semibold text-ink">
          待审资产
          {count > 0 && (
            <span className="rounded-full bg-accent px-1.5 py-px text-caption font-medium text-panel">
              {count}
            </span>
          )}
        </h3>
        <Button variant="ghost" size="sm" onClick={() => void load()} aria-label="刷新待审资产">
          <RefreshCw className="size-3.5" aria-hidden />
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {error && <p className="mb-2 rounded-panel bg-accent-wash px-3 py-2 text-caption text-accent">{error}</p>}

        {proposals === null ? (
          <p className="px-1 py-3 text-caption text-muted">加载中…</p>
        ) : proposals.length === 0 ? (
          <p className="px-1 py-3 text-caption leading-relaxed text-muted">
            暂时没有待审资产。采纳 AI 草稿后，新出现的人物、设定会自动抽出来放在这里等你过目——你点头之前，它们不会进资产库。
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {proposals.map((p) => (
              <ProposalCard
                key={p.candidate_asset_id}
                proposal={p}
                projectId={projectId}
                tenantId={tenantId}
                open={openId === p.candidate_asset_id}
                onToggle={() => setOpenId(openId === p.candidate_asset_id ? null : p.candidate_asset_id)}
                busy={busyId === p.candidate_asset_id}
                csrfReady={Boolean(csrfToken)}
                onDecide={decide}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

const ASSET_TYPE_LABEL: Record<string, string> = {
  character: "人物",
  setting: "设定",
  relationship: "关系",
  world_rule: "世界规则",
  item: "物品",
  faction: "势力",
  location: "地点",
  event: "事件",
};

function assetTypeLabel(assetType: string): string {
  return ASSET_TYPE_LABEL[assetType] ?? assetType;
}

function ProposalCard({
  proposal,
  projectId,
  tenantId,
  open,
  onToggle,
  busy,
  csrfReady,
  onDecide,
}: {
  proposal: AssetProposal;
  projectId: string;
  tenantId: string;
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  csrfReady: boolean;
  onDecide: (proposal: AssetProposal, decision: "accept_create" | "accept_update" | "reject") => void;
}) {
  const [detail, setDetail] = useState<AssetProposalDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || detail) return;
    let cancelled = false;
    fetchAssetProposalDetail(projectId, tenantId, proposal.candidate_asset_id)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : "出处加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [open, detail, projectId, tenantId, proposal.candidate_asset_id]);

  const isUpdate = proposal.operation === "update" && proposal.target_asset_id;

  return (
    <li className="rounded-panel border border-line bg-panel">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left"
      >
        {open ? (
          <ChevronDown className="mt-0.5 size-3.5 shrink-0 text-muted" aria-hidden />
        ) : (
          <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-muted" aria-hidden />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-ink">{proposal.title}</span>
            <span className="shrink-0 rounded-control border border-line bg-paper px-1.5 py-px text-caption text-muted">
              {assetTypeLabel(proposal.asset_type)}
            </span>
            {isUpdate && (
              <span className="shrink-0 rounded-control border border-accent/30 bg-accent-wash px-1.5 py-px text-caption text-accent">
                合并建议
              </span>
            )}
          </span>
          {proposal.summary && (
            <span className="mt-1 line-clamp-2 block text-caption leading-relaxed text-muted">
              {proposal.summary}
            </span>
          )}
        </span>
      </button>

      {open && (
        <div className="border-t border-line-soft px-3 py-2.5">
          {/* Evidence: where in the manuscript this candidate came from. */}
          <p className="text-caption font-medium tracking-wide text-muted">
            出处（{proposal.evidence_count} 处）
          </p>
          {detailError && <p className="mt-1 text-caption text-accent">{detailError}</p>}
          {!detail && !detailError && <p className="mt-1 text-caption text-muted">加载出处…</p>}
          {detail && (
            <ul className="mt-1.5 flex flex-col gap-1.5">
              {detail.evidence.map((ev) => {
                const text = detail.evidence_private?.find((p) => p.evidence_id === ev.evidence_id)?.evidence_text;
                return (
                  <li
                    key={ev.evidence_id}
                    className="rounded-control border border-line-soft bg-paper/70 px-2.5 py-1.5 text-caption leading-relaxed text-ink-soft"
                  >
                    {text ? (
                      <span className="line-clamp-3">「{text}」</span>
                    ) : (
                      <span className="text-muted">手稿片段 {ev.block_id.slice(0, 8)}…（无查看原文权限）</span>
                    )}
                    {!ev.current && (
                      <span className="ml-1 text-caption text-accent">（手稿已改动，采纳前请再核对）</span>
                    )}
                  </li>
                );
              })}
              {detail.evidence.length === 0 && (
                <li className="text-caption text-muted">没有记录出处。</li>
              )}
            </ul>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={() => onDecide(proposal, "accept_create")}
              loading={busy}
              disabled={!csrfReady}
            >
              <Check className="size-3.5" aria-hidden />
              {isUpdate ? "作为新资产采纳" : "采纳进资产库"}
            </Button>
            {isUpdate && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onDecide(proposal, "accept_update")}
                loading={busy}
                disabled={!csrfReady}
              >
                合并到已有资产
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDecide(proposal, "reject")}
              loading={busy}
              disabled={!csrfReady}
            >
              <X className="size-3.5" aria-hidden />
              拒绝
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
