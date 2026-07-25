import { createHash, createHmac } from "node:crypto";

/**
 * Server-side signing for the Go control plane's trusted client proof
 * (`X-Mirofish-Recovery-Client`). The Go API requires this header on
 * credential-gated routes (login/signup/recovery) when platform rate
 * limiting is on. The secret must never reach the browser, so the BFF route
 * signs on the client's behalf using its resolved IP.
 *
 * Proof format (mirrors apps/api/internal/authrecovery):
 *   clientHash = sha256hex(clientIp)            // see hashToken
 *   message    = "v1:<unixSeconds>:<clientHash>"
 *   signature  = hex HMAC-SHA256(secret, message)
 *   header     = "<message>:<signature>"
 */
export function signTrustedClientProof(clientIp: string): string | null {
  const secret = process.env.MIROFISH_RECOVERY_CLIENT_PROOF_SECRET?.trim();
  if (!secret) {
    return null;
  }
  const now = Math.floor(Date.now() / 1000);
  const clientHash = createHash("sha256").update(clientIp).digest("hex");
  const message = `v1:${now}:${clientHash}`;
  const signature = createHmac("sha256", secret).update(message).digest("hex");
  return `${message}:${signature}`;
}
