import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function source(rel) {
  return readFile(path.join(root, rel), "utf8");
}

// Minimal pure reimplementation for runtime tests (mirrors lib/asset-display.ts)
function firstString(payload, keys) {
  if (!payload) return "";
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

const TYPE_KEY_TITLES = new Set([
  "character", "relationship", "world_rule", "plot_thread",
  "ontology", "note_summary", "note", "story_ontology",
]);

function isTypeKeyTitle(value) {
  return TYPE_KEY_TITLES.has(String(value ?? "").trim().toLowerCase());
}

function composeRelationshipTitle(payload) {
  const source = firstString(payload, ["source", "from", "a"]);
  const target = firstString(payload, ["target", "to", "b"]);
  const relType = firstString(payload, ["relationship_type", "relation_type", "type", "kind"]);
  if (!source && !target) return "";
  const left = source || "?";
  const right = target || "?";
  return relType ? `${left} → ${right} / ${relType}` : `${left} → ${right}`;
}

function displayAssetTitle(input) {
  const title = String(input.title ?? "").trim();
  const payload = input.payload ?? undefined;
  if (title && !isTypeKeyTitle(title)) return title;
  const composed = composeRelationshipTitle(payload);
  if (composed) return composed;
  const note = firstString(payload, ["summary", "description"]);
  if (note) return note.length > 80 ? `${note.slice(0, 80)}…` : note;
  return title || "—";
}

test("asset-display source exports displayAssetTitle and structureAssetBody", async () => {
  const src = await source("lib/asset-display.ts");
  assert.match(src, /export function displayAssetTitle/);
  assert.match(src, /export function structureAssetBody/);
  assert.match(src, /export function formatRawPayloadJson/);
  assert.match(src, /composeRelationshipTitle/);
  assert.match(src, /林深|source.*target|→/);
});

test("preview dialog uses structured sections not primary JSON dump", async () => {
  const preview = await source("components/asset-preview-dialog.tsx");
  const browse = await source("components/asset-browse-client.tsx");
  const css = await source("app/globals.css");
  assert.match(preview, /displayAssetTitle/);
  assert.match(preview, /structureAssetBody/);
  assert.match(preview, /summaryDistinct|structured\.summaryDistinct/);
  assert.match(preview, /asset-preview-structured|data-testid="asset-preview-structured"/);
  assert.match(preview, /asset-preview-raw|原始结构/);
  assert.match(preview, /可点开|collapsed by default/);
  assert.match(preview, /formatRawPayloadJson/);
  assert.doesNotMatch(preview, /formatPayloadPreview/);
  assert.match(browse, /displayAssetTitle/);
  // Soft fold cue, not a stiff button chrome.
  assert.match(css, /asset-preview-raw-hint/);
  assert.match(css, /asset-preview-raw-label/);
  assert.match(css, /repeating-linear-gradient/);
});

test("asset-display source defines distinctSummary for duplicate summary/body", async () => {
  const src = await source("lib/asset-display.ts");
  assert.match(src, /export function distinctSummary/);
  assert.match(src, /summaryDistinct/);
  assert.match(src, /normalizeDisplayText/);
  // Pure logic mirrored here so node:test does not need TS loader.
  function normalizeDisplayText(value) {
    return value.trim().replace(/\s+/g, " ");
  }
  function distinctSummary(summary, prose) {
    const s = String(summary ?? "").trim();
    if (!s || isTypeKeyTitle(s)) return "";
    const p = String(prose ?? "").trim();
    if (!p) return s;
    if (normalizeDisplayText(s) === normalizeDisplayText(p)) return "";
    if (p.startsWith(s) && p.length > s.length) return "";
    if (s.startsWith(p) && s.length <= p.length + 8) return "";
    return s;
  }
  const same = "A cold, chaotic energy that enters Chen Ji from dead bodies.";
  assert.equal(distinctSummary(same, same), "");
  assert.equal(distinctSummary("短摘要", same), "短摘要");
});

test("display title composes relationship when stored title is type key", () => {
  assert.equal(
    displayAssetTitle({
      title: "relationship",
      asset_type: "relationship",
      payload: { source: "林深", target: "静妃", relationship_type: "师徒" },
    }),
    "林深 → 静妃 / 师徒",
  );
});

test("display title keeps human name", () => {
  assert.equal(
    displayAssetTitle({ title: "林深", payload: { summary: "主角" } }),
    "林深",
  );
});
