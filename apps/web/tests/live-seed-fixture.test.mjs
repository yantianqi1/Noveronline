import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildFixtureSql,
  extractSessionCookie,
  loadFixtureConfig,
  prepareLiveSeedFixture,
  renderShellExports,
} from "../scripts/prepare-live-seed-fixture.mjs";

const baseEnv = {
  MIROFISH_WEB_LIVE_SEED_FIXTURE_ALLOW_MUTATION: "1",
  MIROFISH_WEB_LIVE_SEED_FIXTURE_THROWAWAY_PROJECT: "1",
  MIROFISH_WEB_LIVE_SEED_FIXTURE_DISPOSABLE_PROJECT_MARKER: "throwaway-live-seed",
  MIROFISH_WEB_LIVE_SEED_FIXTURE_API_BASE_URL: "http://127.0.0.1:3888",
  MIROFISH_WEB_LIVE_SEED_FIXTURE_APP_BASE_URL: "http://localhost:3999",
  MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "provided-session-cookie",
};
const encryptedFixtureKey = "aes-256-gcm:v1:ABEiM0RVZneImaq7:1fPg5GknWYe0jXyV7RRMuw==:70sgjI+43MNUJHTpNlJwKNMPxyhr8rJB";

test("fixture SQL upserts disposable auth/project rows without pre-creating sessions", () => {
  const config = loadFixtureConfig({ env: baseEnv, argv: [] });
  const sql = buildFixtureSql(config);

  assert.match(sql, /INSERT INTO users /);
  assert.match(sql, /INSERT INTO tenants /);
  assert.match(sql, /INSERT INTO tenant_memberships /);
  assert.match(sql, /INSERT INTO projects /);
  assert.match(sql, /INSERT INTO project_members /);
  assert.match(sql, /ON CONFLICT/);
  assert.match(sql, /throwaway-live-seed/);
  assert.doesNotMatch(sql, /user_sessions/i);
});

test("fixture exporter emits both API and browser live Seed export prefixes", async () => {
  const result = await prepareLiveSeedFixture({
    env: baseEnv,
    argv: ["--print-sql"],
    fetchImpl: async () => assert.fail("dev session fetch should not run when a session cookie is provided"),
    runPsql: () => assert.fail("psql should not run in print-sql mode"),
  });

  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_API_BASE_URL='http:\/\/127\.0\.0\.1:3888'/);
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_TENANT_ID='/);
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_PROJECT_ID='/);
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE='provided-session-cookie'/);
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_ALLOW_MUTATION='1'/);
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_THROWAWAY_PROJECT='1'/);
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_DISPOSABLE_PROJECT_MARKER='throwaway-live-seed'/);
  assert.match(result.output, /export MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL='http:\/\/localhost:3999'/);
  assert.match(result.output, /export MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL='http:\/\/127\.0\.0\.1:3888'/);
  assert.match(result.output, /export MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE='provided-session-cookie'/);
  assert.match(result.output, /INSERT INTO projects /);
  assert.doesNotMatch(result.output, /user_sessions/i);
});

test("fixture strict opt-in rejects partial disposable mutation flags without echoing values", () => {
  assert.throws(
    () => loadFixtureConfig({
      env: {
        MIROFISH_WEB_LIVE_SEED_FIXTURE_ALLOW_MUTATION: "1",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_API_BASE_URL: "http://127.0.0.1:3888",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "super-secret-session",
      },
      argv: [],
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_THROWAWAY_PROJECT/);
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_DISPOSABLE_PROJECT_MARKER/);
      assert.doesNotMatch(error.message, /super-secret-session|127\.0\.0\.1:3888|ALLOW_MUTATION=1/);
      return true;
    },
  );
});

test("fixture URL guards only allow local http URLs without credentials", () => {
  for (const value of ["https://localhost:3888", "http://example.com:3888", "http://user:pass@localhost:3888", "//localhost:3888"]) {
    assert.throws(
      () => loadFixtureConfig({
        env: {
          ...baseEnv,
          MIROFISH_WEB_LIVE_SEED_FIXTURE_API_BASE_URL: value,
        },
        argv: [],
      }),
      (error) => {
        assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_API_BASE_URL must be a local http URL/);
        assert.doesNotMatch(error.message, /example\.com|user|pass|localhost:3888/);
        return true;
      },
    );
  }
});

test("fixture apply rejects non-local database URLs before psql", async () => {
  await assert.rejects(
    () => prepareLiveSeedFixture({
      env: {
        ...baseEnv,
        MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL: "postgresql://user:secret@example.com:5432/prod",
      },
      argv: ["--apply"],
      fetchImpl: async () => assert.fail("dev session fetch should not run before database URL validation"),
      runPsql: () => assert.fail("psql should not run for non-local database URLs"),
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL must be a local postgres URL/);
      assert.doesNotMatch(error.message, /example\.com|secret|prod|user/);
      return true;
    },
  );
});

