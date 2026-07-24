/**
 * Reciprocal Rank Fusion (doc 41 §4.6) — merge several recall channels (keyed /
 * hybrid / manuscript / graph) into one ranked list without tuning weights.
 *
 * Each channel contributes 1/(k + rank) for every item it surfaced; an item that
 * appears in multiple channels accumulates the sum, which reliably floats
 * canon that several independent retrievers agree on. k=60 is the standard
 * constant from the RRF paper — no per-project tuning.
 */

export interface FusionItem {
  /** Stable identity within and across channels (asset_id, block_id, entity id). */
  id: string;
  /** Display title for the fused citation. */
  title?: string;
  /** Which channel produced it (keyed | hybrid | manuscript | ...). */
  channel?: string;
  /** Channel-specific payload carried through to the fused result. */
  payload?: Record<string, unknown>;
}

export interface FusedItem extends FusionItem {
  rrf_score: number;
  /** The channels that surfaced this item. */
  channels: string[];
  /** Best (1-based) rank the item achieved in any single channel. */
  best_rank: number;
}

export const RRF_K = 60;

/**
 * Fuse multiple ranked channel lists into a single list, best first.
 * Each list is ordered best-first; ties broken by best rank then id for
 * determinism.
 */
export function reciprocalRankFusion(channelLists: FusionItem[][]): FusedItem[] {
  const byId = new Map<string, FusedItem>();
  for (const list of channelLists) {
    list.forEach((item, index) => {
      const rank = index + 1;
      const contribution = 1 / (RRF_K + rank);
      const channel = item.channel ?? "unknown";
      const existing = byId.get(item.id);
      if (existing) {
        existing.rrf_score += contribution;
        existing.best_rank = Math.min(existing.best_rank, rank);
        if (!existing.channels.includes(channel)) existing.channels.push(channel);
      } else {
        byId.set(item.id, {
          ...item,
          rrf_score: contribution,
          channels: [channel],
          best_rank: rank
        });
      }
    });
  }
  return [...byId.values()].sort(
    (a, b) =>
      b.rrf_score - a.rrf_score ||
      a.best_rank - b.best_rank ||
      a.id.localeCompare(b.id)
  );
}
