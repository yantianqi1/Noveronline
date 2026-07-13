import { NextRequest, NextResponse } from "next/server";
import { createRecoveryClientProof, forwardRecovery } from "../../../../../lib/auth-recovery-server";

export async function POST(request: NextRequest, { params }: { params: Promise<{ action: string }> }) {
  const { action } = await params;
  if (action !== "request" && action !== "reset") {
    return NextResponse.json({ ok: false, error: { code: "NOT_FOUND", message: "password recovery route not found", request_id: "" } }, { status: 404 });
  }
  let body: Record<string, string>;
  try {
    body = await request.json() as Record<string, string>;
  } catch {
    return NextResponse.json({ ok: false, error: { code: "VALIDATION_FAILED", message: "request body is invalid", request_id: "" } }, { status: 400 });
  }
  const clientProof = createRecoveryClientProof(request.headers);
  if (!clientProof) {
    return NextResponse.json({ ok: false, error: { code: "AUTH_RECOVERY_BACKEND_UNAVAILABLE", message: "password recovery client verification is not configured", request_id: "" } }, { status: 503 });
  }
  const result = await forwardRecovery(action, body, clientProof);
  if (result.ok) {
    return NextResponse.json(result, { status: action === "request" ? 202 : 200 });
  }
  const status = result.code === "VALIDATION_FAILED" ? 400
    : result.code === "AUTH_RECOVERY_RATE_LIMITED" ? 429
      : result.code === "PASSWORD_RESET_TOKEN_INVALID" ? 404
        : result.code === "PASSWORD_RESET_TOKEN_EXPIRED" || result.code === "PASSWORD_RESET_TOKEN_ALREADY_USED" ? 409
          : 503;
  return NextResponse.json({ ok: false, error: { code: result.code, message: result.message, request_id: result.request_id } }, { status });
}
