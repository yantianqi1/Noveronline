import { cookies } from "next/headers";

import { apiBaseUrl } from "@/lib/config";
import { signTrustedClientProof } from "@/lib/server/client-proof";

/**
 * Server-side proxy into the Go control plane.
 *
 * Every browser request for workspace data hits a same-origin Next Route
 * Handler, which calls `proxyToApi`. We forward the `mirofish_session` cookie
 * (so the browser never deals with CORS), re-attach the CSRF token the client
 * echoed back to us, sign the trusted-client proof when a secret is present,
 * and relay the upstream status/body verbatim. The secret and the upstream
 * origin never leave the server.
 */

const SESSION_COOKIE = "mirofish_session";
const CSRF_HEADER = "X-CSRF-Token";
const TENANT_HEADER = "X-Tenant-Id";
const REQUEST_ID_HEADER = "X-Request-Id";

export class UpstreamUnavailableError extends Error {
  constructor() {
    super("upstream unavailable");
    this.name = "UpstreamUnavailableError";
  }
}

type ProxyOptions = {
  /** Go path beginning with /v1, e.g. "/v1/me". May include a query string. */
  path: string;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON body for mutating requests (serialized). Ignored when rawBody is set. */
  body?: unknown;
  /**
   * Raw body for non-JSON payloads (e.g. the source-object PUT). Sent as-is
   * with the given contentType instead of JSON-serializing `body`.
   */
  rawBody?: ArrayBuffer | Uint8Array | null;
  contentType?: string;
  /** Incoming request — used to resolve client IP and echo the CSRF token. */
  request: Request;
  /** Tenant scope to forward as X-Tenant-Id, when the client supplied one. */
  tenantId?: string | null;
};

export type ProxyResult = {
  status: number;
  body: string;
  contentType: string;
  /** Set-Cookie headers from upstream (login/logout), relayed to the browser. */
  setCookies: string[];
};

function resolveClientIp(request: Request): string {
  return (
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    request.headers.get("x-real-ip")?.trim() ||
    "127.0.0.1"
  );
}

/** Server-side idempotency key when the caller didn't supply one. */
function mintRequestId(): string {
  return `bff-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export async function proxyToApi(options: ProxyOptions): Promise<ProxyResult> {
  const { path, method = "GET", body, rawBody, contentType, request, tenantId } = options;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  // Forward the session cookie so the Go API can authenticate us.
  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE);
  if (session?.value) {
    headers.Cookie = `${SESSION_COOKIE}=${session.value}`;
  }

  // Mutating requests must carry the CSRF token the browser echoes back.
  if (method !== "GET") {
    const csrf = request.headers.get(CSRF_HEADER);
    if (csrf) {
      headers[CSRF_HEADER] = csrf;
    }
    // The Go control plane requires an idempotency key (X-Request-Id) on
    // launch/mutation routes — e.g. every manuscript-workspace write validates
    // it as part of the request scope. Forward the client's key when present,
    // otherwise mint one server-side so the requirement always holds.
    const incoming = request.headers.get(REQUEST_ID_HEADER)?.trim();
    headers[REQUEST_ID_HEADER] = incoming && incoming.length > 0 ? incoming : mintRequestId();
  }

  if (tenantId) {
    headers[TENANT_HEADER] = tenantId;
  }

  // Attach the trusted-client proof when the platform requires it.
  const proof = signTrustedClientProof(resolveClientIp(request));
  if (proof) {
    headers["X-Mirofish-Recovery-Client"] = proof;
  }

  // Choose the payload: a raw body (file bytes) wins over a JSON body.
  let payload: BodyInit | undefined;
  if (rawBody !== undefined && rawBody !== null) {
    // Normalize to a fresh ArrayBuffer so the BodyInit type is unambiguous
    // (typed-array .buffer may be a SharedArrayBuffer, which BodyInit rejects).
    const bytes = rawBody instanceof ArrayBuffer ? new Uint8Array(rawBody) : rawBody;
    const copy = new Uint8Array(bytes.byteLength);
    copy.set(bytes);
    payload = copy.buffer;
    headers["Content-Type"] = contentType ?? "application/octet-stream";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      headers,
      body: payload,
      cache: "no-store",
    });
  } catch {
    throw new UpstreamUnavailableError();
  }

  const text = await upstream.text();
  const setCookies =
    typeof upstream.headers.getSetCookie === "function"
      ? upstream.headers.getSetCookie()
      : [upstream.headers.get("set-cookie")].filter((v): v is string => Boolean(v));

  return {
    status: upstream.status,
    body: text,
    contentType: upstream.headers.get("Content-Type") ?? "application/json",
    setCookies,
  };
}

/** Turn a ProxyResult into a Response the browser understands. */
export function toResponse(result: ProxyResult): Response {
  const headers = new Headers({ "Content-Type": result.contentType });
  for (const cookie of result.setCookies) {
    headers.append("set-cookie", cookie);
  }
  // 204/205/304 carry no body by definition — undici throws "Invalid response
  // status code" if you hand `new Response()` a (even empty-string) body with
  // one of these statuses, which would turn a successful delete into a 500.
  if (result.status === 204 || result.status === 205 || result.status === 304) {
    headers.delete("Content-Type");
    return new Response(null, { status: result.status, headers });
  }
  return new Response(result.body, { status: result.status, headers });
}

/** Uniform 502 when the Go API is unreachable. */
export function upstreamUnavailableResponse(): Response {
  return Response.json(
    {
      error: {
        code: "UPSTREAM_UNAVAILABLE",
        message: "暂时无法连接服务，请稍后重试",
      },
    },
    { status: 502 },
  );
}