test("fixture apply validates session plan before SQL mutation", async () => {
  await assert.rejects(
    () => prepareLiveSeedFixture({
      env: {
        ...baseEnv,
        MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL: "postgresql://127.0.0.1:5432/mirofish",
      },
      argv: ["--apply"],
      fetchImpl: async () => assert.fail("dev session fetch should not run without explicit create flag"),
      runPsql: () => assert.fail("psql should not run before session cookie/create-dev-session preflight"),
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE or MIROFISH_WEB_LIVE_SEED_FIXTURE_CREATE_DEV_SESSION/);
      assert.doesNotMatch(error.message, /127\.0\.0\.1|mirofish/);
      return true;
    },
  );
});

test("fixture apply failure includes sanitized psql diagnostics without database values", async () => {
  await assert.rejects(
    () => prepareLiveSeedFixture({
      env: {
        ...baseEnv,
        MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL: "postgresql://user:secret@localhost:5432/mirofish",
      },
      argv: ["--apply"],
      fetchImpl: async () => assert.fail("dev session fetch should not run when a session cookie is provided"),
      runPsql: () => ({ ok: false, status: 2, signal: "SIGTERM", errorCode: "ENOENT" }),
    }),
    (error) => {
      assert.match(error.message, /psql fixture apply failed/);
      assert.match(error.message, /status 2/);
      assert.match(error.message, /signal SIGTERM/);
      assert.match(error.message, /error ENOENT/);
      assert.doesNotMatch(error.message, /secret|mirofish|localhost|user/);
      return true;
    },
  );
});

test("fixture can apply optional local Seed LLM module bindings without exporting credential material", async () => {
  let appliedSql = "";
  const result = await prepareLiveSeedFixture({
    env: {
      ...baseEnv,
      MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL: "postgresql://user:secret@localhost:5432/mirofish",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_PREPARE_LLM_BINDINGS: "1",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_PROVIDER_BASE_URL: "http://127.0.0.1:48123",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_ENCRYPTED_API_KEY: encryptedFixtureKey,
    },
    argv: ["--apply"],
    fetchImpl: async () => assert.fail("dev session fetch should not run when a session cookie is provided"),
    runPsql: (_databaseUrl, sql) => {
      appliedSql = sql;
      return { ok: true };
    },
  });

  for (const moduleKey of [
    "sequential_reading",
    "anchor_point_summary",
    "story_ontology",
    "entity_resolution",
    "character_agent_profile",
    "narrative_archives",
  ]) {
    assert.match(appliedSql, new RegExp(`'${moduleKey}'`));
  }
  assert.match(appliedSql, /INSERT INTO llm_channels /);
  assert.match(appliedSql, /INSERT INTO llm_models /);
  assert.match(appliedSql, /INSERT INTO llm_module_bindings /);
  assert.match(appliedSql, /ON CONFLICT \(tenant_id, project_id, module_key\) DO UPDATE/);
  assert.match(appliedSql, /LIVE_SEED_LLM_CHANNEL_TENANT_COLLISION/);
  assert.match(appliedSql, /tenant_id <>/);
  assert.match(appliedSql, /aes-256-gcm:v1:ABEiM0RVZneImaq7:1fPg5GknWYe0jXyV7RRMuw==:70sgjI\+43MNUJHTpNlJwKNMPxyhr8rJB/);
  assert.doesNotMatch(result.output, /aes-256-gcm|ABEiM0RVZneImaq7|LLM_ENCRYPTED_API_KEY|sk-/);
});

test("fixture LLM binding preparation requires apply mode to avoid printing encrypted credentials", async () => {
  await assert.rejects(
    () => prepareLiveSeedFixture({
      env: {
        ...baseEnv,
        MIROFISH_WEB_LIVE_SEED_FIXTURE_PREPARE_LLM_BINDINGS: "1",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_PROVIDER_BASE_URL: "http://127.0.0.1:48123",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_ENCRYPTED_API_KEY: encryptedFixtureKey,
      },
      argv: ["--print-sql"],
      fetchImpl: async () => assert.fail("dev session fetch should not run before LLM apply validation"),
      runPsql: () => assert.fail("psql should not run without apply mode"),
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_PREPARE_LLM_BINDINGS requires --apply/);
      assert.doesNotMatch(error.message, /aes-256-gcm|ciphertext|127\.0\.0\.1|48123/);
      return true;
    },
  );
});

