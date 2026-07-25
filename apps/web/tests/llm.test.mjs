import { test } from "node:test";
import assert from "node:assert/strict";

import {
  bindingFor,
  enabledChannels,
  groupModules,
  summarizeBindings,
} from "../lib/api/llm.ts";

const modules = [
  { module_key: "sequential_reading", group: "Seed / Graph", label: "Sequential Reading", description: "" },
  { module_key: "story_ontology", group: "Seed / Graph", label: "Story Ontology", description: "" },
  { module_key: "writer_reviewer", group: "Writer", label: "Writer Reviewer", description: "" },
  { module_key: "writer_composer", group: "Writer", label: "Writer Composer", description: "" },
  { module_key: "narrative_archives", group: "Archive / Assets", label: "Narrative Archives", description: "" },
  { module_key: "worldline_director", group: "Worldline", label: "Worldline Director", description: "" },
  { module_key: "character_dialogue", group: "Character Console", label: "Character Dialogue", description: "" },
];

function binding(moduleKey, scope) {
  return {
    module_key: moduleKey,
    scope,
    channel_id: "ch-1",
    channel_name: "Test",
    model_id: "gpt-5.5",
    provider: "openai-compatible",
    base_url: "https://x/v1",
    supports_tools: true,
    supports_json: true,
    settings: {},
    updated_at: "2026-07-22",
  };
}

test("groupModules groups into the fixed family order", () => {
  const groups = groupModules(modules);
  assert.deepEqual(
    groups.map((g) => g.key),
    ["Seed / Graph", "Archive / Assets", "Character Console", "Worldline", "Writer"],
  );
});

test("groupModules preserves registry order within a group", () => {
  const groups = groupModules(modules);
  const seed = groups.find((g) => g.key === "Seed / Graph");
  assert.deepEqual(
    seed.modules.map((m) => m.module_key),
    ["sequential_reading", "story_ontology"],
  );
});

test("groupModules keeps unknown groups at the end", () => {
  const withUnknown = [...modules, { module_key: "x", group: "Other", label: "X", description: "" }];
  const groups = groupModules(withUnknown);
  assert.equal(groups[groups.length - 1].key, "Other");
});

test("bindingFor returns unbound when no binding matches", () => {
  assert.deepEqual(bindingFor("sequential_reading", []), { kind: "unbound" });
});

test("bindingFor prefers a project override over inherited", () => {
  const bindings = [binding("sequential_reading", "tenant"), binding("sequential_reading", "project")];
  assert.equal(bindingFor("sequential_reading", bindings).kind, "project");
});

test("bindingFor treats tenant/platform scope as inherited", () => {
  assert.equal(bindingFor("sequential_reading", [binding("sequential_reading", "tenant")]).kind, "inherited");
});

test("summarizeBindings counts bound, overridden, unbound", () => {
  const bindings = [
    binding("sequential_reading", "project"),
    binding("story_ontology", "tenant"),
    binding("writer_reviewer", "project"),
  ];
  const summary = summarizeBindings(modules, bindings);
  assert.equal(summary.total, modules.length);
  assert.equal(summary.bound, 3);
  assert.equal(summary.overridden, 2);
  assert.equal(summary.unbound, modules.length - 3);
});

test("enabledChannels filters out disabled channels", () => {
  const channels = [
    { channel_id: "a", enabled: true },
    { channel_id: "b", enabled: false },
  ];
  assert.deepEqual(
    enabledChannels(channels).map((c) => c.channel_id),
    ["a"],
  );
});
