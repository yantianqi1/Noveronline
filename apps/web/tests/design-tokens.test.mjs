import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

/**
 * Design-system contract.
 *
 * The token vocabulary in app/globals.css only holds if off-scale values are
 * unreachable. Before this test existed the theme was defined and then bypassed:
 * 24 arbitrary font sizes, 15 radii, 18 hand-written shadows, and ~98 hardcoded
 * colours had accumulated alongside the tokens that were supposed to replace
 * them. These assertions are what keep that from happening again.
 *
 * Follows the same shape as scaffold-contract.test.mjs: read the sources, assert
 * on them, no new dependencies.
 */

const root = path.resolve(import.meta.dirname, "..");
const SCAN_ROOTS = ["app", "components"];
const SKIP_DIRS = new Set(["node_modules", ".next", ".next-dev", "api"]);

async function sourceFiles() {
  const out = [];
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      if (SKIP_DIRS.has(entry.name)) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.name.endsWith(".tsx")) out.push(full);
    }
  }
  for (const r of SCAN_ROOTS) await walk(path.join(root, r));
  return out;
}

/** Collect every `pattern` match across the tree as `relative/path:line  match`. */
async function findAll(pattern) {
  const hits = [];
  for (const file of await sourceFiles()) {
    const rel = path.relative(root, file);
    const lines = (await readFile(file, "utf8")).split("\n");
    lines.forEach((line, i) => {
      for (const m of line.matchAll(pattern)) hits.push(`${rel}:${i + 1}  ${m[0]}`);
    });
  }
  return hits;
}

const report = (hits, limit = 12) =>
  `\n${hits.slice(0, limit).join("\n")}${hits.length > limit ? `\n… and ${hits.length - limit} more` : ""}`;

test("type scale: no arbitrary font sizes or line heights", async () => {
  const sizes = await findAll(/\btext-\[[0-9.]+(px|rem|em)\]/g);
  assert.equal(sizes.length, 0, `Use a --text-* token instead:${report(sizes)}`);

  const leading = await findAll(/\bleading-\[[0-9.]+\]/g);
  assert.equal(
    leading.length,
    0,
    `Line height ships paired with each type token; drop the override:${report(leading)}`,
  );
});

test("radius scale: only control / panel / modal / full", async () => {
  const arbitrary = await findAll(/\brounded(-[a-z]{1,2})?-\[[^\]]+\]/g);
  assert.equal(arbitrary.length, 0, `Use rounded-control|panel|modal:${report(arbitrary)}`);

  // Tailwind's stock steps are cleared in @theme, so these would silently
  // render square corners rather than erroring.
  const stock = await findAll(/\brounded-(xs|sm|md|lg|xl|2xl|3xl|4xl)\b/g);
  assert.equal(stock.length, 0, `Not in the theme — use the named steps:${report(stock)}`);
});

test("elevation: no hand-written shadows", async () => {
  const arbitrary = await findAll(/\bshadow-\[[^\]]+\]/g);
  assert.equal(
    arbitrary.length,
    0,
    `Use shadow-hairline|lift|panel|accent|ink:${report(arbitrary)}`,
  );
  const stock = await findAll(/\bshadow-(2xs|xs|sm|md|lg|xl|2xl)\b/g);
  assert.equal(stock.length, 0, `Not in the theme:${report(stock)}`);
});

