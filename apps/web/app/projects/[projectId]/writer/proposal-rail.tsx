"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import type { AssetProposal, AssetProposalDetail } from "@/lib/api/asset-proposal-types";
import { fetchAssetProposalDetail, decideAssetProposal, fetchAssetProposals } from "@/lib/api/asset-proposal-client";
import {
  Check,
  CheckCheck,
  ChevronRight,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";

/**
 * 待审资产 — the author's review queue for manuscript asset distillation.
 *
 * After a draft is adopted, the distillation pipeline extracts candidate
 * characters/settings/relationships/rules from the new prose. Nothing enters
 * the asset library (or the Writer agent's recall) until the author accepts it
 * here — candidates stay lifecycle=candidate and invisible to query tools.
 *
 * This panel fills the 待审资产 tab of the conversation dock. It owns the
 * queue toolbar and scrollable proposal list; the dock-head tabs in the shell
 * own the title, the count, and switching back to the conversation.
 */
export function ProposalRail({
  projectId,
  tenantId,
  csrfToken,
  /** Bump to re-fetch (e.g. after a draft adoption enqueues new candidates). */
  refreshKey,
  /** True while the post-adoption distillation watch is still open. */
  distilling = false,
  /** Called whenever the pending list changes, so the trigger badge stays in sync. */
  onCountChange,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
  refreshKey: number;
  distilling?: boolean;
  onCountChange?: (count: number) => void;
}) {
  const [proposals, setProposals] = useState<AssetProposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);

  async function load() {
    if (!tenantId) return;
    try {
      setError(null);
      const items = await fetchAssetProposals(projectId, tenantId, "pending");
      setProposals(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "待审资产加载失败");
      setProposals([]);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, tenantId, refreshKey]);

  const count = proposals?.length ?? 0;

  useEffect(() => {
    onCountChange?.(count);
  }, [count, onCountChange]);

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

  /**
   * 一键全部通过 — adopts every pending proposal in one go. Update proposals
   * merge into their existing target (accept_update); new candidates become new
   * assets (accept_create). Fires the natural decision for each card and only
   * drops the ones that succeed, so a version race on one merge never silently
   * discards the rest — failures stay in the queue for the author to retry.
   */
  async function approveAll() {
    if (!csrfToken || bulkBusy || busyId || !proposals || proposals.length === 0) return;
    setBulkBusy(true);
    setError(null);
    const queue = [...proposals];
    setBulkProgress({ done: 0, total: queue.length });
    const succeeded: string[] = [];
    let failed = 0;
    for (const p of queue) {
      const isUpdate = p.operation === "update" && p.target_asset_id;
      try {
        await decideAssetProposal(projectId, tenantId, csrfToken, p.candidate_asset_id, {
          decision: isUpdate ? "accept_update" : "accept_create",
          target_asset_id: isUpdate ? p.target_asset_id : undefined,
          expected_target_version: isUpdate ? p.expected_target_version : undefined,
        });
        succeeded.push(p.candidate_asset_id);
      } catch {
        failed += 1;
      }
      setBulkProgress({ done: succeeded.length + failed, total: queue.length });
    }
    setProposals((prev) => prev?.filter((p) => !succeeded.includes(p.candidate_asset_id)) ?? null);
    if (openId && succeeded.includes(openId)) setOpenId(null);
    if (failed > 0) {
      setError(`${failed} 条没能通过（多为合并目标已被改动），已留在列表里，请逐条核对。`);
    }
    setBulkProgress(null);
    setBulkBusy(false);
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* Slim action toolbar — the dock-head tab already carries the
          "待审资产" title + count, so this row is just the queue's controls:
          approve-all + refresh. No duplicate title, no close button. */}
      {(count > 1 || proposals === null) && (
        <div className="flex h-9 shrink-0 items-center justify-end gap-0.5 border-b border-line-soft px-3">
          {count > 1 && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => void approveAll()}
              loading={bulkBusy}
              disabled={!csrfToken || Boolean(busyId)}
              aria-label="全部通过待审资产"
              title="逐条采纳：合并建议并入已有资产，其余作为新资产入库"
            >
              <CheckCheck className="size-3.5" aria-hidden />
              {bulkBusy && bulkProgress ? `${bulkProgress.done}/${bulkProgress.total}` : "全部通过"}
            </Button>
          )}
          <Button
            variant="ghost"
            size="xs"
            onClick={() => void load()}
            disabled={bulkBusy}
            aria-label="刷新待审资产"
            className="px-1.5"
          >
            <RefreshCw className="size-3.5" aria-hidden />
          </Button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {error && (
          <p className="mb-2 rounded-panel border border-danger/30 bg-danger-wash px-3 py-2 text-caption leading-relaxed text-danger">
            {error}
          </p>
        )}

        {proposals === null ? (
          <QueueSkeleton />
        ) : proposals.length === 0 ? (
          <EmptyQueue distilling={distilling} />
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

/** Calm loading placeholder — three candidate-card outlines, not a spinner. */
function QueueSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-panel border border-line-soft bg-panel px-3 py-2.5">
          <div className="h-3.5 w-2/3 animate-pulse rounded-control bg-line-soft" />
          <div className="mt-2 h-3 w-full animate-pulse rounded-control bg-line-soft/70" />
        </div>
      ))}
    </div>
  );
}

