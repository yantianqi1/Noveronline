import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

function sourceSlice(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.notEqual(start, -1, `missing source slice start marker: ${startMarker}`);
  assert.notEqual(end, -1, `missing source slice end marker: ${endMarker}`);
  return source.slice(start, end);
}

test("Next app shell declares tenant/project writer route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getWriterRunSummary/);
  assert.match(page, /WriterWorkbenchShell/);
});

test("writer API client exposes metadata-only manuscript endpoints with tenant headers", async () => {
  const client = await fileText("lib/api.ts");
  const manuscriptClient = [
    sourceSlice(client, "export type ManuscriptBlockMetadata", "export type WorkflowRunSummary"),
    sourceSlice(client, "export async function getProjectManuscript", "export async function getWorkflowRunSummary"),
    sourceSlice(client, "async function decodeProjectManuscriptResponse", "async function decodeWorkflowRunResponse"),
    sourceSlice(client, "function decodeManuscriptBlockMetadata", "function decodeWorkflowRunEvent"),
  ].join("\n");

  assert.match(manuscriptClient, /ManuscriptBlockMetadata/);
  assert.match(manuscriptClient, /ProjectManuscriptSummary/);
  assert.match(manuscriptClient, /ManuscriptExportManifestBlock/);
  assert.match(manuscriptClient, /ProjectManuscriptExportManifestSummary/);
  assert.match(manuscriptClient, /getProjectManuscript/);
  assert.match(manuscriptClient, /getProjectManuscriptExportManifest/);
  assert.match(manuscriptClient, /\/v1\/projects\/\$\{input\.projectId\}\/manuscript`/);
  assert.match(manuscriptClient, /\/v1\/projects\/\$\{input\.projectId\}\/manuscript\/export`/);
  assert.match(manuscriptClient, /headers:\s*contextHeaders\(input\)/);
  assert.equal((manuscriptClient.match(/headers:\s*contextHeaders\(input\)/g) ?? []).length, 2);
  assert.match(manuscriptClient, /block_id/);
  assert.match(manuscriptClient, /chapter_id/);
  assert.match(manuscriptClient, /source_draft_id/);
  assert.match(manuscriptClient, /block_order/);
  assert.match(manuscriptClient, /word_count/);
  assert.match(manuscriptClient, /generated_at/);
  assert.doesNotMatch(manuscriptClient, /block_ids/);
  assert.doesNotMatch(manuscriptClient, /content_text:\s*string/);
  assert.doesNotMatch(manuscriptClient, /draft_text:\s*string/);
  assert.doesNotMatch(manuscriptClient, /manuscript_text:\s*string/);
  assert.doesNotMatch(manuscriptClient, /raw_body:\s*string/);
  assert.doesNotMatch(manuscriptClient, /exported_at:\s*string/);
  assert.doesNotMatch(manuscriptClient, /credential_ref:\s*string/);
  assert.doesNotMatch(manuscriptClient, /encrypted_api_key:\s*string/);
  assert.doesNotMatch(manuscriptClient, /api_key:\s*string/);
});

test("writer page loads manuscript summaries alongside picker data", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");

  assert.match(page, /getProjectManuscript/);
  assert.match(page, /getProjectManuscriptExportManifest/);
  assert.match(page, /const\s*\[\s*assets,\s*graphView,\s*worldlineSavedPaths,\s*manuscript,\s*manuscriptExportManifest\s*\]\s*=\s*await\s+Promise\.all/);
  assert.match(page, /getProjectManuscript\(\{\s*\.\.\.apiContext,\s*projectId,\s*\}\)/s);
  assert.match(page, /getProjectManuscriptExportManifest\(\{\s*\.\.\.apiContext,\s*projectId,\s*\}\)/s);
  assert.match(page, /manuscript=\{manuscript\}/);
  assert.match(page, /manuscriptExportManifest=\{manuscriptExportManifest\}/);
});

test("Writer shell renders metadata-only manuscript and export panels", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");

  assert.match(shell, /ProjectManuscriptSummary/);
  assert.match(shell, /ProjectManuscriptExportManifestSummary/);
  assert.match(shell, /manuscript\.ok/);
  assert.match(shell, /manuscriptExportManifest\.ok/);
  assert.match(shell, /Manuscript metadata/);
  assert.match(shell, /Export manifest/);
  assert.match(shell, /MANUSCRIPT_BACKEND_UNCONFIGURED/);
  assert.match(shell, /MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED/);
  assert.match(shell, /block\.block_id/);
  assert.match(shell, /block\.chapter_id/);
  assert.match(shell, /block\.source_draft_id/);
  assert.match(shell, /block\.word_count/);
  assert.match(shell, /manifestBlock\.block_id/);
  assert.match(shell, /manifestBlock\.word_count/);
  assert.match(shell, /generated_at/);
  assert.doesNotMatch(shell, /block_ids/);
  assert.doesNotMatch(shell, /content_text/);
  assert.doesNotMatch(shell, /draft_text/);
  assert.doesNotMatch(shell, /manuscript_text/);
  assert.doesNotMatch(shell, /raw_body/);
  assert.doesNotMatch(shell, /exported_at/);
  assert.doesNotMatch(shell, /credential_ref|encrypted_api_key|api_key/i);
  assert.doesNotMatch(shell, /PDF|DOCX|TXT/);
});

test("project navigation includes writer and LLM Facility routes with active path state", async () => {
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(layout, /ProjectNav/);
  assert.match(nav, /usePathname/);
  assert.match(nav, /\/overview/);
  assert.match(nav, /\/writer/);
  assert.match(nav, /\/llm-facility/);
  assert.match(nav, /Overview/);
  assert.match(nav, /LLM Facility/);
  assert.match(nav, /aria-current/);
});

test("Next app shell declares tenant/project Overview route for source files and Seed runs", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /afterEventId\?:\s*string/);
  assert.match(page, /after_event_id\?:\s*string/);
  assert.match(page, /afterEventId:\s*query\.after_event_id\s*\?\?\s*query\.afterEventId\s*\?\?\s*""/);
  assert.match(page, /getProjectOverview/);
  assert.match(page, /getProjectSourceFiles/);
  assert.match(page, /getProjectReadinessSnapshot/);
  assert.match(page, /createSourceFileUpload/);
  assert.match(page, /uploadSourceFileObject/);
  assert.match(page, /completeSourceFileUpload/);
  assert.match(page, /startSeedRun/);
  assert.match(page, /getProjectSeedRuns/);
  assert.match(page, /getSeedRunSummary/);
  assert.match(page, /getSeedRunEvents/);
  assert.match(page, /cancelSeedRun/);
  assert.match(page, /retrySeedRun/);
  assert.match(page, /admitSourceFileAction/);
  assert.match(page, /uploadSourceObjectAction/);
  assert.match(page, /completeUploadAction/);
  assert.match(page, /startSeedRunAction/);
  assert.match(page, /cancelSeedRunAction/);
  assert.match(page, /retrySeedRunAction/);
  assert.match(page, /OverviewSeedShell/);
  assert.match(page, /projectOverview=\{projectOverview\}/);
  assert.match(page, /projectReadiness=\{projectReadiness\}/);
});