test("colour: no raw hex, rgba, or stock Tailwind palettes in components", async () => {
  const raw = await findAll(/\b(?:text|bg|border|ring|fill|stroke|from|via|to)-\[(?:#|rgba?\()[^\]]*\]/g);
  assert.equal(raw.length, 0, `Add a token to @theme instead:${report(raw)}`);

  const stockPalette = await findAll(
    /\b(?:text|bg|border|ring)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}\b/g,
  );
  assert.equal(
    stockPalette.length,
    0,
    `Stock palettes clash with paper & vermilion — use the semantic tokens:${report(stockPalette)}`,
  );

  // text-muted/60 mixed down to ~2.7:1 on paper. muted-soft is the tested step.
  const washed = await findAll(/\btext-muted\/[0-9]+/g);
  assert.equal(washed.length, 0, `Use text-muted-soft, not an alpha tint:${report(washed)}`);
});

test("icons: no emoji or glyph substitutes", async () => {
  // Emoji, dingbats, and the box-drawing arrows previously used as chevrons.
  const emoji = await findAll(
    /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{25A0}-\u{25FF}]/gu,
  );
  assert.equal(emoji.length, 0, `Use a lucide-react icon:${report(emoji)}`);
});

test("typography: hanzi labels carry no hand-typed spacing", async () => {
  // "工 作 台" plus a tracking utility double-spaced the label and pushed it
  // off-centre in its chip. The tracking token does this on its own.
  const spaced = await findAll(/[一-鿿](?: [一-鿿]){2,}/g);
  const offenders = spaced.filter((h) => !h.includes("channel-panel"));
  assert.equal(offenders.length, 0, `Remove the spaces; keep tracking-label:${report(offenders)}`);

  // Hanzi has no italic forms; browsers synthesise a skew that reads as a bug.
  const italic = await findAll(/\bitalic\b/g);
  assert.equal(italic.length, 0, `Distinguish with font-serif or weight:${report(italic)}`);
});

test("theme defines the full token vocabulary", async () => {
  const css = await readFile(path.join(root, "app/globals.css"), "utf8");
  const required = [
    "--text-caption", "--text-sm", "--text-base", "--text-md",
    "--text-lg", "--text-xl", "--text-display", "--text-reading",
    "--radius-control", "--radius-panel", "--radius-modal",
    "--shadow-hairline", "--shadow-lift", "--shadow-panel", "--shadow-accent",
    "--color-success", "--color-warning", "--color-danger", "--color-candidate",
    "--color-muted-soft", "--tracking-label",
    "--breakpoint-stack", "--breakpoint-wide",
    "--spacing-rail-nav", "--spacing-rail-filter", "--spacing-rail-inspector",
    "--default-transition-duration",
  ];
  for (const token of required) {
    assert.match(css, new RegExp(`${token}\\s*:`), `@theme is missing ${token}`);
  }
  // Stock scales must stay cleared, or the off-scale values become reachable.
  for (const ns of ["--text-\\*", "--radius-\\*", "--shadow-\\*"]) {
    assert.match(css, new RegExp(`${ns}\\s*:\\s*initial`), `@theme must clear ${ns}`);
  }
});

test("fonts declared in the theme are actually loaded", async () => {
  // The theme used to name IBM Plex Sans and Source Serif 4 while nothing
  // loaded them, so every serif heading silently fell back to a system face.
  const layout = await readFile(path.join(root, "app/layout.tsx"), "utf8");
  const css = await readFile(path.join(root, "app/globals.css"), "utf8");
  assert.match(layout, /next\/font\/google/, "layout must load the type families");
  for (const [family, cssVar] of [
    ["Noto_Sans_SC", "--font-cn-sans"],
    ["Noto_Serif_SC", "--font-cn-serif"],
  ]) {
    assert.match(layout, new RegExp(family), `layout must load ${family}`);
    assert.match(layout, new RegExp(cssVar), `${family} must expose ${cssVar}`);
    assert.match(css, new RegExp(`var\\(${cssVar}\\)`), `@theme must consume ${cssVar}`);
  }
  // CJK families must not be preloaded — that pulls every unicode-range chunk.
  assert.match(layout, /preload:\s*false/, "CJK faces must set preload: false");
});

test("layout bands: rails use the width tokens, not hand-picked pixels", async () => {
  const files = await sourceFiles();
  const offenders = [];
  for (const file of files) {
    const rel = path.relative(root, file);
    const src = await readFile(file, "utf8");
    for (const m of src.matchAll(/w-\[(\d{3})px\]\s+shrink-0/g)) {
      // The graph minimap is a canvas overlay, not a layout rail.
      if (rel.includes("graph-workspace")) continue;
      offenders.push(`${rel}  ${m[0]}`);
    }
  }
  assert.equal(
    offenders.length,
    0,
    `Rails use w-rail-nav | w-rail-filter | w-rail-inspector:${report(offenders)}`,
  );
});
