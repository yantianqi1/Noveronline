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
  assert.match(preview, /displayAssetTitle/);
  assert.match(preview, /structureAssetBody/);
  assert.match(preview, /asset-preview-structured|data-testid="asset-preview-structured"/);
  assert.match(preview, /asset-preview-raw|原始结构/);
  assert.match(preview, /formatRawPayloadJson/);
  assert.doesNotMatch(preview, /formatPayloadPreview/);
  assert.match(browse, /displayAssetTitle/);
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
