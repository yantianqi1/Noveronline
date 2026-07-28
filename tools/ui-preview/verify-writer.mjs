// Page-level acceptance for the Writer workbench redesign.
//
// 1) Seeds REAL data through the running stack (Next BFF → Go control plane →
//    Postgres): a throwaway user, its first project, one chapter, manuscript
//    blocks of Chinese prose (leading `# 第一章 …` heading included), and a
//    conversation-thread record for the dock.
// 2) Drives the REAL UI with the system Chrome: fills the login form, enters
//    the writer workbench, waits for the manuscript + rail to load, and takes
//    a 1600×1000 screenshot.
//
// Usage: node verify-writer.mjs <output.png> [baseUrl]
import { chromium } from "playwright-core";
import { resolve } from "node:path";

const [output, baseUrl = "http://127.0.0.1:3100"] = process.argv.slice(2);
if (!output) {
  console.error("usage: node verify-writer.mjs <output.png> [baseUrl]");
  process.exit(1);
}

const stamp = Date.now().toString(36);
const EMAIL = `ui-review-${stamp}@example.com`;
const PASSWORD = "ui-review-pass-2026!";
const BOOK_TITLE = "清河夜航船";

// Sample prose mirrors the design benchmark (prototype-final3.html), cleaned of
// the UI chrome text the prototype floats over the paragraphs.
const PARAGRAPHS = [
  "沈砚舟觉得自己的运气实在不好。明明是个穿越者，脑子里装着一肚子后世的刑名之学，偏偏投生到了这个鬼地方——一个连科举都没资格参加的胥吏家庭。更要命的是，他现在的身份是大胤朝清河县衙下辖的一名捕快，说白了就是个底层公门中人，整天跟鸡毛蒜皮的案子打交道。",
  "今天又是无聊的一天。沈砚舟从县衙出来，伸了个懒腰，骨节咔咔作响。炼精境的修为让他的身体素质远超常人，但这点实力在真正的强者面前根本不够看——他那个当捕头的师父赵四海就是练气境，比他高出一个大境界，一巴掌就能把他拍趴下。",
  "“砚舟，走，喝酒去。”同僚李栓从后面追上来，拍了拍他的肩膀。这人三十出头，圆脸微胖，一副市井油滑的模样。沈砚舟摆摆手：“今天不行，家里有事。”“得了吧你，谁不知道你们家那点破事。”李栓嘿嘿一笑，“你那婶婶又给你脸色看了？”",
  "沈砚舟没说话，算是默认。说起来也怪他自己。穿越过来三年了，除了练出一身蛮力，什么正经事都没干成。沈家在清河算是底层吏员家庭，二叔沈平志在衙门当捕头，勉强维持一家生计。婶婶李茹是个精明势利的女人，一见他这个白吃饭的侄子就皱眉。",
  "雨是傍晚落起来的。他站在廊下看雨，看雨脚把青石板砸出一个个小坑。库房的更声远远传来，三长两短——那是税银入库的号子。他忽然心里一动：入库的数目，好像对不上。",
];
const USER_INSTRUCTION = "开始第一章——雨夜、县衙、税银入库。";
const AGENT_REPLY = "收到。我先从雨夜县衙起笔，把税银入库的疑点埋进第一章的结尾。";

// ── Seed through the real BFF chain ─────────────────────────────────────

function sessionCookieFrom(response) {
  const cookies =
    typeof response.headers.getSetCookie === "function"
      ? response.headers.getSetCookie()
      : [response.headers.get("set-cookie")].filter(Boolean);
  for (const cookie of cookies) {
    const match = cookie.match(/mirofish_session=([^;]+)/);
    if (match) return `mirofish_session=${match[1]}`;
  }
  return null;
}

