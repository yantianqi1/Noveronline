import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  loadRunnerConfig,
  mergeFixtureEnv,
  runLiveSeedHarness,
} from "../scripts/run-live-seed-harness.mjs";

const completeEnv = {
  MIROFISH_WEB_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:3888",
  MIROFISH_WEB_LIVE_SEED_TENANT_ID: "tenant-live",
  MIROFISH_WEB_LIVE_SEED_PROJECT_ID: "project-live",
  MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE: "api-secret-session",
  MIROFISH_WEB_LIVE_SEED_ALLOW_MUTATION: "1",
  MIROFISH_WEB_LIVE_SEED_THROWAWAY_PROJECT: "1",
  MIROFISH_WEB_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway-live",
  MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL: "http://localhost:3999",
  MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:3888",
  MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID: "tenant-live",
  MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID: "project-live",
  MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE: "browser-secret-session",
  MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION: "1",
  MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT: "1",
  MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway-live",
};

test("live Seed runner fails loud on partial env without leaking values", () => {
  assert.throws(
    () => loadRunnerConfig({
      env: {
        MIROFISH_WEB_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:3888",
        MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE: "secret-session",
      },
      argv: ["--mode", "api"],
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_TENANT_ID/);
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_PROJECT_ID/);
      assert.doesNotMatch(error.message, /secret-session|127\.0\.0\.1:3888/);
      return true;
    },
  );
});

test("live Seed runner checks local services before invoking existing live tests", async () => {
  const fetches = [];
  const commands = [];
  const result = await runLiveSeedHarness({
    env: completeEnv,
    argv: ["--mode", "both"],
    fetchImpl: async (url) => {
      fetches.push(url);
      return { ok: true, status: 200 };
    },
    runCommand: (command, args, options) => {
      commands.push({ command, args, options });
      return { ok: true, status: 0 };
    },
  });

  assert.deepEqual(fetches, [
    "http://127.0.0.1:3888/healthz",
    "http://localhost:3999/",
  ]);
  assert.equal(commands.length, 1);
  assert.equal(commands[0].command, process.execPath);
  assert.deepEqual(commands[0].args, [
    "--test",
    "tests/seed-upload-live.test.mjs",
    "tests/seed-upload-browser-live.test.mjs",
  ]);
  assert.equal(commands[0].options.env.MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE, "api-secret-session");
  assert.equal(commands[0].options.env.MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE, "browser-secret-session");
  assert.match(result.output, /live Seed service preflight passed/);
  assert.match(result.output, /live Seed harness tests passed/);
  assert.doesNotMatch(result.output, /api-secret-session|browser-secret-session/);
});

test("live Seed runner preflights each distinct API base URL before invoking tests", async () => {
  const fetches = [];
  const commands = [];
  await runLiveSeedHarness({
    env: {
      ...completeEnv,
      MIROFISH_WEB_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:3888",
      MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://localhost:3889",
    },
    argv: ["--mode", "both"],
    fetchImpl: async (url) => {
      fetches.push(url);
      return { ok: true, status: 200 };
    },
    runCommand: (command, args, options) => {
      commands.push({ command, args, options });
      return { ok: true, status: 0 };
    },
  });

  assert.deepEqual(fetches, [
    "http://127.0.0.1:3888/healthz",
    "http://localhost:3889/healthz",
    "http://localhost:3999/",
  ]);
  assert.equal(commands.length, 1);
});

test("live Seed runner does not invoke tests when preflight fails", async () => {
  await assert.rejects(
    () => runLiveSeedHarness({
      env: completeEnv,
      argv: ["--mode", "api"],
      fetchImpl: async () => ({
        ok: false,
        status: 503,
        text: async () => "mirofish_session=secret prompt provider_response object_key draft manuscript",
      }),
      runCommand: () => assert.fail("live tests must not run after failed preflight"),
    }),
    (error) => {
      assert.match(error.message, /Go API health preflight failed/);
      assert.match(error.message, /HTTP 503/);
      assert.doesNotMatch(error.message, /secret|prompt|provider|object_key|draft|manuscript/);
      return true;
    },
  );
});

test("live Seed runner passes only required harness env to child tests", async () => {
  const commands = [];
  await runLiveSeedHarness({
    env: {
      ...completeEnv,
      DATABASE_URL: "postgres://secret-database-url",
      OPENAI_API_KEY: "sk-secret-provider-key",
      ANTHROPIC_API_KEY: "secret-provider-key",
      LLM_CREDENTIAL_ENCRYPTION_KEY: "secret-encryption-key",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "fixture-secret",
    },
    argv: ["--mode", "api"],
    fetchImpl: async () => ({ ok: true, status: 200 }),
    runCommand: (command, args, options) => {
      commands.push({ command, args, options });
      return { ok: true, status: 0 };
    },
  });

  assert.equal(commands.length, 1);
  assert.equal(commands[0].options.env.MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE, "api-secret-session");
  assert.equal(commands[0].options.env.MIROFISH_WEB_LIVE_SEED_PROJECT_ID, "project-live");
  assert.equal(commands[0].options.env.NODE_ENV, "test");
  assert.equal(commands[0].options.env.DATABASE_URL, undefined);
  assert.equal(commands[0].options.env.OPENAI_API_KEY, undefined);
  assert.equal(commands[0].options.env.ANTHROPIC_API_KEY, undefined);
  assert.equal(commands[0].options.env.LLM_CREDENTIAL_ENCRYPTION_KEY, undefined);
  assert.equal(commands[0].options.env.MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE, undefined);
});

