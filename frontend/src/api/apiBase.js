const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:5101";

function readEnvApiBaseUrl() {
  return import.meta?.env?.VITE_API_BASE_URL || "";
}

export function resolveApiBaseUrl(options = {}) {
  const envBaseUrl = options.envBaseUrl ?? readEnvApiBaseUrl();
  if (envBaseUrl) {
    return envBaseUrl;
  }
  if (options.windowObject) {
    return "";
  }
  return DEFAULT_BACKEND_ORIGIN;
}

export function buildApiUrl(path, apiBaseUrl) {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path;
}