async function api(path, { method = "GET", cookie, csrf, tenant, body } = {}) {
  const headers = { Accept: "application/json" };
  if (cookie) headers.Cookie = cookie;
  if (csrf) headers["X-CSRF-Token"] = csrf;
  if (tenant) headers["X-Tenant-Id"] = tenant;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${method} ${path} → ${response.status}: ${text.slice(0, 300)}`);
  }
  return { response, json: text ? JSON.parse(text) : null };
}

const signup = await fetch(`${baseUrl}/api/auth/signup`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Accept: "application/json" },
  body: JSON.stringify({
    display_name: "验收编辑",
    email: EMAIL,
    password: PASSWORD,
    project_title: BOOK_TITLE,
  }),
});
if (!signup.ok) {
  throw new Error(`signup → ${signup.status}: ${(await signup.text()).slice(0, 300)}`);
}
const cookie = sessionCookieFrom(signup);
if (!cookie) throw new Error("signup did not return a session cookie");
const me = await signup.json();
const tenantId = me.active_tenants?.[0]?.tenant_id;
const projectId = me.active_projects?.[0]?.project_id;
if (!tenantId || !projectId) {
  throw new Error(`signup response missing tenant/project: ${JSON.stringify(me).slice(0, 300)}`);
}
console.log(`seeded user=${EMAIL} tenant=${tenantId} project=${projectId}`);

const { json: csrfPayload } = await api("/api/auth/csrf-token", { cookie });
const csrf = csrfPayload?.csrf_token;
if (!csrf) throw new Error("no csrf token");

const { json: chapterEnvelope } = await api(`/api/projects/${projectId}/chapters`, {
  method: "POST",
  cookie,
  csrf,
  tenant: tenantId,
  body: { title: "第一章", order: 1 },
});
const chapterId = chapterEnvelope?.data?.chapter_id ?? chapterEnvelope?.chapter_id;
if (!chapterId) throw new Error("chapter creation returned no id");

for (const [index, paragraph] of PARAGRAPHS.entries()) {
  const content = index === 0 ? `# 第一章 · 雨夜借刀\n\n${paragraph}` : paragraph;
  await api(`/api/projects/${projectId}/manuscript-workspace/blocks`, {
    method: "POST",
    cookie,
    csrf,
    tenant: tenantId,
    body: { chapter_id: chapterId, content_text: content },
  });
}
console.log(`seeded chapter=${chapterId} blocks=${PARAGRAPHS.length}`);

const { json: threadEnvelope } = await api(`/api/projects/${projectId}/writer-threads`, {
  method: "POST",
  cookie,
  csrf,
  tenant: tenantId,
  body: {},
});
const threadId = threadEnvelope?.data?.thread_id ?? threadEnvelope?.thread_id;
if (threadId) {
  await api(`/api/projects/${projectId}/writer-threads/${threadId}/messages`, {
    method: "POST",
    cookie,
    csrf,
    tenant: tenantId,
    body: { role: "user", body: USER_INSTRUCTION },
  });
  await api(`/api/projects/${projectId}/writer-threads/${threadId}/messages`, {
    method: "POST",
    cookie,
    csrf,
    tenant: tenantId,
    body: { role: "agent", body: AGENT_REPLY },
  });
  console.log(`seeded thread=${threadId} messages=2`);
} else {
  console.log("thread ensure returned no id — dock will render its empty state");
}

// ── Drive the real UI ───────────────────────────────────────────────────

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 2,
});

await page.goto(`${baseUrl}/login`, { waitUntil: "networkidle" });
await page.locator("#email").fill(EMAIL);
await page.locator("#password").fill(PASSWORD);
await page.getByRole("button", { name: "登录" }).click();
await page.waitForURL(`${baseUrl}/`, { timeout: 30_000 });

// Same selection mechanism the shelf uses when a project is opened.
await page.evaluate(
  ([tenant, project]) => {
    window.sessionStorage.setItem(
      "mirofish.activeProject",
      JSON.stringify({ tenant_id: tenant, project_id: project }),
    );
  },
  [tenantId, projectId],
);

await page.goto(`${baseUrl}/projects/${projectId}/writer`, { waitUntil: "domcontentloaded" });
// Manuscript running head + first paragraph + the dock's thread bubble.
await page.getByText("第一章 · 雨夜借刀", { exact: false }).first().waitFor({ timeout: 30_000 });
await page.getByText("沈砚舟觉得自己的运气实在不好", { exact: false }).first().waitFor({ timeout: 30_000 });
await page.getByText(USER_INSTRUCTION, { exact: false }).first().waitFor({ timeout: 30_000 });
// Let webfonts and entrance transitions settle.
await page.waitForTimeout(900);
await page.screenshot({ path: resolve(output) });

// The dock's second face: 待审资产 review queue (crossfade, both stay mounted).
await page.getByRole("tab", { name: /待审资产/ }).click();
await page.waitForTimeout(500);
const proposalsOutput = resolve(output.replace(/\.png$/, "") + "-proposals.png");
await page.screenshot({ path: proposalsOutput });
console.log(`wrote ${proposalsOutput}`);

await browser.close();
console.log(`wrote ${output}`);
