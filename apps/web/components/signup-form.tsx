"use client";

import {
  ArrowRight,
  BookOpenText,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Mail,
  UserRound,
} from "lucide-react";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

export type SignupFieldName = "display_name" | "email" | "password" | "confirmation" | "project_title";

export type SignupFormState = {
  ok: false;
  code?: string;
  message?: string;
  fieldErrors?: Partial<Record<SignupFieldName, string>>;
};

type SignupFormProps = {
  action: (state: SignupFormState, formData: FormData) => Promise<SignupFormState>;
};

const INITIAL_STATE: SignupFormState = { ok: false };

export function SignupForm({ action }: SignupFormProps) {
  const [state, formAction] = useActionState(action, INITIAL_STATE);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmationVisible, setConfirmationVisible] = useState(false);

  return (
    <form action={formAction} className="login-form signup-form">
      {state.message ? (
        <div className="login-error signup-error" role="alert" data-code={state.code || undefined}>
          <strong>注册未完成</strong>
          <p>{state.message}</p>
        </div>
      ) : null}

      <div className="login-field">
        <label htmlFor="signup-display-name">你的称呼</label>
        <div className="login-input-wrap">
          <UserRound aria-hidden="true" size={18} strokeWidth={1.8} />
          <input
            aria-describedby={errorId(state, "display_name")}
            aria-invalid={Boolean(state.fieldErrors?.display_name)}
            autoComplete="name"
            id="signup-display-name"
            name="display_name"
            placeholder="例如：林墨"
            required
            type="text"
          />
        </div>
        <SignupFieldError field="display_name" state={state} />
      </div>

      <div className="login-field">
        <label htmlFor="signup-email">邮箱地址</label>
        <div className="login-input-wrap">
          <Mail aria-hidden="true" size={18} strokeWidth={1.8} />
          <input
            aria-describedby={errorId(state, "email")}
            aria-invalid={Boolean(state.fieldErrors?.email)}
            autoComplete="email"
            id="signup-email"
            inputMode="email"
            maxLength={254}
            name="email"
            placeholder="name@example.com"
            required
            type="email"
          />
        </div>
        <SignupFieldError field="email" state={state} />
      </div>

      <PasswordField
        describedBy="signup-password-hint"
        error={state.fieldErrors?.password}
        id="signup-password"
        label="设置密码"
        name="password"
        onToggle={() => setPasswordVisible((visible) => !visible)}
        visible={passwordVisible}
      />
      <p className="signup-field-hint" id="signup-password-hint">密码长度为 12 至 72 个字节；中文字符会占用多个字节。</p>

      <PasswordField
        error={state.fieldErrors?.confirmation}
        id="signup-confirmation"
        label="确认密码"
        name="confirmation"
        onToggle={() => setConfirmationVisible((visible) => !visible)}
        visible={confirmationVisible}
      />

      <div className="login-field">
        <label htmlFor="signup-project-title">第一本小说</label>
        <div className="login-input-wrap">
          <BookOpenText aria-hidden="true" size={18} strokeWidth={1.8} />
          <input
            aria-describedby={errorId(state, "project_title")}
            aria-invalid={Boolean(state.fieldErrors?.project_title)}
            autoComplete="off"
            id="signup-project-title"
            name="project_title"
            placeholder="输入作品名称"
            required
            type="text"
          />
        </div>
        <SignupFieldError field="project_title" state={state} />
      </div>

      <SignupSubmitButton />
    </form>
  );
}

function PasswordField({
  describedBy,
  error,
  id,
  label,
  name,
  onToggle,
  visible,
}: {
  describedBy?: string;
  error?: string;
  id: string;
  label: string;
  name: "password" | "confirmation";
  onToggle: () => void;
  visible: boolean;
}) {
  const fieldErrorId = error ? `${id}-error` : undefined;
  const ariaDescribedBy = [describedBy, fieldErrorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="login-field">
      <label htmlFor={id}>{label}</label>
      <div className="login-input-wrap">
        <LockKeyhole aria-hidden="true" size={18} strokeWidth={1.8} />
        <input
          aria-describedby={ariaDescribedBy}
          aria-invalid={Boolean(error)}
          autoComplete="new-password"
          id={id}
          maxLength={72}
          name={name}
          placeholder={name === "password" ? "设置登录密码" : "再次输入密码"}
          required
          type={visible ? "text" : "password"}
        />
        <button
          aria-label={visible ? `隐藏${label}` : `显示${label}`}
          className="login-password-toggle"
          onClick={onToggle}
          title={visible ? `隐藏${label}` : `显示${label}`}
          type="button"
        >
          {visible ? (
            <EyeOff aria-hidden="true" size={18} strokeWidth={1.8} />
          ) : (
            <Eye aria-hidden="true" size={18} strokeWidth={1.8} />
          )}
        </button>
      </div>
      {error ? <p className="signup-field-error" id={fieldErrorId}>{error}</p> : null}
    </div>
  );
}

function SignupFieldError({ field, state }: { field: SignupFieldName; state: SignupFormState }) {
  const error = state.fieldErrors?.[field];
  return error ? <p className="signup-field-error" id={`signup-${field.replace("_", "-")}-error`}>{error}</p> : null;
}

function SignupSubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button aria-busy={pending} className="login-submit" disabled={pending} type="submit">
      {pending ? (
        <>
          <LoaderCircle aria-hidden="true" className="login-submit-spinner" size={19} strokeWidth={1.8} />
          正在创建账号
        </>
      ) : (
        <>
          创建账号并开始写作
          <ArrowRight aria-hidden="true" size={19} strokeWidth={1.8} />
        </>
      )}
    </button>
  );
}

function errorId(state: SignupFormState, field: SignupFieldName) {
  return state.fieldErrors?.[field] ? `signup-${field.replace("_", "-")}-error` : undefined;
}
