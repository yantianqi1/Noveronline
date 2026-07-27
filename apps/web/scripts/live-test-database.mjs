import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const DISPOSABLE_DATABASE_NAME = /^mirofish_test_[a-z0-9_]+$/;

export async function disposableLiveDatabaseConfig(databaseUrl) {
  const runtimeUrl = String(databaseUrl ?? "").trim();
  if (!runtimeUrl) throw new Error("disposable live database URL is required");

  const parsed = new URL(runtimeUrl);
  const databaseName = decodeURIComponent(parsed.pathname.replace(/^\//, "")).toLowerCase();
  if (!DISPOSABLE_DATABASE_NAME.test(databaseName)) {
    throw new Error(`refusing non-disposable live database ${JSON.stringify(databaseName)}`);
  }

  const { stdout } = await execFileAsync("psql", [
    runtimeUrl,
    "-At",
    "-v",
    "ON_ERROR_STOP=1",
    "-c",
    "SELECT current_database(), COALESCE(current_setting('mirofish.live_test', true), '')",
  ]);
  const [actualName, marker] = stdout.trim().split("|");
  if (actualName?.trim().toLowerCase() !== databaseName || marker?.trim() !== "on") {
    throw new Error(`refusing live database without disposable mirofish.live_test marker: ${databaseName}`);
  }
  return { runtimeUrl, databaseName };
}
