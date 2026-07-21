/** Browser/server API base for the Go control plane. */
export function apiBaseUrl(): string {
  return process.env.MIROFISH_API_BASE_URL?.trim() || "http://127.0.0.1:3888";
}
