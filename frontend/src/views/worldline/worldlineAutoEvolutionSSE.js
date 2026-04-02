/**
 * SSE connection helper for the POST-based auto-evolve streaming endpoint.
 * Uses fetch + ReadableStream because the browser EventSource API only supports GET.
 */

export function connectAutoEvolveSSE({ sessionId, payload, onEvent, onError, onDone }) {
  const controller = new AbortController();

  fetch(`/api/worldline/session/${sessionId}/auto-evolve/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    },
    body: JSON.stringify(payload),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`SSE 连接失败 (${response.status}): ${text.slice(0, 200)}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent(data);
            } catch {
              // skip malformed SSE data lines
            }
          }
        }
      }
      // flush remaining buffer
      if (buffer.startsWith("data: ")) {
        try {
          const data = JSON.parse(buffer.slice(6));
          onEvent(data);
        } catch {
          // skip
        }
      }
      onDone?.();
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError?.(err);
      }
    });

  return { abort: () => controller.abort() };
}
