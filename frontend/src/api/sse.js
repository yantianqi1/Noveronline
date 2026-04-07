/**
 * SSE 流式请求工具 — 用于与后端 text/event-stream 端点通信。
 */

import { buildApiUrl, resolveApiBaseUrl } from "./apiBase.js";

const API_BASE_URL = resolveApiBaseUrl({
  windowObject: typeof window === "undefined" ? null : window,
});

function buildUrl(path) {
  return buildApiUrl(path, API_BASE_URL);
}

const DEFAULT_MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1500;

/**
 * 发送 POST 请求并以 SSE 方式逐事件读取响应。
 *
 * @param {string} path - API 路径，如 "/api/novel/draft/generate"
 * @param {object} data - 请求体 JSON
 * @param {object} handlers - 事件回调
 * @param {function} handlers.onEvent - 每收到一个非终结事件时调用 (event)
 * @param {function} handlers.onDone - 收到 type=done 事件时调用 (event)
 * @param {function} handlers.onError - 收到 type=error 事件或网络错误时调用 (event|Error)
 * @param {AbortSignal} [signal] - 可选的 AbortSignal 用于取消请求
 * @param {object} [options] - 额外选项
 * @param {number} [options.maxRetries] - 网络错误最大重试次数（默认 3）
 * @returns {Promise<void>}
 */
export async function postSSE(path, data, handlers = {}, signal, options = {}) {
  const { onEvent, onDone, onError } = handlers;
  const maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (signal?.aborted) return;

    let response;
    try {
      response = await fetch(buildUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data ?? {}),
        signal,
      });
    } catch (err) {
      if (err.name === "AbortError") return;
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }
      onError?.(err);
      return;
    }

    if (!response.ok) {
      onError?.(new Error(`SSE 请求失败: ${response.status}`));
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE 格式: "data: {...}\n\n"
        const segments = buffer.split("\n\n");
        buffer = segments.pop() || "";

        for (const segment of segments) {
          const trimmed = segment.trim();
          if (!trimmed) continue;
          const jsonStr = trimmed.replace(/^data:\s*/, "");
          if (!jsonStr) continue;

          let event;
          try {
            event = JSON.parse(jsonStr);
          } catch {
            continue;
          }

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
      if (err.name === "AbortError") return;
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }
      onError?.(err);
      return;
    }
  }
}
