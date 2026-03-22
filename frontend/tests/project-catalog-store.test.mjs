import test from "node:test";
import assert from "node:assert/strict";

import { createProjectCatalogStore } from "../src/composables/useProjectCatalog.js";

test("refreshProjects updates projects and latestProject from loader", async () => {
  const limits = [];
  const store = createProjectCatalogStore(async (limit) => {
    limits.push(limit);
    return {
      data: [
        { project_id: "proj_new", name: "第二卷", status: "ontology_generated" },
        { project_id: "proj_old", name: "第一卷", status: "created" },
      ],
    };
  });

  await store.refreshProjects(30);

  assert.deepEqual(limits, [30]);
  assert.equal(store.projects.value.length, 2);
  assert.equal(store.latestProject.value?.project_id, "proj_new");
});

test("refreshProjects reuses the last limit when no limit is passed", async () => {
  const limits = [];
  const responses = [
    [{ project_id: "proj_b", name: "第二卷", status: "ontology_generated" }],
    [{ project_id: "proj_a", name: "第一卷", status: "created" }],
  ];
  const store = createProjectCatalogStore(async (limit) => {
    limits.push(limit);
    return { data: responses.shift() || [] };
  });

  await store.refreshProjects(50);
  await store.refreshProjects();

  assert.deepEqual(limits, [50, 50]);
  assert.equal(store.latestProject.value?.project_id, "proj_a");
});

test("refreshProjects falls back to the next latest project after deletion refresh", async () => {
  const responses = [
    [
      { project_id: "proj_latest", name: "第二卷", status: "ontology_generated" },
      { project_id: "proj_next", name: "第一卷", status: "created" },
    ],
    [{ project_id: "proj_next", name: "第一卷", status: "created" }],
    [],
  ];
  const store = createProjectCatalogStore(async () => ({
    data: responses.shift() || [],
  }));

  await store.refreshProjects(30);
  assert.equal(store.latestProject.value?.project_id, "proj_latest");

  await store.refreshProjects();
  assert.equal(store.latestProject.value?.project_id, "proj_next");

  await store.refreshProjects();
  assert.equal(store.latestProject.value, null);
});
