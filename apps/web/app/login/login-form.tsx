"use client";

import { motion, AnimatePresence } from "motion/react";
import { useRouter } from "next/navigation";
import { AlertCircle, Eye, EyeOff, LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const credentialsSchema = z.object({
  email: z.string().trim().min(1, "请输入邮箱").email("邮箱格式不正确"),
  password: z.string().min(1, "请输入密码"),
});

type FieldErrors = { email?: string; password?: string };

/** Map the Go control plane's error envelope onto something an author understands. */
function messageForApiError(code: string | undefined): string {
  switch (code) {
    case "UNAUTHENTICATED":
      return "邮箱或密码不正确，请重试。";
    case "VALIDATION_FAILED":
      return "请输入有效的邮箱和密码。";
    case "RATE_LIMITED":
      return "尝试太频繁了，请稍等片刻再试。";
    case "UPSTREAM_UNAVAILABLE":
      return "暂时无法连接登录服务，请稍后重试。";
    default:
      return "登录失败，请稍后重试。";
  }
}

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const parsed = credentialsSchema.safeParse({ email, password });
    if (!parsed.success) {
      const next: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if (key === "email" || key === "password") {
          next[key] = issue.message;
        }
      }
      setFieldErrors(next);
      return;
    }
    setFieldErrors({});
    setSubmitting(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });

      if (!response.ok) {
        let code: string | undefined;
        try {
          const payload = (await response.json()) as { error?: { code?: string } };
          code = payload?.error?.code;
        } catch {
          code = undefined;
        }
        setFormError(messageForApiError(code));
        return;
      }

      // Session cookie is set by the BFF proxy; move into the workspace.
      router.push("/");
      router.refresh();
    } catch {
      setFormError("网络异常，请检查连接后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <AnimatePresence initial={false}>
        {formError ? (
          <motion.div
            key="form-error"
            initial={{ opacity: 0, y: -6, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -6, height: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-panel border border-accent/30 bg-accent-wash px-3.5 py-3 text-sm leading-relaxed text-accent-strong"
            >
              <AlertCircle className="mt-px size-4 shrink-0" aria-hidden />
              <span>{formError}</span>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <div className="flex flex-col gap-2">
        <Label htmlFor="email">邮箱</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          invalid={Boolean(fieldErrors.email)}
          onChange={(event) => setEmail(event.target.value)}
          disabled={submitting}
          autoFocus
        />
        {fieldErrors.email ? (
          <p className="text-caption text-accent">{fieldErrors.email}</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">密码</Label>
          <a
            href="/recovery"
            className="text-caption text-muted transition-colors hover:text-accent"
          >
            忘记密码？
          </a>
        </div>
        <div className="relative">
          <Input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            placeholder="请输入密码"
            value={password}
            invalid={Boolean(fieldErrors.password)}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            className="pr-11"
          />
          <button
            type="button"
            onClick={() => setShowPassword((value) => !value)}
            aria-label={showPassword ? "隐藏密码" : "显示密码"}
            className="absolute right-1.5 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-panel text-muted transition-colors hover:bg-accent-wash hover:text-accent"
          >
            {showPassword ? (
              <EyeOff className="size-4" aria-hidden />
            ) : (
              <Eye className="size-4" aria-hidden />
            )}
          </button>
        </div>
        {fieldErrors.password ? (
          <p className="text-caption text-accent">{fieldErrors.password}</p>
        ) : null}
      </div>

      <motion.div whileTap={{ scale: 0.985 }} className="pt-1">
        <Button type="submit" size="lg" loading={submitting} className="w-full">
          {submitting ? "正在登录…" : "登录"}
          {!submitting ? <LogIn className="size-4" aria-hidden /> : null}
        </Button>
      </motion.div>
    </form>
  );
}
