import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overviewViewSource = readFileSync(new URL("../src/views/OverviewView.vue", import.meta.url), "utf8");
const uploadPanelSource = readFileSync(new URL("../src/views/overview/SeedUploadPanel.vue", import.meta.url), "utf8");
const pipelineSource = readFileSync(new URL("../src/views/overview/PipelineVisualization.vue", import.meta.url), "utf8");

test("overview stage does not keep the legacy centered max width", () => {
  assert.doesNotMatch(overviewViewSource, /\.overview-stage\s*\{[^}]*max-width:\s*1200px;/s);
});

test("seed upload container does not keep the legacy narrow max width", () => {
  assert.doesNotMatch(uploadPanelSource, /\.upload-container\s*\{[^}]*max-width:\s*900px;/s);
});

test("pipeline visualization uses a wrapping grid instead of horizontal scrolling", () => {
  assert.match(pipelineSource, /\.pipeline-flow\s*\{[^}]*display:\s*grid;/s);
  assert.match(pipelineSource, /\.pipeline-flow\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(/s);
  assert.doesNotMatch(pipelineSource, /\.pipeline-flow\s*\{[^}]*overflow-x:\s*auto;/s);
});

test("overview keeps an idle upload target even before any project exists", () => {
  assert.match(
    overviewViewSource,
    /<div v-if="upload\.state\.uploadPhase === 'idle'" id="seed-upload-anchor" class="hidden-upload">/s,
  );
});