test("source file, Seed, readiness, and overview API client uses sanitized Go endpoints and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /ProjectOverviewRecord/);
  assert.match(client, /ProjectOverviewSummary/);
  assert.match(client, /SourceFileRecord/);
  assert.match(client, /SourceFilesSummary/);
  assert.match(client, /ProjectReadinessSnapshot/);
  assert.match(client, /ProjectReadinessSummary/);
  assert.match(client, /SeedRunStartSummary/);
  assert.match(client, /getProjectOverview/);
  assert.match(client, /getProjectSourceFiles/);
  assert.match(client, /getProjectReadinessSnapshot/);
  assert.match(client, /createSourceFileUpload/);
  assert.match(client, /UploadSourceFileObjectInput/);
  assert.match(client, /SourceFileObjectUploadSummary/);
  assert.match(client, /uploadSourceFileObject/);
  assert.match(client, /completeSourceFileUpload/);
  assert.match(client, /startSeedRun/);
  assert.match(client, /cancelSeedRun/);
  assert.match(client, /retrySeedRun/);
  assert.match(client, /getProjectSeedRuns/);
  assert.match(client, /getSeedRunSummary/);
  assert.match(client, /getSeedRunEvents/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/uploads`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/overview`/);
  assert.match(client, /\/v1\/uploads\/\$\{input\.uploadId\}\/object`/);
  assert.match(client, /method:\s*"PUT"/);
  assert.match(client, /body:\s*input\.file/);
  assert.match(client, /\/v1\/uploads\/\$\{input\.uploadId\}\/complete`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/source-files`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/readiness`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/seed-runs`/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}`/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}\/events/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}\/cancel`/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}\/retry`/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.match(client, /upload_id/);
  assert.match(client, /source_file_count/);
  assert.match(client, /seed_run_count/);
  assert.match(client, /active_workflow_run_id/);
  assert.match(client, /active_workflow_type/);
  assert.match(client, /active_workflow_status/);
  assert.match(client, /asset_count/);
  assert.match(client, /graph_node_count/);
  assert.match(client, /graph_edge_count/);
  assert.match(client, /worldline_session_count/);
  assert.match(client, /worldline_event_count/);
  assert.match(client, /character_interaction_count/);
  assert.match(client, /writer_run_count/);
  assert.match(client, /llm_activity_count/);
  assert.match(client, /llm_token_count/);
  assert.match(client, /llm_enabled_channel_count/);
  assert.match(client, /llm_bound_module_count/);
  assert.match(client, /llm_missing_core_module_count/);
  assert.match(client, /llm_sync_ok_channel_count/);
  assert.match(client, /llm_sync_failed_channel_count/);
  assert.match(client, /llm_sync_pending_channel_count/);
  assert.match(client, /llm_latest_sync_at/);
  assert.match(client, /latest_failed_workflow_run_id/);
  assert.match(client, /latest_failed_workflow_type/);
  assert.match(client, /latest_failed_workflow_error_code/);
  assert.match(client, /latest_failed_workflow_updated_at/);
  assert.match(client, /readiness_snapshot_id/);
  assert.match(client, /readiness_run_id/);
  assert.match(client, /project_readiness_snapshot_id/);
  assert.match(client, /ready_asset_count/);
  assert.match(client, /ready_entity_count/);
  assert.match(client, /ready_relationship_count/);
  assert.match(client, /ready_world_rule_count/);
  assert.match(client, /parse_status/);
  assert.doesNotMatch(client, /object_key:\s*string/);
  assert.doesNotMatch(client, /source_object_key:\s*string/);
  assert.doesNotMatch(client, /presigned/i);
  assert.doesNotMatch(client, /raw_text:\s*string/);
  assert.doesNotMatch(client, /parsed_text:\s*string/);
  assert.doesNotMatch(client, /readiness_report_body:\s*string/);
  assert.doesNotMatch(client, /prompt:\s*string/);
  assert.doesNotMatch(client, /response:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
  assert.doesNotMatch(client, /latest_failed_workflow_error_message/);
});

test("Overview Seed shell renders explicit source file and Seed run states", async () => {
  const shell = await fileText("components/overview-seed-shell.tsx");

  assert.match(shell, /Source files/);
  assert.match(shell, /Project health/);
  assert.match(shell, /projectOverview\.ok/);
  assert.match(shell, /projectOverview\.status/);
  assert.match(shell, /source_file_count/);
  assert.match(shell, /seed_run_count/);
  assert.match(shell, /active_workflow_run_id/);
  assert.match(shell, /active_workflow_type/);
  assert.match(shell, /active_workflow_status/);
  assert.match(shell, /Asset records/);
  assert.match(shell, /Graph nodes/);
  assert.match(shell, /Graph edges/);
  assert.match(shell, /Worldline sessions/);
  assert.match(shell, /Worldline events/);
  assert.match(shell, /Character interactions/);
  assert.match(shell, /Writer runs/);
  assert.match(shell, /LLM calls/);
  assert.match(shell, /LLM tokens/);
  assert.match(shell, /LLM enabled channels/);
  assert.match(shell, /LLM bound modules/);
  assert.match(shell, /LLM missing core modules/);
  assert.match(shell, /LLM sync ok channels/);
  assert.match(shell, /LLM sync failed channels/);
  assert.match(shell, /LLM sync pending channels/);
  assert.match(shell, /LLM latest sync/);
  assert.match(shell, /Latest failed workflow/);
  assert.match(shell, /Failure code/);
  assert.match(shell, /Failure updated/);
  assert.match(shell, /asset_count/);
  assert.match(shell, /graph_node_count/);
  assert.match(shell, /graph_edge_count/);
  assert.match(shell, /worldline_session_count/);
  assert.match(shell, /worldline_event_count/);
  assert.match(shell, /character_interaction_count/);
  assert.match(shell, /writer_run_count/);
  assert.match(shell, /llm_activity_count/);
  assert.match(shell, /llm_token_count/);
  assert.match(shell, /llm_enabled_channel_count/);
  assert.match(shell, /llm_bound_module_count/);
  assert.match(shell, /llm_missing_core_module_count/);
  assert.match(shell, /llm_sync_ok_channel_count/);
  assert.match(shell, /llm_sync_failed_channel_count/);
  assert.match(shell, /llm_sync_pending_channel_count/);
  assert.match(shell, /llm_latest_sync_at/);
  assert.match(shell, /latest_failed_workflow_run_id/);
  assert.match(shell, /latest_failed_workflow_type/);
  assert.match(shell, /latest_failed_workflow_error_code/);
  assert.match(shell, /latest_failed_workflow_updated_at/);
  assert.match(shell, /readiness_snapshot_id/);
  assert.match(shell, /readiness_run_id/);
  assert.match(shell, /PROJECT_OVERVIEW_BACKEND_UNCONFIGURED/);
  assert.match(shell, /Project readiness/);
  assert.match(shell, /projectReadiness\.ok/);
  assert.match(shell, /ready_asset_count/);
  assert.match(shell, /ready_entity_count/);
  assert.match(shell, /ready_relationship_count/);
  assert.match(shell, /ready_world_rule_count/);
  assert.match(shell, /Admit source file/);
  assert.match(shell, /Upload object/);
  assert.match(shell, /uploadSourceObjectAction/);
  assert.match(shell, /type="file"/);
  assert.match(shell, /name="file"/);
  assert.match(shell, /Complete upload/);
  assert.match(shell, /Complete this upload/);
  assert.match(shell, /name="uploadId"/);
  assert.match(shell, /value=\{file\.upload_id\}/);
  assert.match(shell, /Seed pipeline/);
  assert.match(shell, /Seed runs/);
  assert.match(shell, /Inspect Seed run/);
  assert.match(shell, /Inspect/);
  assert.match(shell, /name="runId"/);
  assert.match(shell, /name="after_event_id"/);
  assert.match(shell, /Event cursor/);
  assert.match(shell, /Seed events/);
  assert.match(shell, /startSeedRunAction/);
  assert.match(shell, /cancelSeedRunAction/);
  assert.match(shell, /retrySeedRunAction/);
  assert.match(shell, /completeUploadAction/);
  assert.match(shell, /Cancel Seed run/);
  assert.match(shell, /Retry Seed run/);
  assert.match(shell, /PROJECT_READINESS_BACKEND_UNCONFIGURED/);
  assert.match(shell, /sourceFiles\.ok/);
  assert.match(shell, /seedRuns\.ok/);
  assert.match(shell, /selectedSeedRun\.ok/);
  assert.match(shell, /seedEvents\.ok/);
  assert.match(shell, /SOURCE_FILE_BACKEND_UNCONFIGURED/);
  assert.doesNotMatch(shell, /object key/i);
  assert.doesNotMatch(shell, /presigned/i);
  assert.doesNotMatch(shell, /readiness report body/i);
  assert.doesNotMatch(shell, /mock/i);
});

