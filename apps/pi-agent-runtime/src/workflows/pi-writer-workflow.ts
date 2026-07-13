import { proxyActivities } from "@temporalio/workflow";

import type * as activities from "../activities/pi-writer-activities.js";

const { runPiWriterRunActivity } = proxyActivities<typeof activities>({
  startToCloseTimeout: "10 minutes",
  heartbeatTimeout: "5 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED"
});

export async function PiWriterRunWorkflow(
  payload: unknown
): Promise<activities.PiWriterActivityResult> {
  return await runPiWriterRunActivity(payload);
}
