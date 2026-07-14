/**
 * One-shot repair: re-parse 30-candidates/*.json for a completed analysis run
 * and auto-import into assets. Safe to re-run (replace_run + ON CONFLICT upsert).
 *
 * Usage:
 *   DATABASE_URL=... npx tsx scripts/reimport-analysis-candidates.ts <run_id>
 */
import { createPgPoolQueryExecutor } from "../src/runtime/postgres-pi-writer-deps.js";
import { createPostgresPiAnalysisDeps } from "../src/runtime/postgres-pi-analysis-deps.js";
import { extractAnalysisCandidatesFromWorkspaceFiles } from "../src/runtime/analysis-candidate-extract.js";

const runId = process.argv[2]?.trim();
if (!runId) {
  console.error("usage: reimport-analysis-candidates.ts <run_id>");
  process.exit(2);
}
const databaseUrl = process.env.DATABASE_URL?.trim();
if (!databaseUrl) {
  console.error("DATABASE_URL is required");
  process.exit(2);
}

const db = createPgPoolQueryExecutor(databaseUrl);
try {
  const run = await db.query<{
    tenant_id: string;
    project_id: string;
    status: string;
  }>(
    `SELECT tenant_id::text, project_id::text, status
       FROM analysis_runs WHERE run_id = $1::uuid`,
    [runId],
  );
  const row = run.rows[0];
  if (!row) {
    throw new Error(`analysis run not found: ${runId}`);
  }
  if (row.status !== "completed") {
    throw new Error(`analysis run status is ${row.status}, expected completed`);
  }

  const deps = createPostgresPiAnalysisDeps({ db });
  const files = await deps.listWorkspaceFiles!({
    tenant_id: row.tenant_id,
    project_id: row.project_id,
    run_id: runId,
  });
  const candidates = extractAnalysisCandidatesFromWorkspaceFiles(files);
  console.log(`extracted ${candidates.length} candidates from ${files.filter((f) => f.path.startsWith("30-candidates/")).length} candidate files`);

  const result = await deps.saveAnalysisCandidates!({
    tenant_id: row.tenant_id,
    project_id: row.project_id,
    run_id: runId,
    replace_run: true,
    import_to_assets: true,
    candidates,
  });

  await deps.updateAnalysisRunStatus?.({
    tenant_id: row.tenant_id,
    project_id: row.project_id,
    run_id: runId,
    status: "completed",
    result: {
      candidate_count: result.candidate_count,
      asset_count: result.asset_count ?? result.candidate_count,
      file_count: files.length,
      repaired_at: new Date().toISOString(),
    },
  });

  console.log(JSON.stringify(result, null, 2));
} finally {
  await db.close();
}