test("Next app shell declares tenant/project LLM Facility route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /upsertLLMModuleBinding/);
  assert.match(page, /createLLMChannel/);
  assert.match(page, /updateLLMChannel/);
  assert.match(page, /deleteLLMChannel/);
  assert.match(page, /syncLLMChannelModels/);
  assert.match(page, /getLLMSettings/);
  assert.match(page, /deleteLLMModuleBinding/);
  assert.match(page, /optionalPositiveNumberFromFormData\(formData,\s*"moduleMaxConcurrency"\)/);
  assert.match(page, /max_concurrency:\s*moduleMaxConcurrency/);
  assert.match(page, /bindModuleAction/);
  assert.match(page, /clearBindingAction/);
  assert.match(page, /createChannelAction/);
  assert.match(page, /updateChannelAction/);
  assert.match(page, /deleteChannelAction/);
  assert.match(page, /syncChannelAction/);
  assert.match(page, /getLLMChannels/);
  assert.match(page, /getLLMChannelModels/);
  assert.match(page, /getLLMModules/);
  assert.match(page, /getLLMModuleBindings/);
  assert.match(page, /resolveLLMModuleBinding/);
  assert.match(page, /getLLMActivity/);
  assert.match(page, /getLLMUsage/);
  assert.match(page, /LLMFacilityShell/);
});

test("Next app shell declares tenant/project Asset Library route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/assets/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getProjectAssets/);
  assert.match(page, /getAssetFacets/);
  assert.match(page, /getArchiveAssetMemories/);
  assert.match(page, /getArchiveAssetMemoryEvents/);
  assert.match(page, /adoptArchiveMemory/);
  assert.match(page, /rejectArchiveMemory/);
  assert.match(page, /searchAssets/);
  assert.match(page, /createAsset/);
  assert.match(page, /updateAsset/);
  assert.match(page, /deleteAsset/);
  assert.match(page, /adoptAsset/);
  assert.match(page, /bulkActionAssets/);
  assert.match(page, /startAssetIngestion/);
  assert.match(page, /startAssetReindex/);
  assert.match(page, /memoryAssetId/);
  assert.match(page, /memoryAssetAction/);
  assert.match(page, /adoptArchiveMemoryAction/);
  assert.match(page, /rejectArchiveMemoryAction/);
  assert.match(page, /createAssetAction/);
  assert.match(page, /updateAssetAction/);
  assert.match(page, /deleteAssetAction/);
  assert.match(page, /adoptAssetAction/);
  assert.match(page, /bulkAssetAction/);
  assert.match(page, /ingestAssetAction/);
  assert.match(page, /reindexAssetsAction/);
  assert.match(page, /AssetLibraryShell/);
});

test("legacy Asset Library entry routes redirect to the SaaS asset workspace", async () => {
  const archiveRoute = await fileText("app/archive-library/page.tsx");
  const assetRoute = await fileText("app/asset-library/page.tsx");

  for (const route of [archiveRoute, assetRoute]) {
    assert.match(route, /redirect/);
    assert.match(route, /\/demo\/projects\/demo-project\/assets/);
    assert.doesNotMatch(route, /mock/i);
    assert.doesNotMatch(route, /api_key|encrypted_api_key|credential_ref/i);
  }
});

test("Next app shell declares tenant/project Worldline route with saved-path read side", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx");
  const shell = await fileText("components/worldline-shell.tsx");
  const client = await fileText("lib/api.ts");
  const legacyRoute = await fileText("app/worldline/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getWorldlineSavedPaths/);
  assert.match(page, /getWorldlineSessions/);
  assert.match(page, /getWorldlineTimeline/);
  assert.match(page, /getWorldlineEvents/);
  assert.match(page, /getWorldlinePreparation/);
  assert.match(page, /getWorldlinePreparedAgents/);
  assert.match(page, /startWorldlineSession/);
  assert.match(page, /createWorldlinePreparation/);
  assert.match(page, /injectWorldlineVariable/);
  assert.match(page, /createWorldlineSavedPath/);
  assert.match(page, /adoptWorldlineEvent/);
  assert.match(page, /updateWorldlineEvent/);
  assert.match(page, /startWorldlineStep/);
  assert.match(page, /startWorldlineSessionAction/);
  assert.match(page, /startWorldlineStepAction/);
  assert.match(page, /createWorldlinePreparationAction/);
  assert.match(page, /injectWorldlineVariableAction/);
  assert.match(page, /createWorldlineSavedPathAction/);
  assert.match(page, /adoptWorldlineEventAction/);
  assert.match(page, /updateWorldlineEventAction/);
  assert.match(page, /worldlineSessionStatus/);
  assert.match(page, /worldlinePreparationStatus/);
  assert.match(page, /worldlineVariableStatus/);
  assert.match(page, /worldlineSavedPathStatus/);
  assert.match(page, /worldlineEventAdoptionStatus/);
  assert.match(page, /worldlineEventMutationStatus/);
  assert.match(page, /worldlineStepStatus/);
  assert.match(page, /WorldlineShell/);
  assert.match(shell, /savedPaths\.ok/);
  assert.match(shell, /sessions\.ok/);
  assert.match(shell, /timeline\.ok/);
  assert.match(shell, /events\.ok/);
  assert.match(shell, /preparation/);
  assert.match(shell, /preparedAgents/);
  assert.match(shell, /Start session/);
  assert.match(shell, /Step session/);
  assert.match(shell, /Variable injection/);
  assert.match(shell, /Save path/);
  assert.match(shell, /Prepare agents/);
  assert.match(shell, /Prepared agents/);
  assert.match(shell, /Session history/);
  assert.match(shell, /Timeline/);
  assert.match(shell, /Candidate events/);
  assert.match(shell, /Edit event/);
  assert.match(shell, /Adopt event/);
  assert.match(shell, /WORLDLINE_TIMELINE_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_EVENT_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_STEP_BACKEND_UNCONFIGURED/);
  assert.match(shell, /startWorldlineSessionAction/);
  assert.match(shell, /startWorldlineStepAction/);
  assert.match(shell, /createWorldlinePreparationAction/);
  assert.match(shell, /injectWorldlineVariableAction/);
  assert.match(shell, /createWorldlineSavedPathAction/);
  assert.match(shell, /adoptWorldlineEventAction/);
  assert.match(shell, /updateWorldlineEventAction/);
  assert.match(shell, /name="goal"/);
  assert.match(shell, /name="stepMode"/);
  assert.match(shell, /name="variableName"/);
  assert.match(shell, /name="impactAxis"/);
  assert.match(shell, /name="savedPathTitle"/);
  assert.match(shell, /name="selectedEventIds"/);
  assert.match(shell, /name="eventTitle"/);
  assert.match(shell, /name="eventSummary"/);
  assert.match(shell, /name="eventKind"/);
  assert.match(shell, /name="preparationGoal"/);
  assert.match(shell, /name="anchorPathId"/);
  assert.match(shell, /worldlineSessionStatus/);
  assert.match(shell, /worldlinePreparationStatus/);
  assert.match(shell, /worldlineSavedPathStatus/);
  assert.match(shell, /worldlineEventAdoptionStatus/);
  assert.match(shell, /worldlineEventMutationStatus/);
  assert.match(shell, /worldlineStepStatus/);
  assert.match(shell, /WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_SESSION_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_BACKEND_UNCONFIGURED/);
  assert.match(shell, /path\.path_id/);
  assert.match(client, /CreateWorldlineSavedPathInput/);
  assert.match(client, /createWorldlineSavedPath/);
  assert.match(client, /adoptWorldlineEvent/);
  assert.match(client, /UpdateWorldlineEventInput/);
  assert.match(client, /updateWorldlineEvent/);
  assert.match(client, /StartWorldlineStepInput/);
  assert.match(client, /startWorldlineStep/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/saved-paths`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/steps`/);
  assert.match(client, /\/v1\/worldline-events\/\$\{input\.eventId\}\/adoptions`/);
  assert.match(client, /\/v1\/worldline-events\/\$\{input\.eventId\}`/);
  assert.match(client, /selected_event_ids/);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.match(legacyRoute, /redirect/);
  assert.match(legacyRoute, /\/demo\/projects\/demo-project\/worldline/);
  assert.doesNotMatch(legacyRoute, /mock/i);
  assert.match(nav, /\/worldline/);
  assert.match(nav, /Worldline/);
});

