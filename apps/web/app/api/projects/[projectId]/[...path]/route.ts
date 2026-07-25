import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * Catch-all BFF proxy for project-scoped data.
 *
 * Most routes map `/api/projects/{projectId}/<rest>` → `/v1/projects/{projectId}/<rest>`.
 * The exception is run-scoped Seed routes: the Go API mounts a run's detail,
 * events, cancel, and retry at the TOP level (`/v1/seed-runs/{runId}/...`),
 * not under the project prefix. We translate those here so the browser can use
 * one consistent project-scoped URL shape. An allowlist keeps this from ever
 * becoming an open proxy to arbitrary project mutations.
 */

// Project-prefixed reads/writes (forwarded under /v1/projects/{id}/).
const PROJECT_PATHS: Record<Method, RegExp[]> = {
  GET: [
    /^overview$/,
    /^readiness$/,
    /^source-files$/,
    /^seed-runs$/,
    // LLM settings reads
    /^llm\/modules$/,
    /^llm\/module-bindings$/,
    /^llm\/channels$/,
    /^llm\/channels\/([^/]+)\/models$/,
    // Writer: structure + manuscript workspace reads
    /^chapters$/,
    /^chapters\/([^/]+)$/,
    /^manuscript-workspace\/blocks$/,
    /^manuscript-workspace\/blocks\/([^/]+)$/,
    // Writer: conversation thread
    /^writer-threads$/,
    /^writer-threads\/([^/]+)\/messages$/,
    // Asset library: unified list + facets + search capabilities
    /^assets$/,
    /^assets\/facets$/,
    /^assets\/search-capabilities$/,
    // Asset catalog: detail, versions, collections
    /^asset-catalog\/assets\/([^/]+)$/,
    /^asset-catalog\/assets\/([^/]+)\/versions$/,
    /^asset-catalog\/collections$/,
    // Story graph: current snapshot, viewport, node/edge detail, public evidence, clusters
    /^story-graph\/current$/,
    /^story-graph\/views\/([^/]+)$/,
    /^story-graph\/nodes\/([^/]+)$/,
    /^story-graph\/edges\/([^/]+)$/,
    /^story-graph\/nodes\/([^/]+)\/evidence$/,
    /^story-graph\/edges\/([^/]+)\/evidence$/,
    /^story-graph\/clusters$/,
    // Worldline: list sessions, preparations, goal-starts, saved paths
    /^worldline-sessions$/,
    /^worldlines\/preparations$/,
    /^worldline-goal-starts$/,
    /^worldline\/saved-paths$/,
    // Character console: list interactions
    /^character-interactions$/,
  ],
  POST: [
    /^seed-runs$/,
    // Story graph: start a build (queued; snapshot status flips building → ready/failed)
    /^story-graph\/builds$/,
    // Writer: create chapters + manuscript blocks
    /^chapters$/,
    /^manuscript-workspace\/blocks$/,
    // Writer: ensure thread, append message, start a run
    /^writer-threads$/,
    /^writer-threads\/([^/]+)\/messages$/,
    /^writer-runs$/,
    // Asset catalog: restore a version, create a collection
    /^asset-catalog\/assets\/([^/]+)\/restore$/,
    /^asset-catalog\/collections$/,
    // Worldline: start a session, create a preparation, start a goal-driven run
    /^worldline-sessions$/,
    /^worldlines\/preparations$/,
    /^worldline-goal-starts$/,
    // Character console: create an interaction
    /^character-interactions$/,
  ],
  // LLM module binding overrides (project-scoped) + asset catalog membership
  // add/reorder.
  PUT: [
    /^llm\/module-bindings\/([^/]+)$/,
    /^asset-catalog\/collections\/([^/]+)\/items\/([^/]+)$/,
    /^asset-catalog\/collections\/([^/]+)\/order$/,
  ],
  PATCH: [
    // Writer: rename/reorder chapters, edit manuscript blocks (optimistic lock)
    /^chapters\/([^/]+)$/,
    /^manuscript-workspace\/blocks\/([^/]+)$/,
    // Asset catalog: edit an asset (optimistic lock), rename a collection
    /^asset-catalog\/assets\/([^/]+)$/,
    /^asset-catalog\/collections\/([^/]+)$/,
  ],
  DELETE: [
    /^llm\/module-bindings\/([^/]+)$/,
    /^chapters\/([^/]+)$/,
    /^manuscript-workspace\/blocks\/([^/]+)$/,
    // Source text: delete one imported source file by upload id
    /^source-files\/([^/]+)$/,
    // Asset catalog: delete a collection, remove an asset from it
    /^asset-catalog\/collections\/([^/]+)$/,
    /^asset-catalog\/collections\/([^/]+)\/items\/([^/]+)$/,
  ],
};

