import { proxyActivities } from "@temporalio/workflow";

import type * as activities from "../activities/pi-analysis-activities.js";

const { runPiAnalysisRunActivity } = proxyActivities<typeof activities>({
  startToCloseTimeout: "2 hours",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED"
});

export async function PiAnalysisRunWorkflow(
  payload: unknown
): Promise<activities.PiAnalysisActivityResult> {
  return await runPiAnalysisRunActivity(payload);
}
