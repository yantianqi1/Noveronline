"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const emailSchema = z.object({
  email: z.string().trim().min(1, "请输入邮箱").email("邮箱格式不正确"),
});

const passwordSchema = z
  .object({
    password: z.string().min(12, "密码至少需要 12 个字符").max(72, "密码不能超过 72 个字符"),
    confirmation: z.string(),
  })
  .refine((value) => value.password === value.confirmation, {
    path: ["confirmation"],
    message: "两次输入的密码不一致",
  });

type ApiError = { error?: { code?: string; message?: string } };

async function readApiError(response: Response, fallback: string): Promise<{ code?: string; message: string }> {
  try {
    const payload = (await response.json()) as ApiError;
    return { code: payload.error?.code, message: payload.error?.message || fallback };
  } catch {
    return { message: fallback };
  }
}

function errorMessage(code: string | undefined, fallback: string): string {
  switch (code) {
    case "AUTH_RECOVERY_RATE_LIMITED":
      return "请求太频繁了，请稍后再试。";
    case "PASSWORD_RESET_TOKEN_INVALID":
      return "重置链接无效，请重新申请。";
    case "PASSWORD_RESET_TOKEN_EXPIRED":
      return "重置链接已过期，请重新申请。";
    case "PASSWORD_RESET_TOKEN_ALREADY_USED":
      return "重置链接已经使用过，请重新申请。";
    case "AUTH_RECOVERY_BACKEND_UNAVAILABLE":
    case "UPSTREAM_UNAVAILABLE":
      return "恢复服务暂时不可用，请稍后再试。";
    default:
      return fallback;
  }
}

export function RecoveryRequestForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const parsed = emailSchema.safeParse({ email });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "请输入有效邮箱");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/recovery/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      if (!response.ok) {
        const payload = await readApiError(response, "恢复请求失败，请稍后再试。");
        setError(errorMessage(payload.code, payload.message));
        return;
      }
      setSubmitted(true);
    } catch {
      setError("网络异常，请检查连接后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="space-y-5" role="status">
        <p className="rounded-panel border border-line bg-paper-deep px-4 py-3 text-sm leading-relaxed text-ink-soft">
          如果该邮箱对应可恢复的账户，重置链接将很快送达。请检查收件箱和垃圾邮件。
        </p>
        <Link href="/login" className="block text-center text-sm font-medium text-accent hover:text-accent-strong">
          返回登录
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-5">
      <div className="space-y-2">
        <Label htmlFor="recovery-email">登录邮箱</Label>
        <Input
          id="recovery-email"
          type="email"
          autoComplete="email"
          value={email}
          invalid={Boolean(error)}
          aria-describedby={error ? "recovery-error" : undefined}
          onChange={(event) => setEmail(event.target.value)}
          disabled={submitting}
          autoFocus
        />
      </div>
      {error ? <p id="recovery-error" role="alert" className="text-sm text-danger">{error}</p> : null}
      <Button type="submit" size="lg" loading={submitting} className="w-full">
        发送重置链接
      </Button>
      <Link href="/login" className="block text-center text-sm text-muted hover:text-accent">
        返回登录
      </Link>
    </form>
  );
}

export function RecoveryResetForm({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const parsed = passwordSchema.safeParse({ password, confirmation });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "请输入有效密码");
      return;
    }
    if (!token) {
      setError("重置链接缺少安全 token，请重新申请。");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/recovery/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: parsed.data.password }),
      });
      if (!response.ok) {
        const payload = await readApiError(response, "密码重置失败，请稍后再试。");
        setError(errorMessage(payload.code, payload.message));
        return;
      }
      setSubmitted(true);
    } catch {
      setError("网络异常，请检查连接后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="space-y-5" role="status">
        <p className="rounded-panel border border-line bg-paper-deep px-4 py-3 text-sm leading-relaxed text-ink-soft">
          密码已更新。现在可以使用新密码登录。
        </p>
        <Link href="/login" className="block text-center text-sm font-medium text-accent hover:text-accent-strong">
          前往登录
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-5">
      <div className="space-y-2">
        <Label htmlFor="recovery-password">新密码</Label>
        <Input
          id="recovery-password"
          type="password"
          autoComplete="new-password"
          value={password}
          invalid={Boolean(error)}
          onChange={(event) => setPassword(event.target.value)}
          disabled={submitting}
          autoFocus
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="recovery-confirmation">确认新密码</Label>
        <Input
          id="recovery-confirmation"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          invalid={Boolean(error)}
          aria-describedby={error ? "recovery-reset-error" : undefined}
          onChange={(event) => setConfirmation(event.target.value)}
          disabled={submitting}
        />
      </div>
      <p className="text-caption leading-relaxed text-muted">密码长度需为 12–72 个字符。</p>
      {error ? <p id="recovery-reset-error" role="alert" className="text-sm text-danger">{error}</p> : null}
      <Button type="submit" size="lg" loading={submitting} className="w-full">
        更新密码
      </Button>
      <Link href="/login" className="block text-center text-sm text-muted hover:text-accent">
        返回登录
      </Link>
    </form>
  );
}
