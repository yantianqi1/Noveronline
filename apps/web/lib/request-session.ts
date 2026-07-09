import { workUnitAsyncStorage } from "next/dist/server/app-render/work-unit-async-storage.external";

export function currentRequestSessionCookie(options: { required?: boolean } = {}) {
  const store = workUnitAsyncStorage.getStore();
  if (!store || store.type !== "request") {
    if (options.required) {
      throw new Error("CURRENT_REQUEST_SESSION_CONTEXT_UNAVAILABLE");
    }
    return undefined;
  }
  if (!store.headers || typeof store.headers.get !== "function") {
    throw new Error("CURRENT_REQUEST_SESSION_STORE_UNAVAILABLE");
  }
  return sessionCookieFromHeader(store.headers.get("cookie"));
}

function sessionCookieFromHeader(cookieHeader: string | null) {
  if (!cookieHeader) {
    return undefined;
  }
  const prefix = "mirofish_session=";
  for (const part of cookieHeader.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length)).trim() || undefined;
    }
  }
  return undefined;
}
