import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  agentRefsFromFormData,
  journeyRefsFromFormData,
  parseCharacterAnchorRef,
  parseJourneyRef,
  positiveBoundedInteger,
  selectCurrentWorldSession,
} from "../lib/worldline-character-journey.ts";

test("journey helpers preserve typed refs and reject malformed or unsupported refs", () => {
  assert.deepEqual(parseJourneyRef("worldline_event:event-1"), {
    source_kind: "worldline_event",
    source_id: "event-1",
  });
  assert.equal(parseJourneyRef("branch:legacy"), null);
  assert.equal(parseJourneyRef("asset:"), null);

  const form = new FormData();
  form.append("agentRefs", "asset:asset-1");
  form.append("agentRefs", "entity:entity-1");
  form.append("agentRefs", "saved_path:path-1");
  form.append("sourceRefs", "saved_path:path-1");
  form.append("sourceRefs", "worldline_event:event-1");
  form.append("sourceRefs", "worldline_event:event-1");
  assert.deepEqual(agentRefsFromFormData(form, "agentRefs"), [
    { source_kind: "asset", source_id: "asset-1" },
    { source_kind: "entity", source_id: "entity-1" },
  ]);
  assert.deepEqual(journeyRefsFromFormData(form, "sourceRefs"), [
    { source_kind: "saved_path", source_id: "path-1" },
    { source_kind: "worldline_event", source_id: "event-1" },
  ]);
  assert.deepEqual(parseCharacterAnchorRef("entity:entity-1"), {
    anchorType: "graph_node",
    anchorId: "entity-1",
  });
});

test("current world selection uses only active lifecycle and honors an explicit active session", () => {
  const sessions = {
    ok: true,
    items: [
      session("newest-archived", "archived"),
      session("active-a", "active"),
      session("active-b", "active"),
    ],
  };
  assert.equal(selectCurrentWorldSession(sessions, "active-b")?.session_id, "active-b");
  assert.equal(selectCurrentWorldSession(sessions, "newest-archived")?.session_id, "active-a");
  assert.equal(selectCurrentWorldSession({ ok: true, items: [session("done", "archived")] }, ""), undefined);
  assert.equal(positiveBoundedInteger("5", 3, 50), 5);
  assert.equal(positiveBoundedInteger("51", 3, 50), 3);
});

test("Worldline and Character journey surfaces wire explicit adoption, auto evolution, replay, and writer candidate metadata", async () => {
  const [worldlinePage, worldlineShell, characterPage, characterShell] = await Promise.all([
    source("app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx"),
    source("components/worldline-shell.tsx"),
    source("app/(app)/[tenantSlug]/projects/[projectId]/character-console/page.tsx"),
    source("components/character-console-shell.tsx"),
  ]);
  assert.match(worldlinePage, /startWorldlineAutoEvolution/);
  assert.match(worldlinePage, /agentRefsFromFormData/);
  assert.match(worldlinePage, /journeyRefsFromFormData/);
  assert.match(worldlinePage, /events, pathEvents/);
  assert.match(worldlinePage, /pathEvents=\{pathEvents\}/);
  assert.match(
    worldlinePage,
    /getWorldlineEvents\(\{\s*\.\.\.apiContext,\s*sessionId: selectedSessionId,\s*\}\)/,
  );
  assert.doesNotMatch(worldlinePage, /sessions\.items\[0\]\.session_id/);
  assert.match(worldlineShell, /name="agentRefs"/);
  assert.match(worldlineShell, /name="sourceRefs"/);
  assert.match(worldlineShell, /Refresh preparation and roster/);
  assert.match(worldlineShell, /Enter Characters/);
  assert.match(worldlineShell, /character-console\?/);
  assert.match(worldlineShell, /prepare_id/);
  assert.match(worldlinePage, /prepare_id/);
  assert.match(characterPage, /listWorldlinePreparations/);
  assert.match(characterShell, /WorldlinePreparationSelector/);
  assert.match(worldlineShell, /name="maxSteps"/);
  assert.match(worldlineShell, /adoptWorldlineEventAction/);
  assert.match(worldlineShell, /pathEvents\.items\.map/);
  assert.match(characterPage, /startCharacterDialogue/);
  assert.match(characterPage, /runtime_run_id/);
  assert.match(characterShell, /name="anchorRef"/);
  assert.match(characterShell, /Turn replay/);
  assert.match(characterShell, /proposal\.proposal_type/);
  assert.match(characterShell, /proposal\.lifecycle === "candidate"/);
  assert.match(characterShell, /Request chapter draft/);
  assert.match(characterShell, /View in Writer/);
  assert.match(characterShell, /writerRunHref/);
});

function session(sessionId, lifecycle) {
  return {
    session_id: sessionId,
    run_id: "run",
    project_id: "project",
    status: "paused",
    lifecycle,
    goal_summary: "goal",
    anchor_path_id: "",
    created_by: "user",
    created_at: "2026-07-10T00:00:00Z",
    updated_at: "2026-07-10T00:00:00Z",
  };
}

function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8");
}