// Run/asset-scoped routes that the Go API mounts at the TOP level (not under
// /v1/projects/{id}): Writer runs + drafts, asset detail/adoption, and the
// cross-entity asset search. We keep the browser on one project-scoped URL
// shape and translate here. Keyed by the rest-path prefix.
const TOP_LEVEL_ROUTES: { prefix: RegExp; toGo: (rest: string, query: string) => string }[] = [
  // /api/projects/{id}/writer-runs/{runId}[/events|/cancel] → /v1/writer-runs/{runId}...
  {
    prefix: /^writer-runs\/([^/]+)(\/events|\/cancel)?$/,
    toGo: (rest, query) => {
      const m = rest.match(/^writer-runs\/([^/]+)(\/events|\/cancel)?$/)!;
      return `/v1/writer-runs/${encodeURIComponent(m[1])}${m[2] ?? ""}${query}`;
    },
  },
  // /api/projects/{id}/drafts/{draftId}/adoptions → /v1/drafts/{draftId}/adoptions
  {
    prefix: /^drafts\/([^/]+)\/adoptions$/,
    toGo: (rest, query) => {
      const m = rest.match(/^drafts\/([^/]+)\/adoptions$/)!;
      return `/v1/drafts/${encodeURIComponent(m[1])}/adoptions${query}`;
    },
  },
  // /api/projects/{id}/assets/search → /v1/assets/search (POST body carries project_id)
  {
    prefix: /^assets\/search$/,
    toGo: (_rest, query) => `/v1/assets/search${query}`,
  },
  // /api/projects/{id}/assets/{assetId}[/adoptions] → /v1/assets/{assetId}[/adoptions]
  // The (?!facets|search-capabilities) guard keeps the project-scoped reserved
  // reads (facets / search-capabilities) out of the asset-detail capture so they
  // fall through to the PROJECT_PATHS project list below; otherwise "facets"
  // would be swallowed as an asset id and the Go detail route would 404.
  {
    prefix: /^assets\/(?!facets$|search-capabilities$)([^/]+)(\/adoptions)?$/,
    toGo: (rest, query) => {
      const m = rest.match(/^assets\/(?!facets$|search-capabilities$)([^/]+)(\/adoptions)?$/)!;
      return `/v1/assets/${encodeURIComponent(m[1])}${m[2] ?? ""}${query}`;
    },
  },
  // Worldline run-scoped routes mount at the TOP level (not under /projects).
  // /api/projects/{id}/worldline-sessions/{sessionId}[/timeline|/events|/steps|/auto-evolutions|/variables|/saved-paths]
  //   → /v1/worldline-sessions/{sessionId}[...]
  {
    prefix: /^worldline-sessions\/([^/]+)(\/timeline|\/events|\/steps|\/auto-evolutions|\/variables|\/saved-paths)?$/,
    toGo: (rest, query) => {
      const m = rest.match(/^worldline-sessions\/([^/]+)(\/timeline|\/events|\/steps|\/auto-evolutions|\/variables|\/saved-paths)?$/)!;
      return `/v1/worldline-sessions/${encodeURIComponent(m[1])}${m[2] ?? ""}${query}`;
    },
  },
  // /api/projects/{id}/worldline-preparations/{prepareId}[/agents] → /v1/worldline-preparations/{prepareId}[/agents]
  {
    prefix: /^worldline-preparations\/([^/]+)(\/agents)?$/,
    toGo: (rest, query) => {
      const m = rest.match(/^worldline-preparations\/([^/]+)(\/agents)?$/)!;
      return `/v1/worldline-preparations/${encodeURIComponent(m[1])}${m[2] ?? ""}${query}`;
    },
  },
  // /api/projects/{id}/worldline-events/{eventId}[/adoptions] → /v1/worldline-events/{eventId}[/adoptions]
  {
    prefix: /^worldline-events\/([^/]+)(\/adoptions)?$/,
    toGo: (rest, query) => {
      const m = rest.match(/^worldline-events\/([^/]+)(\/adoptions)?$/)!;
      return `/v1/worldline-events/${encodeURIComponent(m[1])}${m[2] ?? ""}${query}`;
    },
  },
  // /api/projects/{id}/worldline-goal-starts/{runId} → /v1/worldline-goal-starts/{runId}
  {
    prefix: /^worldline-goal-starts\/([^/]+)$/,
    toGo: (rest, query) => {
      const m = rest.match(/^worldline-goal-starts\/([^/]+)$/)!;
      return `/v1/worldline-goal-starts/${encodeURIComponent(m[1])}${query}`;
    },
  },
  // Character console run-scoped routes mount at the TOP level too. The deep
  // proposal-adoption path must be matched BEFORE the generic nested rule below,
  // otherwise the generic one stops at "/proposals" and drops the rest.
  // /api/projects/{id}/character-interactions/{interactionId}/proposals/{assetId}/adoptions
  //   → /v1/character-interactions/{interactionId}/proposals/{assetId}/adoptions
  {
    prefix: /^character-interactions\/([^/]+)\/proposals\/([^/]+)\/adoptions$/,
    toGo: (rest, query) => {
      const m = rest.match(/^character-interactions\/([^/]+)\/proposals\/([^/]+)\/adoptions$/)!;
      return `/v1/character-interactions/${encodeURIComponent(m[1])}/proposals/${encodeURIComponent(m[2])}/adoptions${query}`;
    },
  },
  // /api/projects/{id}/character-interactions/{interactionId}[/turns|/events|/dialogue|/proposals|/chapter-drafts]
  //   → /v1/character-interactions/{interactionId}[...]
  {
    prefix: /^character-interactions\/([^/]+)(\/turns|\/events|\/dialogue|\/proposals|\/chapter-drafts)?$/,
    toGo: (rest, query) => {
      const m = rest.match(/^character-interactions\/([^/]+)(\/turns|\/events|\/dialogue|\/proposals|\/chapter-drafts)?$/)!;
      return `/v1/character-interactions/${encodeURIComponent(m[1])}${m[2] ?? ""}${query}`;
    },
  },
];

