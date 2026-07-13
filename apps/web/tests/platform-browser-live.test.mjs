import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import test from "node:test";
import path from "node:path";
import { chromium } from "playwright";

const prefix = "MIROFISH_WEB_PLATFORM_BROWSER_";
const configured = Object.keys(process.env).some((name) => name.startsWith(prefix));
const browserTest = configured ? test : test.skip;

browserTest("production auth recovery collaboration and LLM admin journey", { timeout: 240_000 }, async () => {
  const config = loadConfig();
  const browser = await chromium.launch({ headless: true });
  const owner = await browser.newContext(contextOptions());
  const invitee = await browser.newContext(contextOptions());
  const anonymous = await browser.newContext(contextOptions());
  const findings = [];
  for (const context of [owner, invitee, anonymous]) {
    await context.addCookies([{ name: "mirofish_locale", value: "en", url: config.appBaseURL, sameSite: "Lax" }]);
  }
  try {
    const recovery = await anonymous.newPage();
    scanRuntime(recovery, findings);
    await recovery.goto(`${config.appBaseURL}/recovery/reset?token=${encodeURIComponent(config.recoveryToken)}`, { waitUntil: "domcontentloaded" });
    await recovery.getByLabel("New password").fill(config.newOwnerPassword);
    await recovery.getByLabel("Confirm password").fill(config.newOwnerPassword);
    await recovery.getByRole("button", { name: "Update password" }).click();
    await recovery.getByText("PASSWORD_RESET_COMPLETE", { exact: true }).waitFor({ timeout: config.timeoutMs });

    await recovery.goto(`${config.appBaseURL}/recovery`, { waitUntil: "domcontentloaded" });
    await recovery.getByLabel("Email").fill(config.ownerEmail);
    await submitAndWait(recovery, recovery.getByRole("button", { name: "Request reset" }), /requested=1/, config.timeoutMs);
    const recoveryStatus = recovery.getByRole("status").filter({ hasText: /reset delivery will be attempted/i });
    try {
      await recoveryStatus.waitFor({ timeout: config.timeoutMs });
    } catch (error) {
      if ((await recovery.locator("body").innerText()).trim()) throw error;
      await recovery.reload({ waitUntil: "domcontentloaded" });
      await recoveryStatus.waitFor({ timeout: config.timeoutMs });
    }
    assert.match(await recoveryStatus.innerText(), /reset delivery will be attempted/i);

    const ownerPage = await owner.newPage();
    scanRuntime(ownerPage, findings);
    await login(ownerPage, config.ownerEmail, config.newOwnerPassword, config.timeoutMs);
    const inviteePage = await invitee.newPage();
    scanRuntime(inviteePage, findings);
    await login(inviteePage, config.inviteeEmail, config.inviteePassword, config.timeoutMs, /\/invitations\/accept/);
    await inviteePage.goto(`${config.appBaseURL}/invitations/accept?token=${encodeURIComponent(config.invitationToken)}`, { waitUntil: "domcontentloaded" });
    await submitAndWait(inviteePage, inviteePage.getByRole("button", { name: "Accept invitation" }), /status=accepted/, config.timeoutMs);
    assert.match(await inviteePage.locator("body").innerText(), /Invitation accepted/i);

    const membersURL = `${config.appBaseURL}/${config.tenantId}/projects/${config.projectId}/members`;
    await ownerPage.goto(membersURL, { waitUntil: "domcontentloaded" });
    await ownerPage.getByRole("cell", { name: config.inviteeEmail, exact: true }).waitFor({ timeout: config.timeoutMs });
    const tenantMembers = ownerPage.locator('section[data-member-scope="tenant"]');
    const ownerRow = tenantMembers.getByRole("row").filter({ hasText: config.ownerEmail });
    await submitAndWait(ownerPage, ownerRow.getByRole("button", { name: "Remove" }), /members_error=/, config.timeoutMs);
    assert.match(decodeURIComponent(ownerPage.url()), /LAST_OWNER/i);

    const quotaURL = `${config.appBaseURL}/${config.tenantId}/projects/${config.projectId}/llm-facility/quotas`;
    await ownerPage.goto(quotaURL, { waitUntil: "domcontentloaded" });
    await ownerPage.getByRole("heading", { name: "Quota & Billing" }).waitFor();
    const policy = ownerPage.locator('section[aria-labelledby="policy-heading"]');
    await policy.locator('input[name="tokenLimit"]').first().fill("100000");
    await policy.locator('input[name="costLimitMicros"]').first().fill("100000");
    await policy.locator('input[name="concurrencyLimit"]').first().fill("2");
    await policy.getByRole("button", { name: "Create policy" }).click({ timeout: config.timeoutMs });
    await waitForPersistedPolicy(ownerPage, config.timeoutMs);
    const health = ownerPage.locator('section[aria-labelledby="health-heading"]');
    await health.locator('input[name="channelId"]').fill(config.channelId);
    await health.locator('input[name="modelId"]').fill(config.modelId);
    await followActionRedirect(ownerPage, health.getByRole("button", { name: "Check" }), config.appBaseURL, config.timeoutMs);
    const healthStatus = health.locator(".success-box");
    await health.locator(".success-box, .error-box").first().waitFor({ timeout: config.timeoutMs });
    const healthError = health.locator(".error-box");
    if (await healthError.count()) assert.fail(`provider health failed: ${(await healthError.first().innerText()).trim()}`);
    assert.match(await healthStatus.innerText(), /healthy.*HTTP 200/i);

    await ownerPage.screenshot({ path: path.join(config.screenshotDir, "platform-desktop.png"), fullPage: true });
    await ownerPage.setViewportSize({ width: 390, height: 844 });
    await ownerPage.reload({ waitUntil: "domcontentloaded" });
    assert.equal(await ownerPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    await ownerPage.screenshot({ path: path.join(config.screenshotDir, "platform-mobile.png"), fullPage: true });
    await assertPrivacy(ownerPage, findings);
  } finally {
    await Promise.all([owner.close(), invitee.close(), anonymous.close()]);
    await browser.close();
  }
});

async function login(page, email, password, timeoutMs, destination = /\/projects\//) {
  await page.goto(`${value("APP_BASE_URL")}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await submitAndWait(page, page.getByRole("button", { name: "Sign in" }), destination, timeoutMs);
}

async function submitAndWait(page, control, urlPattern, timeoutMs) {
  await Promise.all([
    page.waitForURL(urlPattern, { timeout: timeoutMs, waitUntil: "domcontentloaded" }),
    control.click(),
  ]);
}

function scanRuntime(page, findings) {
  page.on("pageerror", (error) => findings.push(`pageerror:${String(error.message).slice(0, 120)}`));
  page.on("response", (response) => { if (response.status() >= 500) findings.push(`http:${response.status()}:${new URL(response.url()).pathname}`); });
}

async function waitForPersistedPolicy(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const version = page.locator('section[aria-labelledby="policy-heading"] input[name="expectedVersion"]');
  while (Date.now() < deadline) {
    await page.reload({ waitUntil: "domcontentloaded" });
    if (await version.count()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("persisted quota policy did not appear");
}

async function followActionRedirect(page, control, appBaseURL, timeoutMs) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/llm-facility/quotas"),
    { timeout: timeoutMs },
  );
  await control.click({ noWaitAfter: true, timeout: timeoutMs });
  const response = await responsePromise;
  const target = (await response.allHeaders())["x-action-redirect"]?.split(";", 1)[0] ?? "";
  if (!target.startsWith("/") || target.startsWith("//")) throw new Error("quota action omitted a safe same-origin redirect");
  await page.goto(new URL(target, appBaseURL).toString(), { waitUntil: "domcontentloaded" });
}

async function assertPrivacy(page, findings) {
  const text = `${await page.locator("body").innerText()}\n${await page.content()}`;
  for (const marker of ["encrypted_api_key", "credential_ref", "provider_response", "raw_body", "prompt", "manuscript content"]) {
    assert.doesNotMatch(text, new RegExp(marker, "i"));
  }
  assert.deepEqual(findings, []);
}

function loadConfig() {
  const config = {
    appBaseURL: value("APP_BASE_URL"), ownerEmail: value("OWNER_EMAIL"), oldOwnerPassword: value("OLD_OWNER_PASSWORD"),
    newOwnerPassword: value("NEW_OWNER_PASSWORD"), inviteeEmail: value("INVITEE_EMAIL"), inviteePassword: value("INVITEE_PASSWORD"),
    recoveryToken: value("RECOVERY_TOKEN"), invitationToken: value("INVITATION_TOKEN"), tenantId: value("TENANT_ID"),
    projectId: value("PROJECT_ID"), channelId: value("CHANNEL_ID"), modelId: value("MODEL_ID"),
    screenshotDir: value("SCREENSHOT_DIR"), timeoutMs: Number(value("TIMEOUT_MS") || 60000),
  };
  for (const [key, item] of Object.entries(config)) if ((typeof item === "string" && !item) || (key === "timeoutMs" && !(item > 0))) throw new Error(`platform browser config missing ${key}`);
  const url = new URL(config.appBaseURL); assert.equal(url.protocol, "http:"); assert.ok(["127.0.0.1", "localhost"].includes(url.hostname)); assert.equal(path.isAbsolute(config.screenshotDir), true);
  return config;
}
function value(suffix) { return String(process.env[`${prefix}${suffix}`] || "").trim(); }
function contextOptions() {
  const suffix = randomBytes(4).toString("hex");
  return { locale: "en-US", extraHTTPHeaders: { "x-forwarded-for": `2001:db8:${suffix.slice(0, 4)}:${suffix.slice(4)}::1` } };
}
