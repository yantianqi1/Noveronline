import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("LLM module bindings panel supports accordion, search, multi-select, and scoped batch binding", async () => {
  const panel = await readFile(path.join(root, "components/llm-module-bindings-panel.tsx"), "utf8");
  const shell = await readFile(path.join(root, "components/llm-facility-shell.tsx"), "utf8");
  const page = await readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx"), "utf8");

  assert.match(panel, /batchBindModuleAction/);
  assert.match(panel, /bindModuleAction/);
  assert.match(panel, /clearBindingAction/);
  assert.match(panel, /channelModels/);
  assert.match(panel, /llm-bindings-accordion/);
  assert.match(panel, /llm-bindings-group-summary/);
  assert.match(panel, /searchQuery|type="search"/);
  assert.match(panel, /filterMode|missing-limit/);
  assert.match(panel, /selectedKeys|type="checkbox"/);
  assert.match(panel, /全选本组|Select group/);
  assert.match(panel, /应用到所选|Apply to selected/);
  assert.match(panel, /应用到本组|Apply to group/);
  assert.match(panel, /应用到全部|Apply to all/);
  assert.match(panel, /一键补全输出上限|Fill output limits/);
  assert.match(panel, /name="scope"/);
  assert.match(panel, /name="moduleKeys"/);
  assert.match(panel, /name="maxTokens"/);
  assert.match(panel, /SUGGESTED_MAX_TOKENS|12800/);
  assert.match(panel, /data-sticky="true"/);
  assert.match(panel, /缺输出上限|Missing output limit/);
  assert.doesNotMatch(panel, /全部绑定|Bind all/);
  assert.doesNotMatch(panel, /max_tokens=/);
  assert.doesNotMatch(panel, /Load models|加载模型/);

  assert.match(shell, /canManageBindings/);
  assert.match(shell, /settingsNumberDisplay\(item\.settings, "max_tokens"\)/);

  assert.match(page, /bindingFailureMessage/);
  assert.match(page, /moduleBindingSettingsFromForm/);
  assert.match(page, /settings\.max_tokens/);
  assert.match(page, /resolveBatchTargetModules/);
  assert.match(page, /stringListFromFormData/);
  assert.match(page, /scope === "selected"|scope === "group"|scope === "all"/);
  assert.match(page, /输出上限/);
  assert.doesNotMatch(page, /max_tokens=\$/);
  assert.match(page, /humanizeFailure/);
});

test("LLM facility models table supports context_window editing", async () => {
  const shell = await readFile(path.join(root, "components/llm-facility-shell.tsx"), "utf8");
  const page = await readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx"), "utf8");
  const api = await readFile(path.join(root, "lib/api.ts"), "utf8");

  assert.match(shell, /updateModelAction/);
  assert.match(shell, /contextWindow/);
  assert.match(shell, /保存模型设置|Save model settings/);
  assert.match(page, /updateLLMChannelModel/);
  assert.match(page, /updateModelAction/);
  assert.match(api, /updateLLMChannelModel/);
  assert.match(api, /context_window/);
});
