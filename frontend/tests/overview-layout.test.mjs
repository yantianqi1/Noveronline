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
    /id="seed-upload-anchor"/s,
  );
});

test("overview composes the command deck around focus card, next actions, and drawer", () => {
  assert.match(overviewViewSource, /<OverviewHeroPanel/s);
  assert.match(overviewViewSource, /<OverviewTaskFocusCard/s);
  assert.match(overviewViewSource, /<OverviewNextActionsPanel/s);
  assert.match(overviewViewSource, /<OverviewTaskDrawer/s);
  assert.match(overviewViewSource, /class="overview-command-grid"/s);
  assert.doesNotMatch(overviewViewSource, /class="empty-guide-preview"/s);
});

test("overview keeps upload module below the command deck with explicit expansion state", () => {
  assert.match(overviewViewSource, /<SeedUploadPanel[\s\S]*:initially-expanded="uploadModuleExpanded"/s);
  assert.match(overviewViewSource, /<SeedAnalysisPanel/s);
});

test("pipeline visualization supports a compact rail mode for the focus card", () => {
  assert.match(pipelineSource, /compact:\s*\{\s*type:\s*Boolean,\s*default:\s*false\s*\}/s);
  assert.match(pipelineSource, /class="pipeline-flow compact"/s);
  assert.match(pipelineSource, /class="pipeline-summary-pill"/s);
});
