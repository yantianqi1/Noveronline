const disposableDatabaseName = /^mirofish_test_[a-z0-9_]+$/;
const allowedQueryParameters = new Set(["application_name", "connect_timeout", "sslmode"]);

export function disposableLiveDatabaseConfig(environment = process.env) {
  const admin = parseDisposableDatabaseUrl(environment.MIROFISH_LIVE_TEST_DATABASE_URL, "admin");
  const runtime = parseDisposableDatabaseUrl(environment.MIROFISH_LIVE_TEST_RUNTIME_DATABASE_URL, "runtime");
  const composeProject = environment.MIROFISH_LIVE_TEST_COMPOSE_PROJECT?.trim() ?? "";
  if (admin.database !== runtime.database) throw new Error("live test database URLs target different databases");
  if (!/^mirofish-saas-live-[a-z0-9_-]+$/.test(composeProject)) {
    throw new Error("live test Compose project is not disposable");
  }
  return {
    adminUrl: admin.url,
    runtimeUrl: runtime.url,
    database: admin.database,
    adminUser: admin.username,
    composeProject,
  };
}

export function parseDisposableDatabaseUrl(rawValue, label = "live test") {
  const value = rawValue?.trim() ?? "";
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${label} database URL is invalid`);
  }
  if (!new Set(["postgres:", "postgresql:"]).has(url.protocol)) {
    throw new Error(`${label} database URL must use PostgreSQL`);
  }
  if (!new Set(["127.0.0.1", "localhost", "[::1]"]).has(url.hostname)) {
    throw new Error(`${label} database URL must use a loopback host`);
  }
  for (const key of url.searchParams.keys()) {
    if (!allowedQueryParameters.has(key.toLowerCase())) {
      throw new Error(`${label} database URL contains a routing override`);
    }
  }
  const database = decodeURIComponent(url.pathname.replace(/^\/+/, "")).toLowerCase();
  if (!disposableDatabaseName.test(database)) {
    throw new Error(`${label} database URL does not target a disposable database`);
  }
  return { url: value, database, username: decodeURIComponent(url.username) };
}
