import { proxyActivities } from "@temporalio/workflow";

import type { PiWorldlineGoalStartActivityResult } from "../activities/pi-worldline-cast-activities.js";

const { runPiWorldlineGoalStartActivity } = proxyActivities<{
  runPiWorldlineGoalStartActivity(payload: unknown): Promise<PiWorldlineGoalStartActivityResult>;
}>({
  startToCloseTimeout: "2 hours",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED",
  retry: {
    initialInterval: "5 seconds",
    backoffCoefficient: 2,
    maximumInterval: "1 minute",
    maximumAttempts: 3
  }
});

export async function PiWorldlineGoalStartWorkflow(payload: unknown): Promise<PiWorldlineGoalStartActivityResult> {
  return await runPiWorldlineGoalStartActivity(payload);
}