test("live Seed runner forwards browser worker-retry harness env without ambient secrets", async () => {
  const commands = [];
  await runLiveSeedHarness({
    env: {
      ...completeEnv,
      MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY: "1",
      MIROFISH_WEB_BROWSER_LIVE_SEED_WORKER_RETRY_TIMEOUT_MS: "120000",
      DATABASE_URL: "postgres://secret-database-url",
      OPENAI_API_KEY: "sk-secret-provider-key",
      LLM_CREDENTIAL_ENCRYPTION_KEY: "secret-encryption-key",
    },
    argv: ["--mode", "browser"],
    fetchImpl: async () => ({ ok: true, status: 200 }),
    runCommand: (command, args, options) => {
      commands.push({ command, args, options });
      return { ok: true, status: 0 };
    },
  });

  assert.equal(commands.length, 1);
  assert.equal(commands[0].options.env.MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY, "1");
  assert.equal(commands[0].options.env.MIROFISH_WEB_BROWSER_LIVE_SEED_WORKER_RETRY_TIMEOUT_MS, "120000");
  assert.equal(commands[0].options.env.DATABASE_URL, undefined);
  assert.equal(commands[0].options.env.OPENAI_API_KEY, undefined);
  assert.equal(commands[0].options.env.LLM_CREDENTIAL_ENCRYPTION_KEY, undefined);
});

test("live Seed runner returns redacted config without session or project identifiers", async () => {
  const result = await runLiveSeedHarness({
    env: completeEnv,
    argv: ["--mode", "api"],
    fetchImpl: async () => ({ ok: true, status: 200 }),
    runCommand: () => ({ ok: true, status: 0 }),
  });

  assert.equal(result.config.mode, "api");
  assert.equal(result.config.api.apiBaseUrl, "http://127.0.0.1:3888");
  assert.equal(result.config.api.sessionCookie, "[redacted]");
  assert.equal(result.config.api.tenantId, "[redacted]");
  assert.equal(result.config.api.projectId, "[redacted]");
  assert.equal(result.config.api.disposableProjectMarker, "[redacted]");
  assert.doesNotMatch(JSON.stringify(result.config), /api-secret-session|tenant-live|project-live|throwaway-live/);
});

test("live Seed runner includes bounded redacted child diagnostics on failure", async () => {
  await assert.rejects(
    () => runLiveSeedHarness({
      env: completeEnv,
      argv: ["--mode", "api"],
      fetchImpl: async () => ({ ok: true, status: 200 }),
      runCommand: () => ({
        ok: false,
        status: 1,
        stdout: "public setup line\nmirofish_session=api-secret-session\n",
        stderr: [
          "first line",
          "prompt=hidden",
          "provider=openai",
          "provider_response=raw",
          "content=private",
          "api_key=sk-secret",
          "credential_ref=credential-a",
          "object_key=tenant/project/source.txt",
          "draft manuscript text",
          "final public failure line",
        ].join("\n"),
      }),
    }),
    (error) => {
      assert.match(error.message, /live Seed harness tests failed/);
      assert.match(error.message, /status 1/);
      assert.match(error.message, /child diagnostics/);
      assert.match(error.message, /final public failure line/);
      assert.doesNotMatch(error.message, /api-secret-session|prompt=hidden|provider=openai|provider_response=raw|content=private|sk-secret|credential-a|tenant\/project\/source|draft manuscript/);
      return true;
    },
  );
});

test("live Seed runner can prepare fixture env without printing session values", async () => {
  const commands = [];
  const result = await runLiveSeedHarness({
    env: {
      MIROFISH_WEB_LIVE_SEED_FIXTURE_ALLOW_MUTATION: "1",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_THROWAWAY_PROJECT: "1",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_DISPOSABLE_PROJECT_MARKER: "throwaway-live",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "fixture-secret-session",
    },
    argv: ["--prepare-fixture", "--mode", "api"],
    prepareFixture: async () => ({
      config: {
        apiBaseUrl: "http://127.0.0.1:3888",
        appBaseUrl: "http://localhost:3999",
        tenantId: "tenant-fixture",
        projectId: "project-fixture",
        sessionCookie: "fixture-secret-session",
        disposableProjectMarker: "throwaway-live",
      },
    }),
    fetchImpl: async () => ({ ok: true, status: 200 }),
    runCommand: (command, args, options) => {
      commands.push({ command, args, options });
      return { ok: true, status: 0 };
    },
  });

  assert.equal(commands.length, 1);
  assert.equal(commands[0].options.env.MIROFISH_WEB_LIVE_SEED_TENANT_ID, "tenant-fixture");
  assert.equal(commands[0].options.env.MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE, "fixture-secret-session");
  assert.match(result.output, /fixture env prepared/);
  assert.doesNotMatch(result.output, /fixture-secret-session|tenant-fixture|project-fixture/);
});

test("mergeFixtureEnv emits both API and browser live Seed prefixes", () => {
  const env = mergeFixtureEnv({}, {
    apiBaseUrl: "http://127.0.0.1:3888",
    appBaseUrl: "http://localhost:3999",
    tenantId: "tenant-a",
    projectId: "project-a",
    sessionCookie: "session-a",
    disposableProjectMarker: "throwaway",
  });

  assert.equal(env.MIROFISH_WEB_LIVE_SEED_API_BASE_URL, "http://127.0.0.1:3888");
  assert.equal(env.MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE, "session-a");
  assert.equal(env.MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL, "http://localhost:3999");
  assert.equal(env.MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE, "session-a");
  assert.equal(env.MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION, "1");
});

test("package scripts expose explicit API/browser live Seed runners", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));

  assert.equal(pkg.scripts["test:live-seed:api"], "node scripts/run-live-seed-harness.mjs --mode api");
  assert.equal(pkg.scripts["test:live-seed:browser"], "node scripts/run-live-seed-harness.mjs --mode browser");
  assert.equal(pkg.scripts["test:live-seed"], "node scripts/run-live-seed-harness.mjs --mode both");
});
