"use client";

import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";
import { useFormStatus } from "react-dom";

type LoginFormProps = {
  action: (formData: FormData) => void | Promise<void>;
};

export function LoginForm({ action }: LoginFormProps) {
  const [passwordVisible, setPasswordVisible] = useState(false);

  return (
    <form action={action} className="login-form">
      <div className="login-field">
        <label htmlFor="login-email">邮箱地址</label>
        <div className="login-input-wrap">
          <Mail aria-hidden="true" size={18} strokeWidth={1.8} />
          <input
            autoComplete="email"
            id="login-email"
            inputMode="email"
            name="email"
            placeholder="name@example.com"
            required
            type="email"
          />
        </div>
      </div>

      <div className="login-field">
        <div className="login-label-row">
          <label htmlFor="login-password">登录密码</label>
          <a href="/recovery">忘记密码？</a>
        </div>
        <div className="login-input-wrap">
          <LockKeyhole aria-hidden="true" size={18} strokeWidth={1.8} />
          <input
            autoComplete="current-password"
            id="login-password"
            name="password"
            placeholder="请输入密码"
            required
            type={passwordVisible ? "text" : "password"}
          />
          <button
            aria-label={passwordVisible ? "隐藏密码" : "显示密码"}
            className="login-password-toggle"
            onClick={() => setPasswordVisible((visible) => !visible)}
            title={passwordVisible ? "隐藏密码" : "显示密码"}
            type="button"
          >
            {passwordVisible ? (
              <EyeOff aria-hidden="true" size={18} strokeWidth={1.8} />
            ) : (
              <Eye aria-hidden="true" size={18} strokeWidth={1.8} />
            )}
          </button>
        </div>
      </div>

      <LoginSubmitButton />
    </form>
  );
}

function LoginSubmitButton() {
  const { pending } = useFormStatus();

  return (
    <button aria-busy={pending} className="login-submit" disabled={pending} type="submit">
      {pending ? (
        <>
          <LoaderCircle aria-hidden="true" className="login-submit-spinner" size={19} strokeWidth={1.8} />
          正在登录
        </>
      ) : (
        <>
          进入创作工作台
          <ArrowRight aria-hidden="true" size={19} strokeWidth={1.8} />
        </>
      )}
    </button>
  );
}
