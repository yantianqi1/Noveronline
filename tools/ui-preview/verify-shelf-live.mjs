// 书架页真实栈视觉验收（无 mock，打真实 Go API via Next BFF）
// 旅程: 登录 → /workspace 书架 → 桌面/移动截图 + 悬停态截图
// 用法: node verify-shelf-live.mjs [baseURL]
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const BASE = process.argv[2] ?? process.env.WEB_BASE_URL ?? "http://127.0.0.1:3000";
function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for live acceptance`);
  return value;
}

const EMAIL = requiredEnv("MIROFISH_ACCEPTANCE_EMAIL");
const PASSWORD = requiredEnv("MIROFISH_ACCEPTANCE_PASSWORD");
const SHOTS = resolve("shots");
mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

// ── 1. 登录（真实 /v1/auth/login） ──────────────────────────────────────
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(1000); // 等 React 水合
const tryLogin = async () => {
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');
  return page
    .waitForFunction(() => !location.pathname.startsWith("/login"), null, { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
};
let loggedIn = await tryLogin();
if (!loggedIn) loggedIn = await tryLogin();
if (!loggedIn) throw new Error("登录未跳转");
console.log("PASS: 登录成功 →", page.url());

// ── 2. 书架页 ───────────────────────────────────────────────────────────
await page.goto(`${BASE}/workspace`, { waitUntil: "domcontentloaded" });
await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
await page.waitForFunction(() => document.body.innerText.includes("你的故事世界"), null, { timeout: 30000 });
await page.waitForTimeout(1600); // 等书本入场动画落位

const bookCount = await page.locator(".shelf-book").count();
const plankCount = await page.locator(".shelf-scene-plank").count();
console.log(`INFO: 书本 ${bookCount} 本, 搁板 ${plankCount} 层`);
if (bookCount === 0) throw new Error("书架没有渲染书本 (.shelf-book)");

await page.screenshot({ path: resolve(SHOTS, "shelf-desktop.png"), fullPage: false });
await page.screenshot({ path: resolve(SHOTS, "shelf-desktop-full.png"), fullPage: true });

// ── 3. 悬停抽出态 ───────────────────────────────────────────────────────
await page.locator(".shelf-book").first().hover();
await page.waitForTimeout(600);
await page.screenshot({ path: resolve(SHOTS, "shelf-hover.png"), fullPage: false });

// ── 4. 移动端 ───────────────────────────────────────────────────────────
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(700);
await page.screenshot({ path: resolve(SHOTS, "shelf-mobile.png"), fullPage: true });

await browser.close();
console.log("PASS: 截图完成 → tools/ui-preview/shots/shelf-*.png");
