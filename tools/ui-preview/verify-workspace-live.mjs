// Authenticated UI acceptance against the disposable Go API + Next BFF stack.
// Run: MIROFISH_ENABLE_SELF_SIGNUP=1 infra/scripts/run-live-test-stack.sh --app -- node tools/ui-preview/verify-workspace-live.mjs
// Chrome is used for layout/paint; Obscura explicitly does not implement them.
// MIROFISH_UI_TIMEOUT_MS overrides the 30-second browser wait on slower machines.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright-core";
import { disposableLiveDatabaseConfig } from "../../apps/web/scripts/live-test-database.mjs";

await disposableLiveDatabaseConfig(process.env.MIROFISH_LIVE_TEST_DATABASE_URL);
const stack = process.env.MIROFISH_LIVE_TEST_COMPOSE_PROJECT;
assert.match(stack ?? "", /^mirofish-saas-live-/);
const base = `http://127.0.0.1:${process.env.WEB_PORT}`;
const api = `http://127.0.0.1:${process.env.API_PORT}`;
const shots = resolve(process.env.MIROFISH_UI_EVIDENCE_DIR ?? "/tmp/mirofish-workspace-ui-20260907");
mkdirSync(shots, { recursive: true });
const checks = [];
const errors = [];
const findings = [];
const requests = new Map();
const timeoutMs = Number(process.env.MIROFISH_UI_TIMEOUT_MS ?? 30000);
assert.ok(Number.isFinite(timeoutMs) && timeoutMs > 0, "MIROFISH_UI_TIMEOUT_MS must be positive");
const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 960 } });
context.setDefaultTimeout(timeoutMs);
context.on("page", (tab) => {
  tab.on("pageerror", (error) => errors.push(error.message));
  tab.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith("/api/")) requests.set(request, {
      method: request.method(), pathname, startedAt: Date.now(), status: "pending",
    });
  });
  tab.on("response", (response) => {
    const entry = requests.get(response.request());
    if (entry) Object.assign(entry, { status: response.status(), elapsedMs: Date.now() - entry.startedAt });
  });
  tab.on("requestfailed", (request) => {
    const entry = requests.get(request);
    if (entry) Object.assign(entry, { status: "failed", elapsedMs: Date.now() - entry.startedAt, error: request.failure()?.errorText });
  });
});
const page = await context.newPage();
const email = `shelf-${randomBytes(6).toString("hex")}@example.test`;
const password = randomBytes(24).toString("base64url");
const longTitle = "山海旧事：在一座不会天亮的城里寻找第七次日出";

function pass(name) { checks.push(name); console.log(`PASS ${name}`); }
async function probe(name, run) {
  try {
    await run();
    pass(name);
  } catch (error) {
    findings.push(`${name}: ${error.message}`);
    console.error(`FAIL ${name}: ${error.message}`);
    await capture(`failure-${findings.length}`);
  }
}
function compose(...args) {
  return execFileSync("docker", ["compose", "-f", resolve("infra/docker-compose.yml"), "-p", stack, ...args],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}
async function expectStatus(response, expected, label) {
  assert.equal(response.status(), expected, `${label}: HTTP ${response.status()}`);
  return response;
}
async function settle() {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
  });
}
async function capture(name, fullPage = true) {
  await settle();
  await page.screenshot({ path: resolve(shots, `${name}.png`), fullPage });
}
async function assertNoOverflow(label) {
  const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
  assert.ok(sizes.document <= sizes.viewport + 1, `${label} overflow: ${JSON.stringify(sizes)}`);
}
async function assertHeaderControlsReachable(width) {
  const blocked = await page.locator("#project-topbar-slot").evaluate((slot) =>
    [...slot.closest("header").querySelectorAll("button")].flatMap((button) => {
      const box = button.getBoundingClientRect();
      if (!box.width || !box.height) return [];
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      const visible = box.left >= 0 && box.right <= innerWidth && hit && button.contains(hit);
      return visible ? [] : [button.getAttribute("aria-label") || button.textContent.trim()];
    }));
  assert.deepEqual(blocked, [], `Writer controls clipped or covered at ${width}`);
}
async function assertFocusInside(dialog, key = "Tab") {
  for (let i = 0; i < 12; i += 1) {
    await page.keyboard.press(key);
    const focus = await dialog.evaluate((node) => ({
      inside: node.contains(document.activeElement), focused: document.hasFocus(),
      activeTag: document.activeElement?.tagName, nativeModal: node.matches(":modal"),
    }));
    // Native dialogs allow tabbing into browser chrome, but never the inert page.
    assert.ok(focus.nativeModal && (focus.inside || (!focus.focused && focus.activeTag === "BODY")),
      `${key} escaped the modal: ${JSON.stringify(focus)}`);
  }
}
async function workspace() {
  await page.goto("/workspace");
  await page.getByRole("heading", { name: "你的故事世界" }).waitFor();
  await page.locator(".shelf-project").first().waitFor();
}
async function passwordLogin() {
  await page.goto("/login?returnTo=%2Fworkspace");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  const loggedIn = page.waitForResponse((response) =>
    response.request().method() === "POST" && response.url().endsWith("/api/auth/login"));
  await page.locator('button[type="submit"]').click();
  await expectStatus(await loggedIn, 201, "password login");
  await page.waitForURL("**/workspace");
  await page.locator(".shelf-project").first().waitFor();
}
async function waitForApi() {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try { if ((await fetch(`${api}/healthz`)).ok) return; } catch { /* API is restarting. */ }
    await new Promise((done) => setTimeout(done, 250));
  }
  throw new Error("real API did not recover within 30 seconds");
}

