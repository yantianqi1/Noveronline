import { buildApiUrl, resolveApiBaseUrl } from "./apiBase.js";

const API_BASE_URL = resolveApiBaseUrl({
  windowObject: typeof window === "undefined" ? null : window,
});

function buildUrl(path) {
  return buildApiUrl(path, API_BASE_URL);
}

function parsePayload(text) {
  try {
    return JSON.parse(text || "{}");
  } catch {
    return {};
  }
}

function ensureSuccess(status, payload) {
  if (status >= 200 && status < 300 && payload.success !== false) {
    return payload;
  }
  throw new Error(payload.error || `请求失败: ${status}`);
}

async function request(path, options = {}) {
  const requestOptions = { ...options };
  if (requestOptions.method === "GET" && !requestOptions.cache) {
    requestOptions.cache = "no-store";
  }
  const response = await fetch(buildUrl(path), requestOptions);
  const payload = await response.json().catch(() => ({}));
  return ensureSuccess(response.status, payload);
}

export async function get(path) {
  return request(path, { method: "GET" });
}

export async function post(path, data) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export async function put(path, data) {
  return request(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export async function patch(path, data) {
  return request(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export async function del(path) {
  return request(path, { method: "DELETE" });
}

export async function postForm(path, formData) {
  return request(path, {
    method: "POST",
    body: formData,
  });
}

export function uploadForm(path, formData, options = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const requestUrl = buildUrl(path);
    options.onRequest?.(xhr);
    xhr.open("POST", requestUrl, true);
    xhr.timeout = 15 * 60 * 1000;

    function networkErrorMessage(prefix) {
      const details = [
        `url=${requestUrl}`,
        `status=${xhr.status}`,
        `readyState=${xhr.readyState}`,
      ].join(", ");
      console.error(prefix, details);
      return `${prefix}（${details}）`;
    }

    xhr.onload = () => {
      try {
        resolve(ensureSuccess(xhr.status, parsePayload(xhr.responseText)));
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(new Error(networkErrorMessage("网络错误，上传请求未完成")));
    xhr.onabort = () => reject(new Error(networkErrorMessage("上传已中断")));
    xhr.ontimeout = () => reject(new Error(networkErrorMessage("上传超时")));
    xhr.upload.onloadstart = () => {
      options.onProgress?.({ phase: "uploading", loaded: 0, total: 0, percent: 0 });
    };
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return;
      }
      options.onProgress?.({
        phase: "uploading",
        loaded: event.loaded,
        total: event.total,
        percent: Math.min(99, Math.round((event.loaded / event.total) * 100)),
      });
    };
    xhr.upload.onload = () => {
      options.onProgress?.({ phase: "processing", loaded: 1, total: 1, percent: 100 });
    };
    xhr.send(formData);
  });
}

export function getApiBaseUrl() {
  return API_BASE_URL || "same-origin (/api)";
}