test("worldline API client exposes preparation endpoints without credential fields", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /WorldlineEventRecord/);
  assert.match(client, /WorldlineEventsSummary/);
  assert.match(client, /WorldlinePreparationRecord/);
  assert.match(client, /WorldlinePreparedAgentRecord/);
  assert.match(client, /getWorldlineEvents/);
  assert.match(client, /createWorldlinePreparation/);
  assert.match(client, /getWorldlinePreparation/);
  assert.match(client, /getWorldlinePreparedAgents/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/events/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldlines\/preparations`/);
  assert.match(client, /\/v1\/worldline-preparations\/\$\{input\.prepareId\}`/);
  assert.match(client, /\/v1\/worldline-preparations\/\$\{input\.prepareId\}\/agents`/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(client, /body_text:\s*string/);
  assert.doesNotMatch(client, /content_text:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("worldline API client exposes metadata-only variable injection", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /WorldlineVariableRecord/);
  assert.match(client, /WorldlineVariableSummary/);
  assert.match(client, /injectWorldlineVariable/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/variables`/);
  assert.match(client, /impact_axis/);
  assert.match(client, /locked/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(client, /body_text:\s*string/);
  assert.doesNotMatch(client, /content_text:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("Next app shell declares tenant/project Character Console route with explicit pending runtime", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/character-console/page.tsx");
  const shell = await fileText("components/character-console-shell.tsx");
  const legacyRoute = await fileText("app/character-console/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /CharacterConsoleShell/);
  assert.match(page, /listCharacterInteractions/);
  assert.match(page, /interactions=/);
  assert.match(shell, /CHARACTER_CONSOLE_RUNTIME_PENDING/);
  assert.match(shell, /WORLDLINE_SESSION_REQUIRED/);
  assert.match(shell, /CharacterInteractionsSummary/);
  assert.match(shell, /interactions\.ok/);
  assert.match(shell, /Convert to chapter draft/);
  assert.doesNotMatch(shell, /mock/i);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
  assert.match(legacyRoute, /redirect/);
  assert.match(legacyRoute, /\/demo\/projects\/demo-project\/character-console/);
  assert.doesNotMatch(legacyRoute, /mock/i);
  assert.match(nav, /\/character-console/);
  assert.match(nav, /Character Console/);
});

test("Character Console route exposes create interaction metadata form and action", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/character-console/page.tsx");
  const shell = await fileText("components/character-console-shell.tsx");

  assert.match(page, /createCharacterInteractionAction/);
  assert.match(page, /createCharacterInteraction/);
  assert.match(page, /appendCharacterInteractionTurnAction/);
  assert.match(page, /appendCharacterInteractionTurn/);
  assert.match(page, /updateCharacterInteractionStatusAction/);
  assert.match(page, /updateCharacterInteractionStatus/);
  assert.match(page, /getCharacterInteraction/);
  assert.match(page, /listCharacterInteractionTurns/);
  assert.match(page, /getCharacterInteractionEvents/);
  assert.match(page, /convertCharacterInteractionToChapterDraft/);
  assert.match(page, /getWorldlineEvents/);
  assert.match(page, /getWorldlinePreparedAgents/);
  assert.match(page, /getWorldlineSavedPaths/);
  assert.match(page, /getWorldlineSessions/);
  assert.match(page, /getStoryGraphView/);
  assert.match(page, /viewId:\s*"current"/);
  assert.match(page, /types:\s*\[\s*"character",\s*"organization",\s*"location",\s*"plot_thread"\s*\]/);
  assert.match(page, /includeEdges:\s*false/);
  assert.match(page, /inspectWorldlineEventAnchorsAction/);
  assert.match(page, /inspectWorldlinePreparationAgentsAction/);
  assert.match(page, /inspectCharacterInteractionAction/);
  assert.match(page, /inspectCharacterInteractionTurnsAction/);
  assert.match(page, /inspectCharacterInteractionEventsAction/);
  assert.match(page, /convertCharacterInteractionToChapterDraftAction/);
  assert.match(page, /searchParams/);
  assert.match(page, /anchor_session_id/);
  assert.match(page, /characterConsoleStatusRoute/);
  assert.match(page, /prepare_id/);
  assert.match(page, /selected_interaction_id/);
  assert.match(page, /turns_interaction_id/);
  assert.match(page, /runtime_status/);
  assert.match(page, /runtime_code/);
  assert.match(page, /runtime_message/);
  assert.match(page, /interaction_status/);
  assert.match(page, /interaction_code/);
  assert.match(page, /interaction_message/);
  assert.match(page, /CHARACTER_INTERACTION_WRITER_RUN_QUEUED/);
  assert.match(page, /Writer run \$\{result\.run_id\} queued/);
  assert.match(page, /turn_status/);
  assert.match(page, /turn_code/);
  assert.match(page, /turn_message/);
  assert.match(page, /optionalJsonObjectFromFormData/);
  assert.match(page, /redirect/);

  assert.match(shell, /createCharacterInteractionAction/);
  assert.match(shell, /appendCharacterInteractionTurnAction/);
  assert.match(shell, /updateCharacterInteractionStatusAction/);
  assert.match(shell, /inspectCharacterInteractionAction/);
  assert.match(shell, /inspectCharacterInteractionTurnsAction/);
  assert.match(shell, /inspectCharacterInteractionEventsAction/);
  assert.match(shell, /convertCharacterInteractionToChapterDraftAction/);
  assert.match(shell, /inspectWorldlineEventAnchorsAction/);
  assert.match(shell, /anchorSessionId/);
  assert.match(shell, /interactionStatus/);
  assert.match(shell, /preparedAgents/);
  assert.match(shell, /prepareId/);
  assert.match(shell, /graphView/);
  assert.match(shell, /runtimeStatus/);
  assert.match(shell, /selectedInteraction/);
  assert.match(shell, /selectedTurns/);
  assert.match(shell, /savedPaths/);
  assert.match(shell, /worldlineEvents/);
  assert.match(shell, /worldlineSessions/);
  assert.match(shell, /CharacterInteractionDetailSummary/);
  assert.match(shell, /CharacterInteractionTurnsSummary/);
  assert.match(shell, /StoryGraphViewSummary/);
  assert.match(shell, /WorldlineSavedPathsSummary/);
  assert.match(shell, /WorldlineEventsSummary/);
  assert.match(shell, /WorldlinePreparedAgentsSummary/);
  assert.match(shell, /graphView\.ok/);
  assert.match(shell, /graphView\.nodes/);
  assert.match(shell, /savedPaths\.ok/);
  assert.match(shell, /savedPaths\.items/);
  assert.match(shell, /worldlineEvents\.ok/);
  assert.match(shell, /worldlineEvents\.items/);
  assert.match(shell, /preparedAgents\.ok/);
  assert.match(shell, /preparedAgents\.items/);
  assert.match(shell, /selectedInteraction\.ok/);
  assert.match(shell, /selectedInteraction\.turns/);
  assert.match(shell, /WorldlineSessionsSummary/);
  assert.match(shell, /worldlineSessions\.ok/);
  assert.match(shell, /worldlineSessions\.items/);
  assert.match(shell, /WORLDLINE_PREPARED_AGENTS_QUERY_FAILED/);
  assert.match(shell, /WORLDLINE_EVENT_QUERY_FAILED/);
  assert.match(shell, /WORLDLINE_BACKEND_UNCONFIGURED/);
  assert.match(shell, /WORLDLINE_SESSION_BACKEND_UNCONFIGURED/);
  assert.match(shell, /STORY_GRAPH_BACKEND_UNCONFIGURED/);
  assert.match(shell, /turnStatus/);
  assert.match(shell, /name="anchorSessionId"/);
  assert.match(shell, /name="prepareId"/);
  assert.match(shell, /name="worldlineSessionId"/);
  assert.match(shell, /name="anchorType"/);
  assert.match(shell, /name="anchorId"/);
  assert.match(shell, /name="povAgentId"/);
  assert.match(shell, /name="mode"/);
  assert.match(shell, /name="title"/);
  assert.match(shell, /name="summary"/);
  assert.match(shell, /name="interactionId"/);
  assert.match(shell, /name="actorType"/);
  assert.match(shell, /name="actorId"/);
  assert.match(shell, /name="turnKind"/);
  assert.match(shell, /name="turnSummary"/);
  assert.match(shell, /name="actionJson"/);
  assert.match(shell, /name="worldStateDeltaJson"/);
  assert.match(shell, /name="traceId"/);
  assert.match(shell, /name="selectedInteractionId"/);
  assert.match(shell, /name="turnsInteractionId"/);
  assert.match(shell, /name="runtimeInteractionId"/);
  assert.match(shell, /name="convertInteractionId"/);
  assert.match(shell, /name="targetChapterId"/);
  assert.match(shell, /name="povMode"/);
  assert.match(shell, /Create interaction/);
  assert.match(shell, /Inspect interaction/);
  assert.match(shell, /Load public turns/);
  assert.match(shell, /Check runtime events/);
  assert.match(shell, /Request chapter draft conversion/);
  assert.match(shell, /Writer run queued/);
  assert.match(shell, /Load worldline events/);
  assert.match(shell, /Load prepared agents/);
  assert.match(shell, /Graph nodes/);
  assert.match(shell, /Graph node anchors/);
  assert.match(shell, /graphView\.nodes\.slice\(0,\s*4\)/);
  assert.match(shell, /node\.node_type/);
  assert.match(shell, /node\.lifecycle/);
  assert.match(shell, /node\.summary/);
  assert.match(shell, /Character dossier/);
  assert.match(shell, /selectedInteraction\.pov_agent_id/);
  assert.match(shell, /preparedAgents\.items\.find/);
  assert.match(shell, /dossierAgent\.role/);
  assert.match(shell, /dossierAgent\.status/);
  assert.match(shell, /dossierAgent\.source_asset_id/);
  assert.match(shell, /dossierAgent\.summary/);
  assert.match(shell, /agentHistoryTurns/);
  assert.match(shell, /selectedInteraction\.turns\.filter/);
  assert.match(shell, /turn\.actor_id === selectedPovAgentId/);
  assert.match(shell, /turn\.actor_type === "user"/);
  assert.match(shell, /Public turn history/);
  assert.match(shell, /agentHistoryTurns\.slice\(0,\s*6\)/);
  assert.match(shell, /historyTurn\.turn_order/);
  assert.match(shell, /historyTurn\.summary/);
  assert.match(shell, /Saved paths/);
  assert.match(shell, /Record turn/);
  assert.match(shell, /Recorded turns/);
  assert.match(shell, /Public turn replay/);
  assert.match(shell, /SelectedPublicTurnReplay/);
  assert.match(shell, /selectedTurns\.ok/);
  assert.match(shell, /selectedTurns\.items/);
  assert.match(shell, /turn\.turn_order/);
  assert.match(shell, /turn\.actor_type/);
  assert.match(shell, /turn\.turn_kind/);
  assert.match(shell, /turn\.action/);
  assert.match(shell, /turn\.world_state_delta/);
  assert.match(shell, /Save interaction/);
  assert.match(shell, /Archive interaction/);
  assert.doesNotMatch(shell, /input_text|output_text|body_text|content_text/i);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
});

test("character console API client exposes metadata-only interaction endpoints", async () => {
  const client = await fileText("lib/api.ts");
  const characterClient = [
    sourceSlice(client, "export type CharacterInteractionRecord", "export type AssetSummary"),
    sourceSlice(client, "export async function listCharacterInteractions", "export async function createWorldlinePreparation"),
    sourceSlice(client, "async function decodeCharacterInteractionsResponse", "async function decodeAssetFacetsResponse"),
    sourceSlice(client, "function decodeCharacterInteractionRecord", "function decodeAssetFacetBucket"),
  ].join("\n");

  assert.match(client, /CharacterInteractionRecord/);
  assert.match(client, /CharacterInteractionTurnRecord/);
  assert.match(client, /CreateCharacterInteractionInput/);
  assert.match(client, /UpdateCharacterInteractionStatusInput/);
  assert.match(client, /CharacterInteractionsSummary/);
  assert.match(client, /CharacterInteractionDetailSummary/);
  assert.match(client, /CharacterInteractionSummary/);
  assert.match(client, /CharacterInteractionTurnsSummary/);
  assert.match(client, /CharacterInteractionEventsSummary/);
  assert.match(client, /CharacterInteractionChapterDraftSummary/);
  assert.match(client, /createCharacterInteraction/);
  assert.match(client, /updateCharacterInteractionStatus/);
  assert.match(client, /listCharacterInteractions/);
  assert.match(client, /getCharacterInteraction/);
  assert.match(client, /appendCharacterInteractionTurn/);
  assert.match(client, /listCharacterInteractionTurns/);
  assert.match(client, /getCharacterInteractionEvents/);
  assert.match(client, /convertCharacterInteractionToChapterDraft/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(client, /worldline_session_id:\s*input\.worldlineSessionId/);
  assert.match(client, /anchor_type:\s*input\.anchorType/);
  assert.match(client, /anchor_id:\s*input\.anchorId/);
  assert.match(client, /pov_agent_id:\s*input\.povAgentId/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/character-interactions`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}`/);
  assert.match(client, /method:\s*"PATCH"/);
  assert.match(client, /status:\s*input\.status/);
  assert.match(client, /items:\s*payload\.items\.map\(\(item\) => decodeCharacterInteractionTurnRecord\(item\)\)/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/turns`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/events`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/chapter-drafts`/);
  assert.match(client, /target_chapter_id:\s*input\.targetChapterId/);
  assert.match(client, /pov_mode:\s*input\.povMode/);
  assert.match(client, /run_id:\s*requiredString\(payload,\s*"run_id"\)/);
  assert.match(client, /trace_id:\s*requiredString\(payload,\s*"trace_id"\)/);
  assert.match(client, /workflow_type:\s*requiredString\(payload,\s*"workflow_type"\)/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(characterClient, /draft_id/);
  assert.doesNotMatch(characterClient, /input_text:\s*string/);
  assert.doesNotMatch(characterClient, /output_text:\s*string/);
  assert.doesNotMatch(characterClient, /body_text:\s*string/);
  assert.doesNotMatch(characterClient, /content_text:\s*string/);
  assert.doesNotMatch(characterClient, /credential_ref:\s*string/);
  assert.doesNotMatch(characterClient, /encrypted_api_key:\s*string/);
});

test("Next app shell declares tenant/project Guide route with explicit onboarding states", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/guide/page.tsx");
  const shell = await fileText("components/guide-shell.tsx");
  const legacyRoute = await fileText("app/guide/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /GuideShell/);
  assert.match(shell, /Guide/);
  assert.match(shell, /Onboarding status/);
  assert.match(shell, /SAAS_GUIDE_RUNTIME_PENDING/);
  assert.match(shell, /Writer-first/);
  assert.match(shell, /Phase 4/);
  assert.match(shell, /Phase 5/);
  assert.match(shell, /Phase 6/);
  assert.doesNotMatch(shell, /mock/i);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
  assert.match(legacyRoute, /redirect/);
  assert.match(legacyRoute, /\/demo\/projects\/demo-project\/guide/);
  assert.doesNotMatch(legacyRoute, /mock/i);
  assert.match(nav, /\/guide/);
  assert.match(nav, /Guide/);
});

test("Next app shell declares tenant/project Story Graph route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/graph/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getStoryGraphCurrent/);
  assert.match(page, /startStoryGraphBuild/);
  assert.match(page, /startStoryGraphBondGeneration/);
  assert.match(page, /buildAction/);
  assert.match(page, /bondAction/);
  assert.match(page, /StoryGraphShell/);
  assert.match(nav, /\/graph/);
  assert.match(nav, /Story Graph/);
});

test("writer API client uses Go API base URL and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /MIROFISH_API_BASE_URL/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.match(client, /\/v1\/projects\/\$\{(?:input\.)?projectId\}\/writer-runs/);
  assert.match(client, /trace_id/);
  assert.doesNotMatch(client, /tenant_id\s*:/);
});

test("asset API client uses sanitized Go asset endpoints and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getProjectAssets/);
  assert.match(client, /getAssetFacets/);
  assert.match(client, /tags:\s*AssetFacetBucket\[\]/);
  assert.match(client, /tags:\s*arrayFromUnknown\(payload\.tags\)/);
  assert.match(client, /searchAssets/);
  assert.match(client, /getArchiveAssetMemories/);
  assert.match(client, /getArchiveAssetMemoryEvents/);
  assert.match(client, /adoptArchiveMemory/);
  assert.match(client, /rejectArchiveMemory/);
  assert.match(client, /ArchiveMemoryRecord/);
  assert.match(client, /createAsset/);
  assert.match(client, /updateAsset/);
  assert.match(client, /deleteAsset/);
  assert.match(client, /adoptAsset/);
  assert.match(client, /bulkActionAssets/);
  assert.match(client, /startAssetIngestion/);
  assert.match(client, /startAssetReindex/);
  assert.match(client, /startStyleExtraction/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/assets`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/assets\/facets`/);
  assert.match(client, /\/v1\/assets\/search`/);
  assert.match(client, /\/v1\/archive-assets\/\$\{input\.assetId\}\/memories/);
  assert.match(client, /\/v1\/archive-assets\/\$\{input\.assetId\}\/memory-events/);
  assert.match(client, /\/v1\/archive-memories\/\$\{input\.memoryId\}\/adoptions`/);
  assert.match(client, /\/v1\/archive-memories\/\$\{input\.memoryId\}\/rejections`/);
  assert.match(client, /project_id/);
  assert.match(client, /\/v1\/assets\/\$\{input\.assetId\}`/);
  assert.match(client, /\/v1\/assets\/\$\{input\.assetId\}\/adoptions`/);
  assert.match(client, /\/v1\/assets\/bulk-actions`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/assets\/reindex`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/asset-ingestions`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/style-extractions`/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.match(client, /content_text/);
  assert.match(client, /target_lifecycle/);
  assert.match(client, /asset_ids/);
  assert.doesNotMatch(client, /body:\s*string/);
  assert.doesNotMatch(client, /requiredString\(value,\s*"body"\)/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("Story Graph API client uses sanitized Go story graph endpoints and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getStoryGraphCurrent/);
  assert.match(client, /getStoryGraphView/);
  assert.match(client, /getStoryGraphEvidence/);
  assert.match(client, /getStoryGraphLayout/);
  assert.match(client, /getStoryGraphClusters/);
  assert.match(client, /startStoryGraphBuild/);
  assert.match(client, /startStoryGraphBondGeneration/);
  assert.match(client, /getWorkflowRunSummary/);
  assert.match(client, /getWorkflowRunEvents/);
  assert.match(client, /WorkflowRunSummary/);
  assert.match(client, /WorkflowRunEventsSummary/);
  assert.match(client, /StoryGraphCurrentSummary/);
  assert.match(client, /StoryGraphViewSummary/);
  assert.match(client, /StoryGraphEvidenceSummary/);
  assert.match(client, /StoryGraphLayoutSummary/);
  assert.match(client, /StoryGraphClustersSummary/);
  assert.match(client, /StoryGraphBuildSummary/);
  assert.match(client, /StoryGraphBondGenerationSummary/);
  assert.match(client, /\/v1\/workflow-runs\/\$\{input\.runId\}`/);
  assert.match(client, /\/v1\/workflow-runs\/\$\{input\.runId\}\/events/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/current`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/views\/\$\{input\.viewId\}`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/\$\{input\.ownerType\}s\/\$\{input\.ownerId\}\/evidence`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/layouts\/\$\{input\.viewId\}`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/clusters`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/builds`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/bond-generations`/);
  assert.match(client, /workflow_type/);
  assert.match(client, /graph_id/);
  assert.match(client, /node_ids/);
  assert.match(client, /node_count/);
  assert.match(client, /edge_count/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(client, /snippet:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("Story Graph shell renders explicit snapshot and build states", async () => {
  const shell = await fileText("components/story-graph-shell.tsx");

  assert.match(shell, /Story Graph/);
  assert.match(shell, /Current Snapshot/);
  assert.match(shell, /Graph canvas/);
  assert.match(shell, /Viewport/);
  assert.match(shell, /Evidence/);
  assert.match(shell, /Layout/);
  assert.match(shell, /Clusters/);
  assert.match(shell, /Build progress/);
  assert.match(shell, /Workflow events/);
  assert.match(shell, /Compose Mode/);
  assert.match(shell, /Generate bonds/);
  assert.match(shell, /bondAction/);
  assert.match(shell, /bondStatus/);
  assert.match(shell, /storyGraphBondStatus/);
  assert.match(shell, /workflowRun\.ok/);
  assert.match(shell, /workflowEvents\.ok/);
  assert.match(shell, /event\.event_type/);
  assert.match(shell, /No build run selected/);
  assert.match(shell, /view\.ok/);
  assert.match(shell, /evidence\.ok/);
  assert.match(shell, /layout\.ok/);
  assert.match(shell, /clusters\.ok/);
  assert.match(shell, /node\.node_id/);
  assert.match(shell, /edge\.edge_id/);
  assert.match(shell, /Start build/);
  assert.match(shell, /current\.ok/);
  assert.match(shell, /node_count/);
  assert.match(shell, /edge_count/);
  assert.match(shell, /storyGraphBuildStatus/);
  assert.doesNotMatch(shell, /mock/i);
});

test("Story Graph page loads workflow progress when a build run id is present", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/graph/page.tsx");

  assert.match(page, /runId\?:\s*string/);
  assert.match(page, /bondStatus\?:\s*string/);
  assert.match(page, /bondRunId\?:\s*string/);
  assert.match(page, /getWorkflowRunSummary/);
  assert.match(page, /getWorkflowRunEvents/);
  assert.match(page, /selectedRunId/);
  assert.match(page, /selectedRunId\s*\?\s*await getWorkflowRunSummary/);
  assert.match(page, /selectedRunId\s*\?\s*await getWorkflowRunEvents/);
  assert.match(page, /query\.runId\s*\?\?\s*""/);
  assert.match(page, /query\.bondRunId\s*\?\?\s*""/);
  assert.match(page, /runId:\s*status\.runId/);
});

test("Asset Library shell renders explicit archive memory review controls", async () => {
  const shell = await fileText("components/asset-library-shell.tsx");

  assert.match(shell, /Archive Memory/);
  assert.match(shell, /Memory review/);
  assert.match(shell, /archiveMemories/);
  assert.match(shell, /archiveMemoryEvents/);
  assert.match(shell, /memoryAssetAction/);
  assert.match(shell, /adoptArchiveMemoryAction/);
  assert.match(shell, /rejectArchiveMemoryAction/);
  assert.match(shell, /No archive asset selected/);
  assert.match(shell, /Adopt memory/);
  assert.match(shell, /Reject memory/);
});

test("writer API client reads and exports agent traces through audited Go endpoints", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getAgentTraceEvents/);
  assert.match(client, /exportAgentTrace/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/agent-traces\/\$\{input\.traceId\}\/events/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/agent-traces\/\$\{input\.traceId\}\/export/);
  assert.match(client, /include_full/);
});

test("writer API client can replay workflow events after a resume cursor", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getWriterRunEvents/);
  assert.match(client, /after_event_id/);
  assert.match(client, /\/v1\/writer-runs\/\$\{input\.runId\}\/events/);
});

test("Writer shell exposes recovered stream replay cursor without sensitive content", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");
  const replaySlice = sourceSlice(shell, "Recovered stream", "Trace Events");

  assert.match(page, /const\s+afterEventId\s*=\s*query\.after_event_id\s*\?\?\s*query\.afterEventId\s*\?\?\s*""/);
  assert.match(page, /const\s+selectedRunId\s*=\s*query\.runId\s*\?\?\s*""/);
  assert.match(page, /const\s+selectedTraceId\s*=\s*query\.traceId\s*\?\?\s*""/);
  assert.match(page, /afterEventId:\s*afterEventId/);
  assert.match(page, /selectedRunId=\{selectedRunId\}/);
  assert.match(page, /selectedTraceId=\{selectedTraceId\}/);
  assert.match(page, /afterEventId=\{afterEventId\}/);
  assert.match(shell, /afterEventId:\s*string/);
  assert.match(shell, /selectedRunId:\s*string/);
  assert.match(shell, /selectedTraceId:\s*string/);
  assert.match(shell, /const\s+replayRunId\s*=\s*runSummary\?\.ok === true \? runSummary\.run_id : selectedRunId/);
  assert.match(shell, /const\s+replayTraceId\s*=\s*selectedTraceId \|\| traceId/);
  assert.match(shell, /<dd>\{replayRunId \|\| "not selected"\}<\/dd>/);
  assert.match(shell, /<dd>\{replayTraceId \|\| "not selected"\}<\/dd>/);
  assert.match(shell, /value=\{replayTraceId\}/);
  assert.match(replaySlice, /action=\{writerHref\(tenantSlug,\s*projectId\)\}/);
  assert.match(replaySlice, /method="get"/);
  assert.match(replaySlice, /name="runId"/);
  assert.match(replaySlice, /value=\{runSummary\?\.ok === true \? runSummary\.run_id : selectedRunId\}/);
  assert.match(replaySlice, /name="traceId"/);
  assert.match(replaySlice, /value=\{selectedTraceId \|\| traceId\}/);
  assert.match(replaySlice, /name="after_event_id"/);
  assert.match(replaySlice, /defaultValue=\{afterEventId\}/);
  assert.match(replaySlice, /Request replay events/);
  assert.match(replaySlice, /Event cursor/);
  assert.doesNotMatch(shell, /JSON\.stringify\(event\.payload/);
  assert.doesNotMatch(replaySlice, /api_key|encrypted_api_key|credential_ref/i);
  assert.doesNotMatch(replaySlice, /content_text|body_text|draft|manuscript/i);
});

test("writer API client reads sanitized worldline saved path picker data", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /WorldlineSavedPathRecord/);
  assert.match(client, /WorldlineSavedPathsSummary/);
  assert.match(client, /WorldlineSessionRecord/);
  assert.match(client, /WorldlineSessionsSummary/);
  assert.match(client, /WorldlineSessionStartSummary/);
  assert.match(client, /WorldlineTimelineEventRecord/);
  assert.match(client, /WorldlineTimelineSummary/);
  assert.match(client, /WorldlineVariableRecord/);
  assert.match(client, /WorldlineVariableSummary/);
  assert.match(client, /getWorldlineSavedPaths/);
  assert.match(client, /getWorldlineSessions/);
  assert.match(client, /getWorldlineSession/);
  assert.match(client, /getWorldlineTimeline/);
  assert.match(client, /startWorldlineSession/);
  assert.match(client, /startWorldlineStep/);
  assert.match(client, /injectWorldlineVariable/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldline\/saved-paths`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldline-sessions`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/timeline`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/steps`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/variables`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldline-sessions`/);
  assert.match(client, /anchor_path_id/);
  assert.match(client, /goal_summary/);
  assert.match(client, /workflow_type/);
  assert.match(client, /selected_event_ids/);
  assert.match(client, /writer_instruction/);
  assert.match(client, /X-Tenant-Id/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /content_text:\s*string/);
  assert.doesNotMatch(client, /body_text:\s*string/);
});

test("LLM Facility API client reads sanitized module resolution, activity, and usage", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /createLLMChannel/);
  assert.match(client, /updateLLMChannel/);
  assert.match(client, /deleteLLMChannel/);
  assert.match(client, /syncLLMChannelModels/);
  assert.match(client, /getLLMSettings/);
  assert.match(client, /deleteLLMModuleBinding/);
  assert.match(client, /getLLMModuleBindings/);
  assert.match(client, /getLLMModules/);
  assert.match(client, /getLLMChannels/);
  assert.match(client, /getLLMChannelModels/);
  assert.match(client, /upsertLLMModuleBinding/);
  assert.match(client, /resolveLLMModuleBinding/);
  assert.match(client, /getLLMActivity/);
  assert.match(client, /getLLMUsage/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/channels`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/channels\/\$\{input\.channelId\}\/models`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/modules`/);
  assert.match(client, /\/v1\/llm\/channels`/);
  assert.match(client, /\/v1\/llm\/settings`/);
  assert.match(client, /\/v1\/llm\/channels\/\$\{input\.channelId\}`/);
  assert.match(client, /\/v1\/llm\/channels\/\$\{input\.channelId\}\/sync-models`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/module-bindings`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/module-bindings\/\$\{input\.moduleKey\}`/);
  assert.match(client, /method:\s*"DELETE"/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/module-bindings\/\$\{input\.moduleKey\}\/resolution/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/activity/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/usage/);
  assert.match(client, /module_key/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
});

test("writer page loads redacted trace events when a run exposes trace_id", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");

  assert.match(page, /getAgentTraceEvents/);
  assert.match(page, /exportAgentTrace/);
  assert.match(page, /getWriterRunEvents/);
  assert.match(page, /startWriterRun/);
  assert.match(page, /getProjectAssets/);
  assert.match(page, /getStoryGraphView/);
  assert.match(page, /getWorldlineSavedPaths/);
  assert.match(page, /startWriterRunAction/);
  assert.match(page, /selectedAssetIds/);
  assert.match(page, /selectedGraphNodeIds/);
  assert.match(page, /worldlinePathIds/);
  assert.match(page, /worldlineSavedPaths/);
  assert.match(page, /selected_asset_ids/);
  assert.match(page, /graph_node_ids/);
  assert.match(page, /worldline_path_ids/);
  assert.match(page, /exportTraceAction/);
  assert.match(page, /includeFull:\s*false/);
  assert.match(page, /runSummary\.ok\s*===\s*true\s*\?\s*runSummary\.trace_id/);
  assert.match(page, /runSummary\.ok\s*===\s*true\s*\?\s*await getWriterRunEvents/);
});

test("writer shell is an operational workbench, not a marketing page", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");

  assert.match(shell, /Writer Run/);
  assert.match(shell, /Writer Events/);
  assert.match(shell, /workflowEvents/);
  assert.match(shell, /Trace/);
  assert.match(shell, /Export redacted trace/);
  assert.match(shell, /exportTraceAction/);
  assert.match(shell, /traceExportStatus/);
  assert.match(shell, /Command Row/);
  assert.match(shell, /Start writer run/);
  assert.match(shell, /Context pickers/);
  assert.match(shell, /Project assets/);
  assert.match(shell, /Graph nodes/);
  assert.match(shell, /Worldline paths/);
  assert.match(shell, /ReferenceWorldlinePaths/);
  assert.match(shell, /worldlineSavedPaths\.ok/);
  assert.match(shell, /writerRunAction/);
  assert.match(shell, /assets\.ok/);
  assert.match(shell, /graphView\.ok/);
  assert.match(shell, /name="selectedAssetIds"/);
  assert.match(shell, /name="selectedGraphNodeIds"/);
  assert.match(shell, /name="worldlinePathIds"/);
  assert.match(shell, /path\.path_id/);
  assert.match(shell, /selected_event_ids/);
  assert.match(shell, /name="instruction"/);
  assert.match(shell, /name="traceId"/);
  assert.match(shell, /redaction_level/);
  assert.match(shell, /event_type/);
  assert.match(shell, /Draft/);
  assert.doesNotMatch(shell, /credential_ref/);
  assert.doesNotMatch(shell, /hero/i);
  assert.doesNotMatch(shell, /Start trial/i);
});

test("writer shell renders typed tool result cards from completed writer events", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");

  assert.match(shell, /Tool result cards/);
  assert.match(shell, /ToolResultCards/);
  assert.match(shell, /ToolResultCard/);
  assert.match(shell, /AssetToolResultCard/);
  assert.match(shell, /GraphToolResultCard/);
  assert.match(shell, /WorldlinePathToolResultCard/);
  assert.match(shell, /writer\.tool\.completed/);
  assert.match(shell, /tool_name/);
  assert.match(shell, /query_assets/);
  assert.match(shell, /query_graph_neighbors/);
  assert.match(shell, /query_worldline_paths/);
  assert.match(shell, /is_error/);
  assert.match(shell, /asset_id/);
  assert.match(shell, /neighbor/);
  assert.match(shell, /path_id/);
  assert.match(shell, /selected_event_ids/);
  assert.match(shell, /UnknownToolResultCard/);
  assert.match(shell, /tool-result-grid/);
  assert.doesNotMatch(shell, /credential_ref/);
});

test("LLM Facility shell is an operational settings console", async () => {
  const shell = await fileText("components/llm-facility-shell.tsx");

  assert.match(shell, /LLM Facility/);
  assert.match(shell, /Tenant Settings/);
  assert.match(shell, /settingsSnapshot/);
  assert.match(shell, /Channels/);
  assert.match(shell, /Channel Management/);
  assert.match(shell, /Create channel/);
  assert.match(shell, /Update channel/);
  assert.match(shell, /name="apiKey"/);
  assert.match(shell, /updateChannelAction/);
  assert.match(shell, /deleteChannelAction/);
  assert.match(shell, /syncChannelAction/);
  assert.match(shell, /Sync models/);
  assert.match(shell, /last_sync_status/);
  assert.match(shell, /Models/);
  assert.match(shell, /Project Binding/);
  assert.match(shell, /Bind module/);
  assert.match(shell, /Clear override/);
  assert.match(shell, /clearBindingAction/);
  assert.match(shell, /name="channelId"/);
  assert.match(shell, /name="modelId"/);
  assert.match(shell, /name="moduleKey"/);
  assert.match(shell, /name="moduleMaxConcurrency"/);
  assert.match(shell, /Module max concurrency/);
  assert.match(shell, /bindingStatus/);
  assert.match(shell, /Module binding/);
  assert.match(shell, /Module Bindings/);
  assert.match(shell, /Module Catalog/);
  assert.match(shell, /modules\.items\.map/);
  assert.match(shell, /Activity/);
  assert.match(shell, /Usage/);
  assert.match(shell, /Telemetry filter/);
  assert.match(shell, /name="runId"/);
  assert.match(shell, /Filter telemetry/);
  assert.match(shell, /writer_composer/);
  assert.doesNotMatch(shell, /api_key/);
  assert.doesNotMatch(shell, /hero/i);
});

test("Asset Library shell is an operational asset console", async () => {
  const shell = await fileText("components/asset-library-shell.tsx");

  assert.match(shell, /Asset Library/);
  assert.match(shell, /Facets/);
  assert.match(shell, /FacetGroup label="Tags"/);
  assert.match(shell, /Search/);
  assert.match(shell, /Versions:/);
  assert.match(shell, /Collections:/);
  assert.match(shell, /Assets/);
  assert.match(shell, /Create asset/);
  assert.match(shell, /Update asset/);
  assert.match(shell, /Delete asset/);
  assert.match(shell, /Adopt candidate/);
  assert.match(shell, /Bulk action/);
  assert.match(shell, /Ingest material/);
  assert.match(shell, /Reindex assets/);
  assert.match(shell, /Extract style/);
  assert.match(shell, /createAssetAction/);
  assert.match(shell, /updateAssetAction/);
  assert.match(shell, /deleteAssetAction/);
  assert.match(shell, /adoptAssetAction/);
  assert.match(shell, /bulkAssetAction/);
  assert.match(shell, /ingestAssetAction/);
  assert.match(shell, /reindexAssetsAction/);
  assert.match(shell, /extractStyleAction/);
  assert.match(shell, /name="contentText"/);
  assert.match(shell, /name="targetLifecycle"/);
  assert.match(shell, /name="assetIds"/);
  assert.match(shell, /name="bulkAction"/);
  assert.match(shell, /bulkStatus/);
  assert.match(shell, /assetStatus/);
  assert.match(shell, /ingestionStatus/);
  assert.match(shell, /reindexStatus/);
  assert.match(shell, /styleStatus/);
  assert.doesNotMatch(shell, /item\.body/);
  assert.doesNotMatch(shell, /api_key/);
  assert.doesNotMatch(shell, /credential_ref/);
  assert.doesNotMatch(shell, /hero/i);
});

test("asset search client decodes version and collection metadata", async () => {
  const api = await fileText("lib/api.ts");

  assert.match(api, /type AssetSearchVersion/);
  assert.match(api, /type AssetSearchCollection/);
  assert.match(api, /version: decodeAssetSearchVersion/);
  assert.match(api, /collections: arrayFromUnknown\(value\.collections\)\.map\(\(collection\) => decodeAssetSearchCollection\(collection\)\)/);
  assert.doesNotMatch(api, /body:\s*string/);
  assert.doesNotMatch(api, /requiredString\(value,\s*"body"\)/);
});

test("global styles avoid one-note purple, cream, and dark-slate dominance", async () => {
  const css = await fileText("app/globals.css");

  assert.match(css, /--surface/);
  assert.match(css, /--accent/);
  assert.doesNotMatch(css, /#fffbeb/i);
  assert.doesNotMatch(css, /#0f172a/i);
  assert.doesNotMatch(css, /purple|violet/i);
});

test("project app frame collapses to one column on mobile", async () => {
  const css = await fileText("app/globals.css");

  assert.match(css, /\.panel\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /@media\s*\(max-width:\s*860px\)/);
  assert.match(css, /\.app-frame\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(css, /\.app-main\s*\{[^}]*padding:\s*16px/s);
  assert.match(css, /\.app-sidebar\s*\{[^}]*border-right:\s*0/s);
});

test("trace JSON blocks stay inside mobile workbench panels", async () => {
  const css = await fileText("app/globals.css");

  assert.match(css, /\.trace-list\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.trace-event\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.trace-event\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.trace-event-header\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /\.trace-event pre\s*\{[^}]*max-width:\s*100%/s);
  assert.match(css, /\.trace-event pre\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.trace-event pre\s*\{[^}]*width:\s*100%/s);
});
