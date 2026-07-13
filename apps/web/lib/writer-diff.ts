/**
 * Pure manuscript revision diff helpers.
 *
 * Produces ordered hunks from base and proposed text so accept/reject can be unit
 * tested without ProseMirror. Positions are UTF-16 code unit offsets matching
 * JavaScript string indexing used by the browser editor.
 */

export type DiffOp = "equal" | "insert" | "delete";

export type DiffHunk = {
  id: string;
  op: DiffOp;
  baseText: string;
  proposedText: string;
  /** Inclusive start offset in the current working text before this hunk is applied. */
  start: number;
  /** Exclusive end offset in the current working text before this hunk is applied. */
  end: number;
};

export type ApplyHunkDecision = "accept" | "reject";

/**
 * Compute line-aware hunks between base and proposed prose.
 * Consecutive equal lines are collapsed; inserts/deletes become individual hunks.
 */
export function computeRevisionHunks(baseText: string, proposedText: string): DiffHunk[] {
  const base = String(baseText ?? "");
  const proposed = String(proposedText ?? "");
  if (base === proposed) {
    return [];
  }

  const baseLines = splitLines(base);
  const proposedLines = splitLines(proposed);
  const ops = myersDiff(baseLines, proposedLines);
  const hunks: DiffHunk[] = [];
  let baseOffset = 0;
  let hunkIndex = 0;

  for (const op of ops) {
    if (op.type === "equal") {
      baseOffset += op.value.length;
      continue;
    }
    if (op.type === "delete") {
      const text = op.value;
      hunks.push({
        id: `hunk-${hunkIndex++}`,
        op: "delete",
        baseText: text,
        proposedText: "",
        start: baseOffset,
        end: baseOffset + text.length,
      });
      baseOffset += text.length;
      continue;
    }
    // insert — position is a zero-width span at baseOffset
    hunks.push({
      id: `hunk-${hunkIndex++}`,
      op: "insert",
      baseText: "",
      proposedText: op.value,
      start: baseOffset,
      end: baseOffset,
    });
  }

  return mergeAdjacentHunks(hunks);
}

/**
 * Apply accept/reject decisions to base text.
 * Decisions not listed for a hunk default to reject (leave base).
 */
export function applyHunkDecisions(
  baseText: string,
  hunks: readonly DiffHunk[],
  decisions: Readonly<Record<string, ApplyHunkDecision>>,
): string {
  const base = String(baseText ?? "");
  if (hunks.length === 0) {
    return base;
  }

  // Apply from end to start so earlier offsets stay valid.
  const ordered = [...hunks].sort((a, b) => b.start - a.start || b.end - a.end);
  let result = base;
  for (const hunk of ordered) {
    const decision = decisions[hunk.id] ?? "reject";
    if (decision === "reject") {
      continue;
    }
    if (hunk.op === "delete") {
      result = result.slice(0, hunk.start) + result.slice(hunk.end);
      continue;
    }
    if (hunk.op === "insert") {
      result = result.slice(0, hunk.start) + hunk.proposedText + result.slice(hunk.start);
      continue;
    }
  }
  return result;
}

/** Accept every non-equal hunk. */
export function acceptAllHunks(baseText: string, proposedText: string): string {
  const hunks = computeRevisionHunks(baseText, proposedText);
  const decisions: Record<string, ApplyHunkDecision> = {};
  for (const hunk of hunks) {
    decisions[hunk.id] = "accept";
  }
  return applyHunkDecisions(baseText, hunks, decisions);
}

/** Reject every hunk — identity. */
export function rejectAllHunks(baseText: string, _proposedText: string): string {
  return String(baseText ?? "");
}

function splitLines(text: string): string[] {
  if (text.length === 0) {
    return [];
  }
  // Keep trailing newline semantics: "a\nb" → ["a\n", "b"]; "a\n" → ["a\n"]
  const lines: string[] = [];
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "\n") {
      lines.push(text.slice(start, index + 1));
      start = index + 1;
    }
  }
  if (start < text.length) {
    lines.push(text.slice(start));
  }
  return lines;
}

type MyersOp = { type: DiffOp; value: string };

function myersDiff(a: string[], b: string[]): MyersOp[] {
  // Simple LCS-based diff for line arrays — fine for manuscript selection size.
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (a[i] === b[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }
  const ops: MyersOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      ops.push({ type: "equal", value: a[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: "delete", value: a[i] });
      i += 1;
    } else {
      ops.push({ type: "insert", value: b[j] });
      j += 1;
    }
  }
  while (i < n) {
    ops.push({ type: "delete", value: a[i] });
    i += 1;
  }
  while (j < m) {
    ops.push({ type: "insert", value: b[j] });
    j += 1;
  }
  return collapseOps(ops);
}

function collapseOps(ops: MyersOp[]): MyersOp[] {
  const collapsed: MyersOp[] = [];
  for (const op of ops) {
    const last = collapsed[collapsed.length - 1];
    if (last && last.type === op.type) {
      last.value += op.value;
    } else {
      collapsed.push({ ...op });
    }
  }
  return collapsed;
}

function mergeAdjacentHunks(hunks: DiffHunk[]): DiffHunk[] {
  // Keep delete+insert pairs adjacent as separate hunks for per-hunk UI control.
  return hunks;
}
