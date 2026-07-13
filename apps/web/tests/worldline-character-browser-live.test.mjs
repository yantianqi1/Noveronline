import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import {
  addJourneySession,
  apiContext,
  assertPrivacyClean,
  assertResponsiveSurface,
  attachPrivacyScanner,
  authenticateJourney,
  hasJourneyConfig,
  loadJourneyConfig,
  projectUrl,
  scanPage,
  waitUntil,
} from "./worldline-character-live-harness.mjs";

const journeyTest = hasJourneyConfig() ? test : test.skip;

journeyTest("Worldline and Character complete the authenticated current-world product journey", async () => {
  const config = loadJourneyConfig();
  process.env.MIROFISH_API_BASE_URL = config.apiBaseUrl;
  const api = await import(`../lib/api.ts?worldlineCharacterLive=${Date.now()}`);
  const auth = await authenticateJourney(api, config);
  const contextInput = apiContext(config, auth);
  const manuscriptBefore = await api.getProjectManuscript(contextInput);
  assert.equal(manuscriptBefore.ok, true, "cannot establish the zero-manuscript baseline");

  const { chromium } = await import("@playwright/test");
  const browser = await chromium.launch({ headless: true });
  const screenshots = {
    worldlineDesktop: path.join(config.screenshotDir, "worldline-1440.png"),
    worldlineMobile: path.join(config.screenshotDir, "worldline-375.png"),
    characterDesktop: path.join(config.screenshotDir, "character-1440.png"),
    characterMobile: path.join(config.screenshotDir, "character-375.png"),
  };
  await mkdir(config.screenshotDir, { recursive: true });
  const findings = [];

  try {
    const browserContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await addJourneySession(browserContext, config, auth);
    const page = await browserContext.newPage();
    page.setDefaultNavigationTimeout(config.timeoutMs);
    page.setDefaultTimeout(config.timeoutMs);
    attachPrivacyScanner(page, findings);

    await page.goto(projectUrl(config, "worldline"), { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Worldline", exact: true }).waitFor();
    journeyStage("worldline loaded");
    const session = await ensureCurrentWorld(page, api, config, contextInput);
    journeyStage("current world selected");
    const preparation = await prepareRoster(page, api, config, contextInput);
    journeyStage("preparation completed");
    const firstCandidate = await evolveAndAdopt(page, api, config, contextInput, session.session_id);
    journeyStage("worldline candidate adopted");
    const savedPathId = await savePath(page, api, config, contextInput, session.session_id, firstCandidate.event_id);
    journeyStage("worldline path saved");

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Prepared agents" }).locator("..").getByText(preparation.prepare_id, { exact: false }).first().waitFor({ timeout: 5_000 }).catch(() => {});
    await scanPage(page, findings);
    await assertResponsiveSurface(page, 1440, 1000, screenshots.worldlineDesktop);
    await assertResponsiveSurface(page, 375, 812, screenshots.worldlineMobile);

    const character = await runCharacterJourney(page, api, config, contextInput, {
      prepareId: preparation.prepare_id,
      sessionId: session.session_id,
      savedPathId,
    });
    journeyStage("character and writer handoff completed");
    await scanPage(page, findings);
    await assertResponsiveSurface(page, 1440, 1000, screenshots.characterDesktop);
    await assertResponsiveSurface(page, 375, 812, screenshots.characterMobile);

    await page.reload({ waitUntil: "domcontentloaded" });
    assert.equal(new URL(page.url()).searchParams.get("selected_interaction_id"), character.interactionId);
    assert.equal(new URL(page.url()).searchParams.get("runtime_run_id"), character.writerRunId);
    const replay = await api.listCharacterInteractionTurns({ ...contextInput, interactionId: character.interactionId });
    assert.equal(replay.ok, true);
    assert.ok(replay.items.length >= 4, "two dialogue rounds were not recoverable after refresh");

    const manuscriptAfter = await api.getProjectManuscript(contextInput);
    assert.equal(manuscriptAfter.ok, true);
    assert.equal(manuscriptAfter.blocks.length, manuscriptBefore.blocks.length, "Character handoff auto-created manuscript blocks");
    assertPrivacyClean(findings);
  } finally {
    await browser.close();
  }
});

async function ensureCurrentWorld(page, api, config, contextInput) {
  const existing = await api.getWorldlineSessions(contextInput);
  assert.equal(existing.ok, true);
  const active = existing.items.find((item) => item.lifecycle === "active");
  if (active) return active;
  const panel = page.getByRole("heading", { name: "Start session" }).locator("..");
  const goal = `Browser current world ${Date.now()}`;
  await panel.getByLabel("Goal").fill(goal);
  await submitServerAction(page, panel.getByRole("button", { name: "Start session" }), "worldlineSessionStatus", Boolean, config.timeoutMs);
  assertQueryStatus(page, "worldlineSessionStatus", "success");
  return waitUntil(
    () => api.getWorldlineSessions(contextInput),
    (result) => result.ok && result.items.some((item) => item.lifecycle === "active" && item.goal_summary.includes("Browser current world")),
    config,
    "active current_world session",
  ).then((result) => result.items.find((item) => item.lifecycle === "active" && item.goal_summary.includes("Browser current world")));
}

async function prepareRoster(page, api, config, contextInput) {
  await page.goto(projectUrl(config, "worldline"), { waitUntil: "domcontentloaded" });
  const panel = page.getByRole("heading", { name: "Prepare agents" }).locator("..");
  await panel.getByLabel("Goal").fill("Prepare the selected character for a two-round negotiation");
  const agentRefs = panel.locator('input[name="agentRefs"]');
  assert.ok(await agentRefs.count() > 0, "no real Asset or Entity is selectable for preparation");
  await agentRefs.first().check();
  const sourceRefs = panel.locator('input[name="sourceRefs"]');
  if (await sourceRefs.count()) await sourceRefs.first().check();
  await submitServerAction(page, panel.getByRole("button", { name: "Prepare agents" }), "worldlinePreparationPrepareId", Boolean, config.timeoutMs);
  const prepareId = new URL(page.url()).searchParams.get("worldlinePreparationPrepareId");
  assert.ok(prepareId);
  const preparation = await waitUntil(
    () => api.getWorldlinePreparation({ ...contextInput, prepareId }),
    (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
    config,
    "worldline preparation",
  );
  assert.equal(
    preparation.status,
    "completed",
    `preparation failed with ${preparation.status}: ${preparation.error_code || "UNKNOWN"} ${preparation.error_message || ""}`.trim(),
  );
  const roster = await api.getWorldlinePreparedAgents({ ...contextInput, prepareId });
  assert.equal(roster.ok, true);
  assert.ok(roster.items.length > 0, "completed preparation has an empty roster");
  return preparation;
}

async function evolveAndAdopt(page, api, config, contextInput, sessionId) {
  await page.goto(projectUrl(config, "worldline", { selectedSessionId: sessionId }), { waitUntil: "domcontentloaded" });
  const beforeStep = await api.getWorldlineEvents({ ...contextInput, sessionId, status: "candidate" });
  assert.equal(beforeStep.ok, true);
  const stepPanel = page.getByRole("heading", { name: "Step session" }).locator("..");
  await submitServerAction(page, stepPanel.getByRole("button", { name: "Step session" }), "worldlineStepStatus", Boolean, config.timeoutMs);
  assertQueryStatus(page, "worldlineStepStatus", "success");
  await waitForCompletedRun(api, config, contextInput, new URL(page.url()).searchParams.get("worldlineStepRunId"), "worldline step");
  await waitForCandidate(api, config, contextInput, sessionId, beforeStep.items.length + 1);
  journeyStage("worldline step completed");

  await page.goto(projectUrl(config, "worldline", { selectedSessionId: sessionId }), { waitUntil: "domcontentloaded" });
  const beforeAuto = await api.getWorldlineEvents({ ...contextInput, sessionId, status: "candidate" });
  assert.equal(beforeAuto.ok, true);
  const autoPanel = page.getByRole("heading", { name: "Evolve current world" }).locator("..");
  await autoPanel.getByLabel("Maximum steps").fill("2");
  await submitServerAction(page, autoPanel.getByRole("button", { name: "Start auto evolution" }), "worldlineAutoStatus", Boolean, config.timeoutMs);
  assertQueryStatus(page, "worldlineAutoStatus", "success");
  await waitForCompletedRun(api, config, contextInput, new URL(page.url()).searchParams.get("worldlineAutoRunId"), "worldline auto evolution");
  const candidates = await waitForCandidate(api, config, contextInput, sessionId, beforeAuto.items.length + 1);
  journeyStage("worldline auto evolution completed");

  await page.goto(projectUrl(config, "worldline", { selectedSessionId: sessionId }), { waitUntil: "domcontentloaded" });
  const adoption = page.getByRole("heading", { name: "Adopt event" }).locator("..");
  await adoption.getByLabel("Candidate event").selectOption(candidates[0].event_id);
  await submitServerAction(page, adoption.getByRole("button", { name: "Adopt event" }), "worldlineEventAdoptionStatus", Boolean, config.timeoutMs);
  assertQueryStatus(page, "worldlineEventAdoptionStatus", "success");
  return candidates[0];
}

async function waitForCompletedRun(api, config, contextInput, runId, label) {
  assert.ok(runId, `${label} redirect omitted run_id`);
  journeyStage(`${label} admitted ${runId}`);
  const run = await waitUntil(
    () => api.getWorkflowRunSummary({ ...contextInput, runId }),
    (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
    config,
    label,
  );
  assert.equal(run.status, "completed", `${label} failed with ${run.status}`);
}

async function waitForCandidate(api, config, contextInput, sessionId, minimum) {
  const result = await waitUntil(
    () => api.getWorldlineEvents({ ...contextInput, sessionId, status: "candidate" }),
    (value) => value.ok && value.items.length >= minimum,
    config,
    `${minimum} current-world candidate events`,
  );
  assert.ok(
    result.items.every((event) => event.status === "candidate" && event.lifecycle === "simulation"),
    "worldline candidate left simulation without explicit adoption",
  );
  return result.items;
}

function assertQueryStatus(page, key, expected) {
  const query = new URL(page.url()).searchParams;
  const actual = query.get(key);
  const code = query.get(key.replace(/Status$/, "Code"));
  assert.equal(actual, expected, `${key}=${actual ?? "missing"}; code=${code ?? "missing"}`);
}

async function savePath(page, api, config, contextInput, sessionId, eventId) {
  await page.goto(projectUrl(config, "worldline", { selectedSessionId: sessionId }), { waitUntil: "domcontentloaded" });
  const panel = page.getByRole("heading", { name: "Save path" }).locator("..");
  await panel.getByLabel("Title").fill(`Browser saved path ${Date.now()}`);
  await panel.locator(`input[name="selectedEventIds"][value="${eventId}"]`).check();
  await submitServerAction(page, panel.getByRole("button", { name: "Save path" }), "worldlineSavedPathId", Boolean, config.timeoutMs);
  const pathId = new URL(page.url()).searchParams.get("worldlineSavedPathId");
  const paths = await api.getWorldlineSavedPaths(contextInput);
  assert.equal(paths.ok, true);
  assert.ok(paths.items.some((item) => item.path_id === pathId && item.selected_event_ids.includes(eventId)));
  return pathId;
}

async function runCharacterJourney(page, api, config, contextInput, anchors) {
  await page.getByRole("link", { name: "Enter Character Console" }).click();
  await page.waitForURL(/\/character-console/, { waitUntil: "domcontentloaded" });
  const create = page.getByRole("heading", { name: "Create interaction" }).locator("..");
  await create.getByLabel("Worldline session").selectOption(anchors.sessionId);
  await create.getByLabel("Typed anchor").selectOption(`saved_path:${anchors.savedPathId}`);
  await create.getByLabel("POV agent").selectOption({ index: 1 });
  await create.getByLabel("Title").fill(`Browser character journey ${Date.now()}`);
  await submitServerAction(page, create.getByRole("button", { name: "Create interaction" }), "interaction_id", Boolean, config.timeoutMs);
  const interactionId = new URL(page.url()).searchParams.get("interaction_id");
  assert.ok(interactionId);
  await page.goto(projectUrl(config, "character-console", {
    selected_interaction_id: interactionId,
    turns_interaction_id: interactionId,
    runtime_interaction_id: interactionId,
    anchor_session_id: anchors.sessionId,
    prepare_id: anchors.prepareId,
  }), { waitUntil: "domcontentloaded" });

  for (const summary of ["What do you remember about the rain-night pact?", "How will that memory change your next choice?"]) {
    const turn = page.getByRole("heading", { name: "Record turn" }).locator("..");
    await turn.getByLabel("Interaction").selectOption(interactionId);
    await turn.getByLabel("Turn summary").fill(summary);
    await submitServerAction(page, turn.getByRole("button", { name: "Record turn" }), "turn_id", Boolean, config.timeoutMs);
    assertQueryStatus(page, "runtime_status", "success");
    await waitUntil(
      () => api.listCharacterInteractionTurns({ ...contextInput, interactionId }),
      (result) => result.ok && result.items.filter((item) => item.actor_type === "agent").length >= (summary.startsWith("What") ? 1 : 2),
      config,
      "character dialogue response",
    );
    await page.reload({ waitUntil: "domcontentloaded" });
  }

  const currentCSRF = await api.getSessionCSRFToken({ sessionCookie: contextInput.sessionCookie });
  assert.equal(currentCSRF.ok, true, "failed to refresh CSRF before concurrent dialogue");
  const concurrencyContext = { ...contextInput, csrfToken: currentCSRF.csrf_token };
  const concurrentTurns = [];
  for (const summary of ["Concurrent turn A", "Concurrent turn B"]) {
    concurrentTurns.push(await api.appendCharacterInteractionTurn({
      ...concurrencyContext,
      interactionId,
      actorType: "user",
      turnKind: "dialogue",
      summary,
    }));
  }
  assert.ok(concurrentTurns.every((result) => result.ok), "failed to persist concurrent user turns");
  const admissionRequestIds = concurrentTurns.map((_, index) => `browser-dialogue-${Date.now()}-${index}`);
  const concurrentAdmissions = await Promise.all(concurrentTurns.map((turn, index) => startCharacterDialogueWithRequestId(
    config,
    concurrencyContext,
    interactionId,
    turn.turn_id,
    admissionRequestIds[index],
  )));
  const admittedIndex = concurrentAdmissions.findIndex((result) => result.ok);
  const admitted = concurrentAdmissions[admittedIndex];
  const conflict = concurrentAdmissions.find((result) => !result.ok);
  assert.ok(admitted, "no concurrent dialogue request was admitted");
  assert.equal(conflict?.code, "CHARACTER_TURN_ACTIVE", "concurrent dialogue did not expose the active-turn conflict");
  await waitUntil(
    () => api.getWorkflowRunSummary({ ...contextInput, runId: admitted.run_id }),
    (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
    config,
    "concurrent character dialogue",
  );
  const replay = await waitUntil(
    () => startCharacterDialogueWithRequestId(
      config,
      concurrencyContext,
      interactionId,
      concurrentTurns[admittedIndex].turn_id,
      admissionRequestIds[admittedIndex],
    ),
    (result) => result.ok,
    config,
    "character request replay",
  );
  assert.equal(replay.run_id, admitted.run_id, "dialogue replay started a duplicate run");

  const proposals = await waitUntil(
    () => api.getCharacterProposals({ ...contextInput, interactionId }),
    (result) => result.ok && ["memory", "relation", "world_state"].every((type) => result.items.some((item) => item.proposal_type === type && item.lifecycle === "candidate")),
    config,
    "three character proposal types",
  );
  for (const type of ["memory", "relation", "world_state"]) {
    const proposal = proposals.items.find((item) => item.proposal_type === type && item.lifecycle === "candidate");
    await page.goto(projectUrl(config, "character-console", { selected_interaction_id: interactionId, turns_interaction_id: interactionId, runtime_interaction_id: interactionId, anchor_session_id: anchors.sessionId, prepare_id: anchors.prepareId }), { waitUntil: "domcontentloaded" });
    const card = page.locator("article").filter({ hasText: proposal.title }).first();
    await submitServerAction(
      page,
      card.getByRole("button", { name: "Adopt" }),
      "runtime_code",
      (value) => value === "CHARACTER_PROPOSAL_ADOPTED",
      config.timeoutMs,
    );
  }
  const adopted = await api.getCharacterProposals({ ...contextInput, interactionId });
  assert.equal(adopted.ok, true);
  assert.ok(["memory", "relation", "world_state"].every((type) => adopted.items.some((item) => item.proposal_type === type && item.lifecycle !== "candidate")));

  const writer = page.getByRole("heading", { name: "Convert to chapter draft" }).locator("..");
  await writer.getByLabel("Interaction").selectOption(interactionId);
  assert.equal(await writer.getByLabel("Target chapter").inputValue(), "");
  assert.equal(await writer.getByLabel("Target scene").inputValue(), "");
  await submitServerAction(page, writer.getByRole("button", { name: "Request chapter draft" }), "runtime_run_id", Boolean, config.timeoutMs);
  await page.getByRole("link", { name: "View in Writer" }).click();
  await page.waitForURL(/\/writer\?.*runId=/, { waitUntil: "domcontentloaded" });
  const writerRunId = new URL(page.url()).searchParams.get("runId");
  assert.ok(writerRunId);
  const writerRun = await waitUntil(
    () => api.getWriterRunSummary({ ...contextInput, runId: writerRunId }),
    (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
    config,
    "Pi Writer candidate run",
  );
  assert.equal(writerRun.status, "completed", `Pi Writer handoff failed with ${writerRun.status}`);
  await page.getByRole("heading", { name: "Writer", exact: true }).waitFor();
  return { interactionId, writerRunId };
}

async function startCharacterDialogueWithRequestId(config, contextInput, interactionId, userTurnId, requestId) {
  const response = await fetch(`${config.apiBaseUrl}/v1/character-interactions/${encodeURIComponent(interactionId)}/dialogue`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": contextInput.csrfToken,
      "X-Request-Id": requestId,
      "X-Tenant-Id": contextInput.tenantId,
      Cookie: `mirofish_session=${contextInput.sessionCookie}`,
    },
    body: JSON.stringify({ user_turn_id: userTurnId }),
  });
  const payload = await response.json();
  if (response.ok) return { ok: true, ...payload };
  return {
    ok: false,
    code: payload?.error?.code || "CHARACTER_DIALOGUE_START_FAILED",
    message: payload?.error?.message || `HTTP ${response.status}`,
    request_id: payload?.error?.request_id || "",
  };
}

async function submitServerAction(page, button, key, accept, timeoutMs) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.status() >= 300 && response.status() < 400,
    { timeout: timeoutMs },
  );
  const clickPromise = button.click({ noWaitAfter: true });
  const response = await responsePromise;
  await clickPromise;
  const redirectHeader = response.headers().location ?? response.headers()["x-action-redirect"];
  assert.ok(redirectHeader, `${key} server action response is missing a redirect location`);
  const location = redirectHeader.replace(/;(?:push|replace)$/, "");
  const target = new URL(location, page.url());
  assert.equal(accept(target.searchParams.get(key)), true, `${key} redirect did not reach the required value`);
  const reachedTarget = () => accept(new URL(page.url()).searchParams.get(key));
  if (!reachedTarget()) {
    try {
      await page.waitForURL((url) => accept(url.searchParams.get(key)), {
        timeout: Math.min(timeoutMs, 5_000),
        waitUntil: "domcontentloaded",
      });
    } catch (error) {
      if (error?.name !== "TimeoutError") throw error;
      await page.goto(target.href, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("domcontentloaded");
    }
  }
  assert.equal(reachedTarget(), true, `${key} page navigation did not reach the redirect target`);
}

function journeyStage(stage) {
  process.stdout.write(`Worldline/Character journey: ${stage}\n`);
}
