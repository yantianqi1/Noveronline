import "server-only";
import { createHash, createHmac } from "node:crypto";
import { isIP } from "node:net";
import type { RecoveryResult } from "./auth-recovery-api";

const recoveryClientProofHeader = "X-Mirofish-Recovery-Client";

export async function requestPasswordResetFromServer(email: string, requestHeaders: Headers): Promise<RecoveryResult> {
  const proof = createRecoveryClientProof(requestHeaders);
  if (!proof) {
    return { ok: false, code: "AUTH_RECOVERY_BACKEND_UNAVAILABLE", message: "password recovery client verification is not configured", request_id: "" };
  }
  return forwardRecovery("request", { email }, proof);
}

export async function forwardRecovery(action: "request" | "reset", body: Record<string, string>, clientProof?: string): Promise<RecoveryResult> {
  const base = process.env.MIROFISH_API_BASE_URL?.trim().replace(/\/$/, "");
  if (!base) {
    return { ok: false, code: "AUTH_RECOVERY_BACKEND_UNAVAILABLE", message: "password recovery backend is not configured", request_id: "" };
  }
  try {
    const response = await fetch(`${base}/v1/auth/recovery/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(clientProof ? { [recoveryClientProofHeader]: clientProof } : {}) },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await response.json() as Record<string, unknown>;
    if (response.ok) {
      return { ok: true, message: typeof payload.message === "string" ? payload.message : undefined };
    }
    const error = (payload.error ?? {}) as Record<string, unknown>;
    return {
      ok: false,
      code: stringValue(error.code) || "AUTH_RECOVERY_FAILED",
      message: stringValue(error.message) || `HTTP ${response.status}`,
      request_id: stringValue(error.request_id),
    };
  } catch {
    return { ok: false, code: "AUTH_RECOVERY_BACKEND_UNAVAILABLE", message: "password recovery backend is unavailable", request_id: "" };
  }
}

export function createRecoveryClientProof(requestHeaders: Headers, now = Date.now()): string | undefined {
  const trustedHeader = process.env.MIROFISH_TRUSTED_CLIENT_IP_HEADER?.trim().toLowerCase();
  const secret = process.env.MIROFISH_RECOVERY_CLIENT_PROOF_SECRET?.trim();
  if (!trustedHeader || !/^[a-z0-9-]+$/.test(trustedHeader) || !secret || Buffer.byteLength(secret) < 32) {
    return undefined;
  }
  const clientIP = requestHeaders.get(trustedHeader)?.trim() ?? "";
  if (!clientIP || clientIP.includes(",") || isIP(clientIP) === 0) {
    return undefined;
  }
  const timestamp = Math.floor(now / 1000).toString();
  const clientHash = createHash("sha256").update(clientIP).digest("hex");
  const message = `v1:${timestamp}:${clientHash}`;
  const signature = createHmac("sha256", secret).update(message).digest("hex");
  return `${message}:${signature}`;
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
