import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("LLM module bindings panel supports flat table, group chips, search, multi-select, and scoped batch binding", async () => {
  const panel = await readFile(path.join(root, "components/llm-module-bindings-panel.tsx"), "utf8");
  const shell = await readFile(path.join(root, "components/llm-facility-shell.tsx"), "utf8");
  const page = await readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx"), "utf8");

  assert.match(panel, /batchBindModuleAction/);
  assert.match(panel, /bindModuleAction/);
  assert.match(panel, /clearBindingAction/);
  assert.match(panel, /channelModels/);
  assert.match(panel, /llm-bindings-group-chips/);
  assert.match(panel, /llm-bindings-group-chip/);
  assert.match(panel, /groupFilterId/);
  assert.match(panel, /filteredModules/);
  assert.match(panel, /searchQuery|type="search"/);
  assert.match(panel, /filterMode/);
  assert.match(panel, /selectedKeys|type="checkbox"/);
  assert.match(panel, /全选当前列表|Select visible list/);
  assert.match(panel, /应用到所选|Apply to selected/);
  assert.match(panel, /应用到本组|Apply to group/);
  assert.match(panel, /应用到全部|Apply to all/);
  assert.match(panel, /primaryBatchScope/);
  assert.match(panel, /handleBatchApply|optimisticBind/);
  assert.match(panel, /preferredBatchSelection/);
  assert.match(panel, /useTransition/);
  assert.match(panel, /name="maxTokens"/);
  assert.match(panel, /SUGGESTED_MAX_TOKENS|12800/);
  assert.match(panel, /data-sticky="true"/);
  assert.match(panel, /is-highlight|llm-bindings-feedback/);
  assert.match(panel, /llm-bindings-module-list/);
  assert.match(panel, /模块绑定列表|Module binding list/);
  // Compact author surface: no per-row status / output / default restore clutter.
  assert.doesNotMatch(panel, /输出上限|Output limit/);
  assert.doesNotMatch(panel, /项目已绑定|Project bound/);
  assert.doesNotMatch(panel, /缺输出上限|Missing output limit/);
  assert.doesNotMatch(panel, /补全输出上限|Fill output limits/);
  assert.doesNotMatch(panel, /恢复所选默认|Restore selected defaults/);
  assert.doesNotMatch(panel, />\s*<Bi zh="默认" en="Default" \/>/);
  assert.doesNotMatch(panel, /一张表管理全部模块绑定/);
  assert.doesNotMatch(panel, /llm-bindings-accordion/);
  assert.doesNotMatch(panel, /全部绑定|Bind all/);
  assert.doesNotMatch(panel, /max_tokens=/);
  assert.doesNotMatch(panel, /Load models|加载模型/);
  assert.doesNotMatch(panel, /redirect\(/);
  // Batch toolbar must not always reset to models[0] after refresh.
  assert.doesNotMatch(
    panel,
    /useState\(\(\) => \(\s*channelModels\[channels\[0\]\?\.channel_id \|\| ""\]\?\.\[0\]\?\.model_id/,
  );

  assert.match(shell, /canManageBindings/);
  assert.match(shell, /settingsNumberDisplay\(item\.settings, "max_tokens"\)/);
  assert.match(shell, /LLMBindingActionResult/);

  assert.match(page, /bindingFailureMessage/);
  assert.match(page, /moduleBindingSettingsFromForm/);
  assert.match(page, /settings\.max_tokens/);
  assert.match(page, /resolveBatchTargetModules/);
  assert.match(page, /stringListFromFormData/);
  assert.match(page, /scope === "selected"|scope === "group"|scope === "all"/);
  assert.match(page, /LLMBindingActionResult/);
  assert.match(page, /appliedModuleKeys/);
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
