import { proxyActivities } from "@temporalio/workflow";

import type * as activities from "../activities/pi-writer-activities.js";

const { runPiWriterRunActivity } = proxyActivities<typeof activities>({
  startToCloseTimeout: "10 minutes",
  heartbeatTimeout: "5 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED",
  // Bounded retries: without this, Temporal's default policy retries the
  // activity indefinitely inside the 6-hour workflow window — a failing run
  // would re-burn LLM quota for hours. Three attempts cover transient
  // DB/Temporal blips; deterministic failures surface to the author instead.
  retry: {
    initialInterval: "5 seconds",
    backoffCoefficient: 2,
    maximumInterval: "1 minute",
    maximumAttempts: 3
  }
});

export async function PiWriterRunWorkflow(
  payload: unknown
): Promise<activities.PiWriterActivityResult> {
  return await runPiWriterRunActivity(payload);
}
