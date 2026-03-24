const MANUAL_MODE = "manual";
const FIRST_ROUND_MODE = "first_round";
const DEFAULT_MAX_STEPS = 6;
const MIN_STEPS = 1;
export const MAIN_WORLD_BRANCH_ID = "main";
const MAIN_WORLD_TITLE = "当前世界";

function normalizeMaxSteps(maxSteps) {
  const numeric = Number(maxSteps);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_MAX_STEPS;
  }
  return Math.max(MIN_STEPS, Math.round(numeric));
}

export function buildAutoEvolvePayload({
  createMode = MANUAL_MODE,
  goalText = "",
  maxSteps = DEFAULT_MAX_STEPS,
} = {}) {
  if (createMode === MANUAL_MODE) {
    return null;
  }
  if (createMode === FIRST_ROUND_MODE) {
    return {
      mode: FIRST_ROUND_MODE,
      goal_text: "",
      max_steps: 1,
    };
  }
  return {
    mode: createMode,
    goal_text: goalText.trim(),
    max_steps: normalizeMaxSteps(maxSteps),
  };
}

export function createInitialAutoTaskMap(branches = []) {
  void branches;
  return {
    [MAIN_WORLD_BRANCH_ID]: {
      branch_id: MAIN_WORLD_BRANCH_ID,
      branch_title: MAIN_WORLD_TITLE,
      task_id: "",
      status: "idle",
    },
  };
}

export function mergeAutoTaskSnapshot(current = {}, snapshot = {}) {
  const branchId = snapshot.branch_id || MAIN_WORLD_BRANCH_ID;
  const existing = current[branchId] || {
    branch_id: branchId,
    branch_title: snapshot.branch_title || MAIN_WORLD_TITLE,
    task_id: "",
    status: "idle",
  };
  return {
    ...current,
    [branchId]: {
      ...existing,
      ...snapshot,
      branch_title: snapshot.branch_title || existing.branch_title || MAIN_WORLD_TITLE,
    },
  };
}