// Run-scoped Seed routes (forwarded to TOP-level /v1/seed-runs/{runId}/...).
const RUN_PATHS: Partial<Record<Method, RegExp[]>> = {
  GET: [/^seed-runs\/([^/]+)$/, /^seed-runs\/([^/]+)\/events$/],
  POST: [/^seed-runs\/([^/]+)\/cancel$/, /^seed-runs\/([^/]+)\/retry$/],
};

function matchAny(patterns: RegExp[], rest: string): RegExpMatchArray | null {
  for (const pattern of patterns) {
    const match = rest.match(pattern);
    if (match) return match;
  }
  return null;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

async function handle(
  request: Request,
  context: { params: Promise<{ projectId: string; path?: string[] }> },
) {
  const { projectId, path } = await context.params;
  const rest = (path ?? []).join("/");
  const method = request.method.toUpperCase() as Method;

  if (
    method !== "GET" &&
    method !== "POST" &&
    method !== "PUT" &&
    method !== "PATCH" &&
    method !== "DELETE"
  ) {
    return Response.json({ error: { code: "NOT_FOUND", message: "未知的项目接口" } }, { status: 404 });
  }

  const url = new URL(request.url);
  const query = url.search; // includes leading "?" when present

  // Resolve the upstream Go path. Order matters: run-scoped Seed routes, then
  // top-level routes (Writer runs/drafts, asset detail + search), then plain
  // project routes — so "assets/search" and "assets/{id}" never fall through to
  // the project assets list.
  let goPath: string | null = null;

  const runMatch = matchAny(RUN_PATHS[method] ?? [], rest);
  if (runMatch) {
    const runId = runMatch[1];
    const suffix = rest.slice(`seed-runs/${runId}`.length); // "", "/events", "/cancel", "/retry"
    goPath = `/v1/seed-runs/${encodeURIComponent(runId)}${suffix}${query}`;
  } else {
    const topLevel = TOP_LEVEL_ROUTES.find((r) => r.prefix.test(rest));
    if (topLevel) {
      goPath = topLevel.toGo(rest, query);
    } else if (matchAny(PROJECT_PATHS[method] ?? [], rest)) {
      goPath = `/v1/projects/${encodeURIComponent(projectId)}/${rest}${query}`;
    }
  }

  if (!goPath) {
    return Response.json({ error: { code: "NOT_FOUND", message: "未知的项目接口" } }, { status: 404 });
  }

  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
  }

  let body: unknown;
  if (method !== "GET") {
    try {
      body = await request.json();
    } catch {
      body = undefined; // empty body is fine for cancel/retry and most deletes
    }
  }

  // The cross-entity asset search is a top-level POST whose body must carry the
  // project id; the browser only knows the URL shape, so inject it here.
  if (method === "POST" && rest === "assets/search") {
    body = { ...(typeof body === "object" && body !== null ? body : {}), project_id: projectId };
  }

  try {
    const result = await proxyToApi({ path: goPath, method, body, request, tenantId });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
