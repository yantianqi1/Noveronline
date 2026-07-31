"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";

type ApiError = { error?: { code?: string; message?: string } };

async function readError(response: Response): Promise<ApiError> {
  try {
    return (await response.json()) as ApiError;
  } catch {
    return {};
  }
}

function messageFor(code: string | undefined, fallback: string): string {
  switch (code) {
    case "UNAUTHENTICATED":
      return "请先登录，再接受这份邀请。";
    case "INVITATION_INVALID":
      return "邀请链接无效，请联系邀请人重新发送。";
    case "INVITATION_EXPIRED":
      return "邀请链接已过期，请联系邀请人重新发送。";
    case "INVITATION_ALREADY_USED":
      return "这份邀请已经使用过了。";
    case "COLLABORATION_ACCESS_DENIED":
      return "当前账号没有接受这份邀请的权限。";
    case "UPSTREAM_UNAVAILABLE":
      return "服务暂时不可用，请稍后再试。";
    default:
      return fallback;
  }
}

export function InvitationAcceptForm({ token }: { token: string }) {
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const returnTo = useMemo(
    () => `/invitations/accept?token=${encodeURIComponent(token)}`,
    [token],
  );
  const loginHref = `/login?returnTo=${encodeURIComponent(returnTo)}`;

  async function accept() {
    setError(null);
    if (!token) {
      setError("邀请链接缺少安全 token，请使用邮件中的完整链接。");
      return;
    }
    setSubmitting(true);
    try {
      const csrfResponse = await fetch("/api/auth/csrf-token", { cache: "no-store" });
      if (!csrfResponse.ok) {
        const payload = await readError(csrfResponse);
        setError(messageFor(payload.error?.code, "请先登录，再接受这份邀请。"));
        return;
      }
      const csrfPayload = (await csrfResponse.json()) as { csrf_token?: string };
      if (!csrfPayload.csrf_token) {
        setError("登录状态已失效，请重新登录。");
        return;
      }
      const response = await fetch("/api/collaboration/invitations/accept", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfPayload.csrf_token,
          "X-Request-Id": crypto.randomUUID(),
        },
        body: JSON.stringify({ token }),
      });
      if (!response.ok) {
        const payload = await readError(response);
        setError(messageFor(payload.error?.code, payload.error?.message ?? "接受邀请失败，请稍后再试。"));
        return;
      }
      setAccepted(true);
    } catch {
      setError("网络异常，请检查连接后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  if (accepted) {
    return (
      <div className="space-y-5" role="status">
        <p className="rounded-panel border border-line bg-paper-deep px-4 py-3 text-sm leading-relaxed text-ink-soft">
          邀请已接受。你现在可以进入工作区开始创作。
        </p>
        <Link href="/" className="block text-center text-sm font-medium text-accent hover:text-accent-strong">
          进入工作台
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {error ? <p role="alert" className="rounded-panel border border-danger/30 bg-danger-wash px-4 py-3 text-sm leading-relaxed text-danger">{error}</p> : null}
      <Button type="button" size="lg" loading={submitting} onClick={accept} className="w-full">
        接受邀请
      </Button>
      <Link href={loginHref} className="block text-center text-sm text-muted hover:text-accent">
        使用其他账号登录
      </Link>
    </div>
  );
}
