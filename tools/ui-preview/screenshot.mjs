// Screenshot a local HTML file with the system Chrome (no browser download).
// Usage: node screenshot.mjs <input.html> <output.png> [width] [height] [fullPage]
import { chromium } from "playwright-core";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const [input, output, width = "1600", height = "1000", fullPage = "false"] =
  process.argv.slice(2);

if (!input || !output) {
  console.error("usage: node screenshot.mjs <input.html> <output.png> [w] [h] [fullPage]");
  process.exit(1);
}

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({
  viewport: { width: Number(width), height: Number(height) },
  deviceScaleFactor: 2,
});
const target = /^https?:\/\//.test(input)
  ? input
  : pathToFileURL(resolve(input)).href;
await page.goto(target, { waitUntil: "networkidle" });
// Give webfonts / animations a beat to settle.
await page.waitForTimeout(600);
await page.screenshot({ path: resolve(output), fullPage: fullPage === "true" });
await browser.close();
console.log(`wrote ${output}`);
