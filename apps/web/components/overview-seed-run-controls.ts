type SeedRunControlSummary = {
  ok: boolean;
  status?: string;
};

const TERMINAL_SEED_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);
const RETRYABLE_TERMINAL_SEED_RUN_STATUSES = new Set(["failed", "cancelled"]);

export function canCancelSeedRun(selectedSeedRun: SeedRunControlSummary | null) {
  return Boolean(
    selectedSeedRun?.ok && !isTerminalSeedRunStatus(selectedSeedRun.status ?? "")
  );
}

export function canRetrySeedRun(selectedSeedRun: SeedRunControlSummary | null) {
  return Boolean(
    selectedSeedRun?.ok && isRetryableTerminalSeedRunStatus(selectedSeedRun.status ?? "")
  );
}

function isTerminalSeedRunStatus(status: string) {
  return TERMINAL_SEED_RUN_STATUSES.has(status.trim().toLowerCase());
}

function isRetryableTerminalSeedRunStatus(status: string) {
  return RETRYABLE_TERMINAL_SEED_RUN_STATUSES.has(status.trim().toLowerCase());
}
