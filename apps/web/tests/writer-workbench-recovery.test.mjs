import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import { decodeWriterCredentialEncryptionKey } from "../scripts/prepare-live-writer-fixture.mjs";

const root = path.resolve(import.meta.dirname, "..");

async function writerShell() {
  return readFile(path.join(root, "components/writer-workbench-shell.tsx"), "utf8");
}

test("writer recovery keeps run trace and explicit replay cursors across refresh and reconnect", async () => {
  const shell = await writerShell();

  assert.match(shell, /function RecoveryActions/);
  assert.match(shell, /Refresh run status/);
  assert.match(shell, /Reconnect after latest event/);
  assert.match(shell, /latestEvent\?\.event_id \|\| afterEventId/);
  assert.match(shell, /function RecoveryFields/);
  assert.match(shell, /name="runId"/);
  assert.match(shell, /name="traceId"/);
  assert.match(shell, /name="after_event_id"/);
  assert.match(shell, /draftId \? <input name="draftId" type="hidden" value=\{draftId\}/);
  assert.match(shell, /method="get"/);
  assert.doesNotMatch(shell, /new EventSource|EventSource\(/);
  assert.doesNotMatch(shell, /JSON\.stringify\(event\.payload/);
});

test("writer candidate recovery and adoption remain metadata-only and explicitly user triggered", async () => {
  const shell = await writerShell();

  assert.match(shell, /selectedDraftId\?: string/);
  assert.match(shell, /recoverDraftId\(selectedDraftId, runSummary, workflowEvents\)/);
  assert.match(shell, /writer\.draft\.saved/);
  assert.match(shell, /writer\.run\.completed/);
  assert.match(shell, /stringValue\(event\.payload, "draft_id"\)/);
  assert.match(shell, /function DraftAdoptionPanel/);
  assert.match(shell, /name="draftId"/);
  assert.match(shell, /Adopt draft into manuscript/);
  assert.match(shell, /!adopted && action/);
  assert.doesNotMatch(shell, /useEffect|componentDidMount/);
  assert.doesNotMatch(shell, /draft_text|manuscript_text|content_text|prompt_snapshot/i);
});

test("writer export controls expose a real artifact download and fail closed without one", async () => {
  const shell = await writerShell();

  assert.match(shell, /export type WriterManuscriptExportArtifact/);
  assert.match(shell, /artifact_id: string/);
  assert.match(shell, /download_href: string/);
  assert.match(shell, /exportManuscriptAction/);
  assert.match(shell, /Generate manuscript export/);
  assert.match(shell, /function ManuscriptArtifactDownload/);
  assert.match(shell, /action=\{artifact\.download_href\}/);
  assert.match(shell, /Download exported manuscript/);
  assert.match(shell, /FailureText/);
  assert.doesNotMatch(shell, /data:text|URL\.createObjectURL|new Blob/);
});

test("writer cancellation is active-run only and retry remains an explicit new admission", async () => {
  const shell = await writerShell();
  const page = await readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx"), "utf8");

  assert.match(shell, /function WriterRunControl/);
  assert.match(shell, /runStatus === "queued" \|\| runStatus === "running"/);
  assert.match(shell, /Cancel writer run/);
  assert.match(page, /function cancelWriterRunAction/);
  assert.match(page, /\/v1\/writer-runs\/\$\{encodeURIComponent\(runId\)\}\/cancel/);
  assert.match(page, /writerActionHeaders\(context\)/);
  assert.match(page, /WRITER_RUN_CANCELLED/);
  assert.doesNotMatch(page, /\/v1\/writer-runs\/[^\n]*\/retry/);
  assert.doesNotMatch(shell, /useEffect|componentDidMount/);
});

test("writer reviewer UI is explicit, recoverable, and issue actions remain metadata-only", async () => {
  const [shell, page, workspace] = await Promise.all([
    writerShell(),
    readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx"), "utf8"),
    readFile(path.join(root, "components/writer-product-workspace.tsx"), "utf8"),
  ]);

  assert.match(page, /selectedDraftId=\{recoveredDraftId\}/);
  assert.match(page, /listDraftReviews\(workspaceContext, props\.selectedDraftId\)/);
  assert.match(page, /function draftIdFromWriterEvents/);
  assert.match(page, /startDraftReview\(/);
  assert.match(page, /updateReviewIssue\(/);
  assert.match(workspace, /function ReviewerPanel/);
  assert.match(workspace, /Start reviewer/);
  assert.match(workspace, /issue\.status === "open" && issue\.updated_at/);
  assert.match(workspace, /name="status"/);
  assert.match(workspace, /name="draftId"/);
  assert.doesNotMatch(shell, /function DraftReviewPanel/);
  const reviewerPanel = workspace.slice(workspace.indexOf("function ReviewerPanel"), workspace.indexOf("function ChapterScenePanel"));
  assert.doesNotMatch(reviewerPanel, /adopt|manuscript/i);
});

test("writer live fixture is isolated and never prints credential key material", async () => {
  const fixturePath = path.join(root, "scripts/prepare-live-writer-fixture.mjs");
  const fixture = await readFile(fixturePath, "utf8");
  const provider = await readFile(path.join(root, "scripts/writer-live-provider.mjs"), "utf8");
  const hexKey = "0123456789abcdef".repeat(4);
  const base64Key = Buffer.alloc(32, 0xa5).toString("base64");

  assert.match(fixture, /c1000000-0000-4000-8000-/);
  assert.doesNotMatch(fixture, /91000000-0000-4000-8000-/);
  assert.doesNotMatch(fixture, /101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f/);
  assert.match(fixture, /required\("LLM_CREDENTIAL_ENCRYPTION_KEY"\)/);
  assert.doesNotMatch(fixture, /keyMaterial,\s*\n\s*}\)\}/);
  assert.deepEqual(decodeWriterCredentialEncryptionKey(hexKey), Buffer.from(hexKey, "hex"));
  assert.deepEqual(decodeWriterCredentialEncryptionKey(base64Key), Buffer.from(base64Key, "base64"));
  for (const invalid of [
    "private-invalid-key-material",
    "0".repeat(62),
    Buffer.alloc(31, 0xa5).toString("base64"),
    Buffer.alloc(33, 0xa5).toString("base64"),
    Buffer.alloc(32, 0xff).toString("base64").replace(/\//g, "_"),
  ]) {
    assert.throws(
      () => decodeWriterCredentialEncryptionKey(invalid),
      (error) => error instanceof Error && /must be 32-byte hex or standard base64/.test(error.message) && !error.message.includes(invalid),
    );
  }
  const missingKey = spawnSync(process.execPath, [fixturePath, "prepare"], {
    encoding: "utf8",
    env: {
      PATH: process.env.PATH,
      MIROFISH_WEB_WRITER_FIXTURE_DATABASE_URL: "postgresql://fixture@127.0.0.1:55432/mirofish_test_unit",
      MIROFISH_WEB_WRITER_FIXTURE_PROVIDER_BASE_URL: "http://127.0.0.1:43117/v1",
    },
  });
  assert.notEqual(missingKey.status, 0);
  assert.match(missingKey.stderr, /missing MIROFISH_WEB_WRITER_FIXTURE_LLM_CREDENTIAL_ENCRYPTION_KEY/);
  assert.doesNotMatch(missingKey.stderr, /writer-browser-local-key|1011121314151617/);
  assert.match(fixture, /assertLocalDatabase/);
  assert.match(fixture, /INSERT INTO llm_quota_policies/);
  assert.match(fixture, /'module','\$\{ids\.project\}','writer_orchestrator'/);
  assert.match(fixture, /'module','\$\{ids\.project\}','writer_composer'/);
  assert.match(fixture, /'module','\$\{ids\.project\}','writer_reviewer'/);
  assert.match(fixture, /'module','\$\{ids\.project\}','writer_dedup_extractor'/);
  assert.match(fixture, /'module','\$\{ids\.project\}','writer_book_planner'/);
  assert.match(fixture, /INSERT INTO book_plans/);
  assert.match(provider, /query_graph_neighbors/);
  assert.match(provider, /writer-live-reviewer/);
  assert.match(provider, /writer-live-dedup/);
  assert.match(provider, /writer-live-book-planner/);
  assert.match(provider, /pov_drift/);
  assert.match(provider, /CANCEL_BOUNDARY/);
  assert.match(provider, /MIROFISH_WRITER_CANCEL_BOUNDARY_TIMEOUT_MS/);
  assert.match(provider, /cancellationBoundaryTimeoutMs/);
  assert.doesNotMatch(provider, /waitForCancellationBoundary\(response, 5_000\)/);
});
