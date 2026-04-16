/**
 * HTTP request utilities for the MiroFish-Novel API.
 *
 * All domain API modules import from this file.
 */

/* ---------- Types ---------- */

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  count?: number;
  traceback?: string;
}

export interface UploadProgress {
  phase: "uploading" | "processing";
  loaded: number;
  total: number;
  percent: number;
}

export interface UploadFormOptions {
  onProgress?: (progress: UploadProgress) => void;
  onRequest?: (xhr: XMLHttpRequest) => void;
}

/* ---------- Internal helpers ---------- */

const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:5101";

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

function parsePayload(text: string): ApiResponse {
  try {
    return JSON.parse(text || "{}") as ApiResponse;
  } catch {
    return {} as ApiResponse;
  }
}

function ensureSuccess<T>(status: number, payload: T & { success?: boolean; error?: string }): T {
  if (status >= 200 && status < 300 && payload.success !== false) {
    return payload;
  }
  throw new Error(payload.error || `请求失败: ${status}`);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const requestOptions: RequestInit = { ...options };
  if (requestOptions.method === "GET" && !requestOptions.cache) {
    requestOptions.cache = "no-store";
  }
  const response = await fetch(buildUrl(path), requestOptions);
  const payload = await response.json().catch(() => ({}));
  return ensureSuccess<T>(response.status, payload);
}

/* ---------- Public HTTP methods ---------- */

export async function get<T = ApiResponse>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export async function post<T = ApiResponse>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export async function put<T = ApiResponse>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export async function patch<T = ApiResponse>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export async function del<T = ApiResponse>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export async function postForm<T = ApiResponse>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: formData,
  });
}

export function uploadForm(
  path: string,
  formData: FormData,
  options: UploadFormOptions = {},
): Promise<ApiResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const requestUrl = buildUrl(path);
    options.onRequest?.(xhr);
    xhr.open("POST", requestUrl, true);
    xhr.timeout = 15 * 60 * 1000;

    function networkErrorMessage(prefix: string): string {
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
    xhr.upload.onprogress = (event: ProgressEvent) => {
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

/* ---------- Utility ---------- */

export function getApiBaseUrl(): string {
  return API_BASE_URL || "same-origin (/api)";
}
