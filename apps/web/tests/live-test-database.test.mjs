import assert from "node:assert/strict";
import test from "node:test";

import { disposableLiveDatabaseConfig, parseDisposableDatabaseUrl } from "../scripts/live-test-database.mjs";

test("disposable live database config accepts only an isolated stack", () => {
  const config = disposableLiveDatabaseConfig({
    MIROFISH_LIVE_TEST_DATABASE_URL: "postgresql://admin@127.0.0.1:55432/mirofish_test_123_456?sslmode=disable",
    MIROFISH_LIVE_TEST_RUNTIME_DATABASE_URL: "postgresql://runtime@localhost:55432/mirofish_test_123_456?application_name=mirofish-live-test",
    MIROFISH_LIVE_TEST_COMPOSE_PROJECT: "mirofish-saas-live-123_456",
  });
  assert.equal(config.database, "mirofish_test_123_456");
  assert.equal(config.adminUser, "admin");
});

test("runtime database and libpq routing overrides fail closed", () => {
  assert.throws(() => parseDisposableDatabaseUrl("postgresql://admin@localhost/mirofish"), /disposable/);
  assert.throws(
    () => parseDisposableDatabaseUrl("postgresql://admin@localhost/mirofish_test_123?hostaddr=203.0.113.10"),
    /routing override/,
  );
  assert.throws(
    () => disposableLiveDatabaseConfig({
      MIROFISH_LIVE_TEST_DATABASE_URL: "postgresql://admin@localhost/mirofish_test_123",
      MIROFISH_LIVE_TEST_RUNTIME_DATABASE_URL: "postgresql://runtime@localhost/mirofish_test_456",
      MIROFISH_LIVE_TEST_COMPOSE_PROJECT: "mirofish-saas-live-123",
    }),
    /different databases/,
  );
});
