import { proxyActivities } from "@temporalio/workflow";

import type * as activities from "../activities/pi-writer-activities.js";

const { runPiWriterRunActivity } = proxyActivities<typeof activities>({
  startToCloseTimeout: "10 minutes"
});

export async function PiWriterRunWorkflow(
  payload: unknown
): Promise<activities.PiWriterActivityResult> {
  return await runPiWriterRunActivity(payload);
}