test("fixture LLM binding preparation rejects invalid credential envelopes without side effects", async () => {
  for (const encryptedKey of ["", "sk-live-seed-raw", "aes-256-gcm:v1:iv:tag:ciphertext", "aes-256-gcm:v1:AAAA:BBBB:CCCC"]) {
    await assert.rejects(
      () => prepareLiveSeedFixture({
        env: {
          ...baseEnv,
          MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL: "postgresql://user:secret@localhost:5432/mirofish",
          MIROFISH_WEB_LIVE_SEED_FIXTURE_PREPARE_LLM_BINDINGS: "1",
          MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_PROVIDER_BASE_URL: "http://127.0.0.1:48123",
          MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_ENCRYPTED_API_KEY: encryptedKey,
        },
        argv: ["--apply"],
        fetchImpl: async () => assert.fail("dev session fetch should not run before LLM credential validation"),
        runPsql: () => assert.fail("psql should not run with invalid LLM credential configuration"),
      }),
      (error) => {
        assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_ENCRYPTED_API_KEY/);
        assert.doesNotMatch(error.message, /sk-live|secret|localhost|48123/);
        return true;
      },
    );
  }
});

test("fixture LLM binding preparation rejects non-local provider URL before psql", async () => {
  await assert.rejects(
    () => prepareLiveSeedFixture({
      env: {
        ...baseEnv,
        MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL: "postgresql://user:secret@localhost:5432/mirofish",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_PREPARE_LLM_BINDINGS: "1",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_PROVIDER_BASE_URL: "https://provider.example.test",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_ENCRYPTED_API_KEY: encryptedFixtureKey,
      },
      argv: ["--apply"],
      fetchImpl: async () => assert.fail("dev session fetch should not run before LLM provider URL validation"),
      runPsql: () => assert.fail("psql should not run with a non-local LLM provider URL"),
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_PROVIDER_BASE_URL must be a local http URL/);
      assert.doesNotMatch(error.message, /provider\.example|ciphertext|secret/);
      return true;
    },
  );
});

test("fixture can request a dev session and parse mirofish_session from Set-Cookie", async () => {
  const calls = [];
  const result = await prepareLiveSeedFixture({
    env: {
      ...baseEnv,
      MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "",
      MIROFISH_WEB_LIVE_SEED_FIXTURE_CREATE_DEV_SESSION: "1",
    },
    argv: [],
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return {
        ok: true,
        status: 201,
        headers: {
          get(name) {
            if (name.toLowerCase() !== "set-cookie") {
              return null;
            }
            return "other=value; Path=/, mirofish_session=session-from-set-cookie; Path=/; HttpOnly; SameSite=Lax";
          },
        },
      };
    },
    runPsql: () => ({ ok: true }),
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:3888/v1/auth/dev-sessions");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { user_id: result.config.userId });
  assert.match(result.output, /export MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE='session-from-set-cookie'/);
  assert.match(result.output, /export MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE='session-from-set-cookie'/);
});

test("fixture dev session failures do not leak tokens, raw bodies, keys, or novel text", async () => {
  await assert.rejects(
    () => prepareLiveSeedFixture({
      env: {
        ...baseEnv,
        MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE: "",
        MIROFISH_WEB_LIVE_SEED_FIXTURE_CREATE_DEV_SESSION: "1",
      },
      argv: [],
      fetchImpl: async () => ({
        ok: false,
        status: 500,
        headers: { get: () => null },
        text: async () => "mirofish_session=secret prompt provider_response sk-secret object_key draft manuscript",
      }),
      runPsql: () => ({ ok: true }),
    }),
    (error) => {
      assert.match(error.message, /dev session request failed/);
      assert.doesNotMatch(error.message, /secret|prompt|provider|sk-|object_key|draft|manuscript/);
      return true;
    },
  );
});

test("extractSessionCookie accepts multiple Set-Cookie header shapes", () => {
  assert.equal(
    extractSessionCookie({
      getSetCookie: () => ["theme=light; Path=/", "mirofish_session=session-a; Path=/; HttpOnly"],
    }),
    "session-a",
  );
  assert.equal(
    extractSessionCookie({
      raw: () => ({ "set-cookie": ["mirofish_session=session-b; Path=/"] }),
    }),
    "session-b",
  );
  assert.equal(extractSessionCookie({ get: () => "mirofish_session=session-c; Path=/" }), "session-c");
  assert.equal(extractSessionCookie({ get: () => "theme=light; Path=/" }), "");
});

test("rendered shell exports quote values safely", () => {
  const config = loadFixtureConfig({
    env: {
      ...baseEnv,
      MIROFISH_WEB_LIVE_SEED_FIXTURE_DISPOSABLE_PROJECT_MARKER: "throwaway-'quoted'",
    },
    argv: [],
  });
  const exports = renderShellExports({ ...config, sessionCookie: "cookie-'quoted'" });

  assert.match(exports, /export MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE='cookie-'"'"'quoted'"'"''/);
  assert.match(exports, /export MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER='throwaway-'"'"'quoted'"'"''/);
});