/** An empty queue reads as a resolved state, not a blank hole — unless
 *  distillation is still running after 采用, in which case waiting is honest. */
function EmptyQueue({ distilling }: { distilling: boolean }) {
  if (distilling) {
    return (
      <div className="flex h-full flex-col items-center justify-center rounded-panel border border-dashed border-line-soft bg-panel/50 px-4 py-6 text-center">
        <span className="grid size-9 place-items-center rounded-full bg-accent-wash text-accent">
          <Sparkles className="size-4 animate-pulse" aria-hidden />
        </span>
        <p className="mt-2.5 text-sm font-medium text-ink">正在从正文蒸馏资产</p>
        <p className="mt-1 max-w-[240px] text-caption leading-relaxed text-muted">
          采用后会自动抽取人物、设定与关系，通常需要半分钟到几分钟。完成后会出现在这里，点头之前不会进资产库。
        </p>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col items-center justify-center rounded-panel border border-dashed border-line-soft bg-panel/50 px-4 py-6 text-center">
      <span className="grid size-9 place-items-center rounded-full bg-success-wash text-success">
        <Check className="size-4" aria-hidden />
      </span>
      <p className="mt-2.5 text-sm font-medium text-ink">队列已清空</p>
      <p className="mt-1 max-w-[240px] text-caption leading-relaxed text-muted">
        暂时没有待审资产。采纳 AI 草稿后，新出现的人物、设定会抽出来放在这里等你过目——你点头之前不进资产库。
      </p>
    </div>
  );
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
    <li
      className={`overflow-hidden rounded-panel border bg-panel transition-colors ${
        open ? "border-line shadow-hairline" : "border-line-soft hover:border-line"
      }`}
    >
      {/* Summary row — the whole row is the expand toggle; decision buttons
          live only in the open body so a collapsed card is a single calm line. */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left"
      >
        <ChevronRight
          className={`mt-0.5 size-3.5 shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-sm font-medium text-ink">{proposal.title}</span>
            <span className="shrink-0 text-caption text-candidate">
              {assetTypeLabel(proposal.asset_type)}
            </span>
            {isUpdate && (
              <span className="shrink-0 text-caption text-muted">
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
          <p className="flex items-center gap-1.5 text-caption font-medium tracking-label text-muted">
            <Sparkles className="size-3 text-candidate" aria-hidden />
            出处（{proposal.evidence_count} 处）
          </p>
          {detailError && <p className="mt-1 text-caption text-danger">{detailError}</p>}
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
              className="hover:bg-danger-wash hover:text-danger"
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
