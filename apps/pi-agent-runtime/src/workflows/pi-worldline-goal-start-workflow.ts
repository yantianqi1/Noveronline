import { proxyActivities } from "@temporalio/workflow";

import type { PiWorldlineGoalStartActivityResult } from "../activities/pi-worldline-cast-activities.js";

const { runPiWorldlineGoalStartActivity } = proxyActivities<{
  runPiWorldlineGoalStartActivity(payload: unknown): Promise<PiWorldlineGoalStartActivityResult>;
}>({
  startToCloseTimeout: "2 hours",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED"
});

export async function PiWorldlineGoalStartWorkflow(payload: unknown): Promise<PiWorldlineGoalStartActivityResult> {
  return await runPiWorldlineGoalStartActivity(payload);
}
