/**
 * POST-based SSE (Server-Sent Events) streaming client.
 *
 * Sends a POST request with JSON body and reads the response as
 * a text/event-stream, dispatching parsed events to the supplied handlers.
 */

/* ---------- Types ---------- */

export interface SSEEvent {
  type?: string;
  [key: string]: unknown;
}

export interface SSEHandlers {
  onEvent?: (event: SSEEvent) => void;
  onDone?: (event: SSEEvent) => void;
  onError?: (event: SSEEvent | Error) => void;
}

export interface SSEOptions {
  maxRetries?: number;
}

/* ---------- Internal constants ---------- */

const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:5101";
const DEFAULT_MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1500;

function readEnvApiBaseUrl(): string {
  return import.meta?.env?.VITE_API_BASE_URL || "";
}

function resolveApiBaseUrl(): string {
  const envBaseUrl = readEnvApiBaseUrl();
  if (envBaseUrl) {
    return envBaseUrl;
  }
  if (typeof window !== "undefined") {
    return "";
  }
  return DEFAULT_BACKEND_ORIGIN;
}

const API_BASE_URL: string = resolveApiBaseUrl();

function buildUrl(path: string): string {
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

/* ---------- Public ---------- */

/**
 * Send a POST request and consume the response as an SSE stream.
 *
 * @param path     - API path, e.g. "/api/writer-agent/run"
 * @param data     - Request body (JSON-serialisable)
 * @param handlers - Event callbacks: onEvent, onDone, onError
 * @param signal   - Optional AbortSignal for cancellation
 * @param options  - Extra options (maxRetries)
 */
export async function postSSE(
  path: string,
  data: unknown,
  handlers: SSEHandlers = {},
  signal?: AbortSignal,
  options: SSEOptions = {},
): Promise<void> {
  const { onEvent, onDone, onError } = handlers;
  const maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (signal?.aborted) return;

    let response: Response;
    try {
      response = await fetch(buildUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data ?? {}),
        signal,
      });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }
      onError?.(err instanceof Error ? err : new Error(String(err)));
      return;
    }

    if (!response.ok) {
      onError?.(new Error(`SSE 请求失败: ${response.status}`));
      return;
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    // Once the server has started emitting SSE events the request is no longer
    // idempotent — replaying the POST would re-run the writer agent from scratch
    // and duplicate `writer_token` output. Retries are only safe BEFORE any
    // payload has been seen.
    let hasReceivedData = false;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE format: "data: {...}\n\n"
        const segments = buffer.split("\n\n");
        buffer = segments.pop() || "";

        for (const segment of segments) {
          const trimmed = segment.trim();
          if (!trimmed) continue;
          // Ignore comment/heartbeat lines like ":ping"
          if (trimmed.startsWith(":")) {
            hasReceivedData = true;
            continue;
          }
          const jsonStr = trimmed.replace(/^data:\s*/, "");
          if (!jsonStr) continue;

          let event: SSEEvent;
          try {
            event = JSON.parse(jsonStr) as SSEEvent;
          } catch {
            continue;
          }

          hasReceivedData = true;
          if (event.type === "error") {
            onError?.(event);
          } else if (event.type === "done") {
            onDone?.(event);
          } else {
            onEvent?.(event);
          }
        }
      }
      // Stream completed normally — no retry needed
      return;
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      // If the server already began streaming, retrying would re-trigger the
      // same generation and append duplicated tokens. Surface the error instead.
      if (hasReceivedData) {
        onError?.(err instanceof Error ? err : new Error(String(err)));
        return;
      }
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }
      onError?.(err instanceof Error ? err : new Error(String(err)));
      return;
    }
  }
}