try {
  await expectStatus(await context.request.post("/api/auth/signup", { data: {
    display_name: "书架验收作者", email, password, project_title: "雨夜长卷",
  } }), 201, "signup");
  await context.clearCookies();
  await passwordLogin();
  pass("real signup, password login, and /api/me membership");

  const me = await (await context.request.get("/api/me")).json();
  const tenant = me.active_tenants.find((item) => item.role === "owner");
  assert.ok(tenant);
  const csrf = (await (await context.request.get("/api/auth/csrf-token")).json()).csrf_token;
  assert.ok(csrf);
  for (const title of ["青山以北", "长风渡", "未寄出的第七封信", longTitle]) {
    await expectStatus(await context.request.post(`/api/tenants/${tenant.tenant_id}/projects`, {
      headers: { "X-CSRF-Token": csrf, "X-Tenant-Id": tenant.tenant_id }, data: { title },
    }), 201, "create project through BFF");
  }
  await workspace();
  assert.equal(await page.locator(".shelf-project").count(), 5);

  const account = page.getByRole("button", { name: "账户菜单", exact: true });
  await account.focus();
  await page.keyboard.press("ArrowDown");
  assert.ok(await page.getByRole("menuitem", { name: "退出登录" }).evaluate((node) => node === document.activeElement));
  await page.keyboard.press("Escape");
  assert.ok(await account.evaluate((node) => node === document.activeElement));
  pass("account menu keyboard entry and Escape focus restoration");

  const search = page.getByRole("searchbox", { name: "搜索作品名称" });
  await search.fill("青山");
  await page.waitForFunction(() => document.querySelectorAll(".shelf-project").length === 1);
  assert.equal(new URL(page.url()).searchParams.get("q"), "青山");
  await page.reload();
  await page.locator(".shelf-project").first().waitFor();
  assert.equal(await search.inputValue(), "青山");
  assert.equal(await page.locator(".shelf-project").count(), 1);
  await page.locator(".shelf-project").first().click();
  await page.waitForURL(/\/overview$/);
  await page.getByRole("heading", { name: "导入与分析", exact: true }).waitFor();
  await page.goBack();
  await search.waitFor();
  assert.equal(await search.inputValue(), "青山");
  await search.fill("没有这本书");
  await page.getByRole("heading", { name: "没有找到匹配的作品" }).waitFor();
  await page.getByRole("search").getByRole("button", { name: "清除搜索" }).click();
  assert.equal(await search.inputValue(), "");
  assert.ok(await search.evaluate((node) => node === document.activeElement));
  pass("search, no results, clear, reload and back-navigation persistence");

  const create = page.getByRole("button", { name: "创建新作品", exact: true });
  await create.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "创建一部小说" });
  await dialog.waitFor();
  const titleInput = dialog.getByLabel("作品名称", { exact: true });
  assert.ok(await titleInput.evaluate((node) => node === document.activeElement));
  await assertFocusInside(dialog);
  await assertFocusInside(dialog, "Shift+Tab");
  await titleInput.fill("   ");
  await dialog.getByRole("button", { name: "创建并进入" }).click();
  await dialog.getByRole("alert").waitFor();
  assert.equal(await titleInput.getAttribute("aria-invalid"), "true");
  await titleInput.fill("夜航手记");
  await capture("create-desktop", false);
  await page.setViewportSize({ width: 375, height: 812 });
  await assertNoOverflow("mobile create");
  await capture("create-mobile", false);
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "detached" });
  assert.ok(await create.evaluate((node) => node === document.activeElement));
  await create.click();
  await dialog.getByLabel("作品名称", { exact: true }).fill("夜航手记");
  const created = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/projects"));
  await dialog.getByRole("button", { name: "创建并进入" }).click();
  await expectStatus(await created, 201, "create from UI");
  await page.waitForURL(/\/overview$/);
  await page.getByRole("heading", { name: "导入与分析", exact: true }).waitFor();
  pass("create dialog focus isolation, validation, cancellation and real persistence");

  await workspace();
  assert.equal(await page.locator(".shelf-project").count(), 6);
  assert.equal(await page.locator(".shelf-project-title").filter({ hasText: longTitle }).textContent(), longTitle);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: width === 375 ? 812 : 960 });
    await assertNoOverflow(`shelf ${width}`);
    await capture(`shelf-${width}`);
    const clipped = await page.locator(".shelf-project-title").evaluateAll((nodes) => nodes.some((node) => node.scrollHeight > node.clientHeight + 1));
    assert.equal(clipped, false, `title clipped at ${width}`);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.locator(".shelf-project").first().hover();
  assert.equal(await page.locator(".shelf-book").first().evaluate((node) => getComputedStyle(node).transform), "none");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  pass("375/768/1024/1440 layouts, complete long titles and reduced motion");

  await probe("project link in a new tab resolves real membership", async () => {
    const opened = context.waitForEvent("page");
    await page.getByRole("link", { name: "进入《青山以北》工作台", exact: true }).click({ button: "middle" });
    const other = await opened;
    try {
      await other.getByRole("heading", { name: "导入与分析", exact: true }).waitFor();
    } finally {
      await other.close();
    }
  });
  await probe("direct Writer link resolves membership without saved selection", async () => {
    const href = await page.getByRole("link", { name: "进入《青山以北》工作台", exact: true }).getAttribute("href");
    const direct = await context.newPage();
    try {
      await direct.goto(`${href}/writer`);
      await direct.getByText("稿件", { exact: true }).first().waitFor();
    } finally {
      await direct.close();
    }
  });

  const boundaryTitle = "山海旧事日月长明风雨归舟林间听雪江畔见月".repeat(10);
  await expectStatus(await context.request.post(`/api/tenants/${tenant.tenant_id}/projects`, {
    headers: { "X-CSRF-Token": csrf, "X-Tenant-Id": tenant.tenant_id }, data: { title: boundaryTitle },
  }), 201, "create title at the API length boundary");
  await workspace();
  await probe("maximum-length cover labels remain inside their covers", async () => {
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: width === 375 ? 812 : 960 });
      await capture(`shelf-long-title-${width}`);
      const escaped = await page.locator(".shelf-book-label").evaluateAll((labels) => labels.some((label) => {
        const bounds = label.getBoundingClientRect();
        const cover = label.closest(".shelf-book").getBoundingClientRect();
        return bounds.left < cover.left || bounds.right > cover.right;
      }));
      assert.equal(escaped, false, `cover title overflow at ${width}`);
      const caption = page.locator(".shelf-project-title").filter({ hasText: boundaryTitle });
      assert.equal(await caption.textContent(), boundaryTitle);
      assert.ok(await caption.evaluate((node) => node.scrollHeight <= node.clientHeight + 1));
      await assertNoOverflow(`maximum-length title ${width}`);
    }
  });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("link", { name: "进入《夜航手记》工作台", exact: true }).click();
  await page.waitForURL(/\/overview$/);
  await page.getByRole("heading", { name: "导入与分析", exact: true }).waitFor();
  const navButton = page.getByRole("button", { name: "工作台导航", exact: true });
  await navButton.waitFor();
  await navButton.focus();
  await page.keyboard.press("Enter");
  const navDialog = page.getByRole("dialog", { name: "工作台导航", exact: true });
  await navDialog.waitFor();
  assert.ok(await navDialog.evaluate((node) => node.matches(":modal")));
  await assertFocusInside(navDialog);
  await assertFocusInside(navDialog, "Shift+Tab");
  await page.keyboard.press("Escape");
  await navDialog.waitFor({ state: "detached" });
  assert.ok(await navButton.evaluate((node) => node === document.activeElement));
  await navButton.click();
  await capture("navigation-mobile");
  await navDialog.locator('a[href$="/writer"]').click();
  await page.waitForURL(/\/writer$/);
  await navDialog.waitFor({ state: "detached" });
  await page.getByText("稿件", { exact: true }).first().waitFor();
  await probe("Writer header controls remain reachable at every layout width", async () => {
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: width === 375 ? 812 : 960 });
      await settle();
      await assertHeaderControlsReachable(width);
    }
  });
  await page.setViewportSize({ width: 375, height: 812 });
  const chapterCreated = page.waitForResponse((response) =>
    response.request().method() === "POST" && response.url().endsWith("/chapters"));
  await page.getByRole("button", { name: "新章节", exact: true }).click();
  await expectStatus(await chapterCreated, 201, "create a chapter from the mobile header");
  const manuscript = page.getByRole("textbox", { name: /^手稿第 / }).first();
  await manuscript.waitFor();
  const saved = page.waitForResponse((response) =>
    response.request().method() === "PATCH" && response.url().includes("/manuscript-workspace/blocks/"));
  await manuscript.fill("夜色贴着纸页缓缓落下，远处的钟声刚好响了三下。");
  assert.equal(await manuscript.inputValue(), "夜色贴着纸页缓缓落下，远处的钟声刚好响了三下。");
  await expectStatus(await saved, 200, "save the manuscript through the real API");
  await page.getByText("已保存", { exact: true }).waitFor();
  await assertHeaderControlsReachable(375);
  const views = page.getByRole("navigation", { name: "画布视图", exact: true });
  await views.getByRole("button", { name: "章节", exact: true }).click();
  await page.getByText("用上下键调整顺序", { exact: false }).waitFor();
  await views.getByRole("button", { name: "稿件", exact: true }).click();
  await manuscript.waitFor();
  assert.equal(await manuscript.inputValue(), "夜色贴着纸页缓缓落下，远处的钟声刚好响了三下。");
  await page.reload();
  await manuscript.waitFor();
  assert.equal(await manuscript.inputValue(), "夜色贴着纸页缓缓落下，远处的钟声刚好响了三下。");
  pass("mobile header chapter creation, exact manuscript save, view switching and reload");
  await assertNoOverflow("mobile writer");
  await capture("writer-mobile");
  await navButton.click();
  await page.setViewportSize({ width: 1440, height: 960 });
  await navDialog.waitFor({ state: "detached" });
  await probe("desktop composer survives mobile resize and supports keyboard input", async () => {
    await settle();
    const composer = page.getByRole("textbox", { name: "给合著者的指令", exact: true });
    const size = await composer.evaluate((node) => ({
      visible: node.clientHeight,
      needed: Math.min(node.scrollHeight, parseFloat(getComputedStyle(node).maxHeight)),
    }));
    assert.ok(size.visible >= size.needed - 1, `composer clipped after resize: ${JSON.stringify(size)}`);
    await composer.fill("在钟声响起后续写。");
    await composer.press("End");
    await composer.press("Shift+Enter");
    await page.keyboard.insertText("保留叙述视角。");
    assert.equal(await composer.inputValue(), "在钟声响起后续写。\n保留叙述视角。");
    await composer.fill("");
  });
  await capture("writer-desktop");
  pass("mobile navigation focus isolation, Writer route and desktop resize dismissal");

  await workspace();
  compose("stop", "api");
  try {
    await probe("creation preserves the real CSRF service error", async () => {
      await create.click();
      await dialog.getByLabel("作品名称", { exact: true }).fill("服务恢复后再创建");
      const csrfFailed = page.waitForResponse((response) => response.url().endsWith("/api/auth/csrf-token"));
      await dialog.getByRole("button", { name: "创建并进入" }).click();
      const response = await expectStatus(await csrfFailed, 502, "CSRF during outage");
      const payload = await response.json();
      await dialog.getByRole("alert").waitFor();
      assert.equal(await dialog.getByRole("alert").textContent(), payload.error.message);
    });
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "detached" });

    await probe("failed keyboard logout keeps its error visible", async () => {
      await account.focus();
      await page.keyboard.press("ArrowDown");
      const rejected = page.waitForResponse((response) => response.url().endsWith("/api/auth/csrf-token"));
      await page.keyboard.press("Enter");
      await expectStatus(await rejected, 502, "logout during the real API outage");
      await page.locator(".shelf-header").getByRole("alert").waitFor();
      assert.ok(await account.evaluate((node) => node === document.activeElement));
    });
    await page.reload();
    await page.getByRole("heading", { name: "书架暂时打不开" }).waitFor();
    await capture("shelf-api-error");
  } finally {
    compose("up", "-d", "--no-deps", "--force-recreate", "api");
    await waitForApi();
  }
  await page.getByRole("button", { name: "重新加载" }).click();
  await page.locator(".shelf-project").first().waitFor();
  assert.equal(await page.locator(".shelf-project").count(), 7);
  pass("real API outage, visible error, restart and retry recovery");

  await create.click();
  await dialog.getByLabel("作品名称", { exact: true }).fill("登录恢复后再创建");
  await expectStatus(await context.request.delete("/api/auth/session", {
    headers: { "X-CSRF-Token": csrf },
  }), 204, "revoke the current session while the form stays open");
  await probe("expired creation session offers sign-in recovery", async () => {
    const rejected = page.waitForResponse((response) => response.url().endsWith("/api/auth/csrf-token"));
    await dialog.getByRole("button", { name: "创建并进入" }).click();
    await expectStatus(await rejected, 401, "creation after session revocation");
    await dialog.getByRole("link", { name: "重新登录", exact: true }).click();
    await page.waitForURL(/\/login\?returnTo=/);
  });
  await passwordLogin();

  await account.focus();
  await page.keyboard.press("ArrowDown");
  const loggedOut = page.waitForResponse((response) => response.request().method() === "DELETE" && response.url().endsWith("/api/auth/session"));
  await page.keyboard.press("Enter");
  await expectStatus(await loggedOut, 204, "logout");
  await page.waitForURL(/\/login$/);
  assert.equal((await context.request.get("/api/me")).status(), 401);
  pass("keyboard logout with real CSRF/session revocation");
  assert.deepEqual(errors, [], "unexpected browser page errors");
  assert.deepEqual(findings, [], "workspace boundary regressions");
  writeFileSync(resolve(shots, "report.json"), JSON.stringify({ result: "passed", checks, pageErrors: errors, widths: [375, 768, 1024, 1440] }, null, 2));
  console.log(`Evidence: ${shots}`);
} catch (error) {
  await page.screenshot({ path: resolve(shots, "failure.png"), fullPage: true }).catch(() => {});
  const [bff, apiHealth, browserBff] = await Promise.all([
    context.request.get("/api/me", { timeout: 5000 }).then((response) => response.status(), () => "unreachable"),
    fetch(`${api}/healthz`, { signal: AbortSignal.timeout(5000) }).then((response) => response.status, () => "unreachable"),
    page.evaluate(async () => {
      try { return (await fetch("/api/me", { signal: AbortSignal.timeout(5000) })).status; }
      catch { return "unreachable"; }
    }).catch(() => "unreachable"),
  ]);
  writeFileSync(resolve(shots, "transport.json"), JSON.stringify({ bff, apiHealth, browserBff }, null, 2));
  writeFileSync(resolve(shots, "network.json"), JSON.stringify([...requests.values()], null, 2));
  writeFileSync(resolve(shots, "report.json"), JSON.stringify({ result: "failed", checks, pageErrors: errors, findings, error: error.message }, null, 2));
  throw error;
} finally {
  await context.close();
  await browser.close();
}
