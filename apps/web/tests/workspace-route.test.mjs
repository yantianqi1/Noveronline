import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isInternalWorkspaceSegment,
  internalWorkspaceSection,
  matchesWorkspaceNavigationPath,
  projectPublicKey,
  publicWorkspaceSection,
  resolvePublicWorkspaceRoute,
  resolveProjectPublicKey,
  resolveWorkspaceKey,
  workspaceKeyFromIds,
  workspaceIdFromPublicSegment,
  workspacePathForProject,
} from "../lib/workspace-route.ts";

const tenants = [
  { tenant_id: "10000000-0000-0000-0000-000000000101", name: "MiroFish Studio" },
];
const projects = [
  {
    tenant_id: tenants[0].tenant_id,
    project_id: "10000000-0000-0000-0000-000000000201",
    name: "长篇小说计划",
  },
];

test("workspace routes expose a 12-character project key instead of names and UUIDs", () => {
  const path = workspacePathForProject(tenants, projects[0], "/overview");
  assert.match(path, /^\/p\/[a-z0-9]{12}$/);
  assert.doesNotMatch(path, /0000-0000-0000/);
  assert.doesNotMatch(path, /mirofish|小说|projects/);
  assert.equal(path.split("/")[2], projectPublicKey(projects[0].project_id));
  assert.equal(isInternalWorkspaceSegment(tenants[0].tenant_id), true);
  assert.equal(isInternalWorkspaceSegment(path.split("/")[2]), false);
  assert.equal(
    workspaceIdFromPublicSegment("old-studio-name-10000000000000000000000000000101"),
    tenants[0].tenant_id,
  );
});

test("workspace keys keep projects unambiguous without exposing their labels", () => {
  assert.notEqual(
    projectPublicKey("11111111-0000-0000-0000-000000000001"),
    projectPublicKey("22222222-0000-0000-0000-000000000002"),
  );
});

test("workspace page aliases stay short and round-trip to internal routes", () => {
  assert.equal(publicWorkspaceSection("overview"), "");
  assert.equal(publicWorkspaceSection("llm-facility"), "llm");
  assert.equal(publicWorkspaceSection("character-console"), "characters");
  assert.equal(publicWorkspaceSection("llm-facility/quotas"), "llm/quotas");
  assert.equal(publicWorkspaceSection("materials"), "materials");
  assert.equal(publicWorkspaceSection("me"), "me");
  assert.equal(internalWorkspaceSection(""), "overview");
  assert.equal(internalWorkspaceSection("llm"), "llm-facility");
  assert.equal(internalWorkspaceSection("characters"), "character-console");
  assert.equal(internalWorkspaceSection("materials"), "materials");
  assert.equal(internalWorkspaceSection("me"), "me");
});

test("workspace navigation stays active across public URLs and server rewrites", () => {
  const overviewHref = workspacePathForProject(tenants, projects[0], "overview");
  const assetsHref = workspacePathForProject(tenants, projects[0], "assets");
  const internalBase = `/${tenants[0].tenant_id}/projects/${projects[0].project_id}`;

  assert.equal(matchesWorkspaceNavigationPath(overviewHref, overviewHref, "/overview"), true);
  assert.equal(matchesWorkspaceNavigationPath(`${internalBase}/overview`, overviewHref, "/overview"), true);
  assert.equal(matchesWorkspaceNavigationPath(`${assetsHref}/asset-1`, assetsHref, "/assets"), true);
  assert.equal(matchesWorkspaceNavigationPath(`${internalBase}/assets/asset-1`, assetsHref, "/assets"), true);
  assert.equal(matchesWorkspaceNavigationPath(`${internalBase}/writer`, assetsHref, "/assets"), false);
});

test("public workspace routes resolve only through active membership data", () => {
  const path = workspacePathForProject(tenants, projects[0], "writer");
  const publicKey = path.split("/")[2];
  assert.deepEqual(resolveProjectPublicKey(tenants, projects, publicKey), {
    ...projects[0],
    tenant: tenants[0],
  });
  const legacyWorkspaceKey = workspaceKeyFromIds(tenants[0].tenant_id, projects[0].project_id);
  assert.deepEqual(resolveWorkspaceKey(tenants, projects, legacyWorkspaceKey), {
    ...projects[0],
    tenant: tenants[0],
  });
  assert.deepEqual(
    resolvePublicWorkspaceRoute(
      tenants,
      projects,
      "old-tenant-10000000000000000000000000000101",
      "old-project-10000000000000000000000000000201",
    ),
    { ...projects[0], tenant: tenants[0] },
  );
  assert.equal(resolveProjectPublicKey(tenants, projects, "unknown"), undefined);
});

test("renamed workspaces keep resolving through their stable short identifiers", () => {
  assert.deepEqual(
    resolvePublicWorkspaceRoute(
      tenants,
      projects,
      "old-studio-name-10000000000000000000000000000101",
      "old-project-name-10000000000000000000000000000201",
    ),
    { ...projects[0], tenant: tenants[0] },
  );
});
