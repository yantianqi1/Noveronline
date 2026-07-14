"use client";

import { Plus } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Bi } from "./bilingual-text";
import { type Locale, tx } from "../lib/locale";

type LLMCreateChannelDialogProps = {
  createChannelAction: (formData: FormData) => Promise<void>;
  /** When true after a failed create, reopen so the operator can correct fields. */
  forceOpen?: boolean;
  locale: Locale;
  statusSlot?: ReactNode;
};

/**
 * Create-channel entry: primary button opens a modal with the fields to fill.
 * Keeps the channel admin surface compact until the operator intends to add one.
 */
export function LLMCreateChannelDialog({
  createChannelAction,
  forceOpen = false,
  locale,
  statusSlot,
}: LLMCreateChannelDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [open, setOpen] = useState(forceOpen);

  useEffect(() => {
    if (forceOpen) {
      setOpen(true);
    }
  }, [forceOpen]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (open) {
      previousFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      if (!dialog.open) {
        dialog.showModal();
      }
      // Prefer first field so keyboard users start filling immediately.
      firstFieldRef.current?.focus();
      return;
    }

    if (dialog.open) {
      dialog.close();
    }
    previousFocusRef.current?.focus();
  }, [open]);

  return (
    <div className="llm-create-channel">
      <div className="llm-create-channel-toolbar">
        <div className="llm-create-channel-copy">
          <p className="form-hint">
            <Bi
              zh="添加 OpenAI 兼容的 API 渠道后，再同步模型并绑定到写作能力。"
              en="Add an OpenAI-compatible API channel, then sync models and bind them to writing modules."
            />
          </p>
        </div>
        <button
          className="submit-button"
          data-tone="primary"
          onClick={() => setOpen(true)}
          type="button"
        >
          <Plus aria-hidden="true" size={16} strokeWidth={2.2} />
          <Bi zh="创建渠道" en="Create channel" />
        </button>
      </div>

      {statusSlot}

      {open ? (
        <dialog
          aria-describedby={descriptionId}
          aria-labelledby={titleId}
          className="llm-create-channel-dialog"
          onCancel={(event) => {
            event.preventDefault();
            setOpen(false);
          }}
          ref={dialogRef}
        >
          <div className="llm-create-channel-dialog-header">
            <div>
              <h2 id={titleId}>
                <Bi zh="创建渠道" en="Create channel" />
              </h2>
              <p id={descriptionId}>
                <Bi
                  zh="填写名称、基础 URL 与 API 密钥。创建后可同步模型。"
                  en="Enter a name, base URL, and API key. Sync models after creation."
                />
              </p>
            </div>
            <button
              className="submit-button"
              data-tone="secondary"
              onClick={() => setOpen(false)}
              type="button"
            >
              <Bi zh="关闭" en="Close" />
            </button>
          </div>

          <form action={createChannelAction} className="binding-form llm-create-channel-form">
            <label htmlFor="channel-name">
              <Bi zh="名称" en="Name" />
            </label>
            <input
              id="channel-name"
              name="name"
              placeholder={tx(locale, "写作渠道", "Writing channel")}
              ref={firstFieldRef}
              required
            />

            <label htmlFor="channel-provider">
              <Bi zh="提供方" en="Provider" />
            </label>
            <select id="channel-provider" name="provider" defaultValue="openai-compatible">
              <option value="openai-compatible">openai-compatible</option>
              <option value="openai">openai</option>
            </select>

            <label htmlFor="channel-base-url">
              <Bi zh="基础 URL" en="Base URL" />
            </label>
            <input
              id="channel-base-url"
              name="baseUrl"
              placeholder="https://api.example.com/v1"
              required
              type="url"
            />

            <label htmlFor="channel-api-key">
              <Bi zh="API 密钥" en="API key" />
            </label>
            <input id="channel-api-key" name="apiKey" required type="password" autoComplete="off" />

            <label htmlFor="channel-concurrency">
              <Bi zh="最大并发数" en="Max concurrency" />
            </label>
            <input
              id="channel-concurrency"
              min={1}
              name="maxConcurrency"
              required
              type="number"
              defaultValue={1}
            />

            <label className="checkbox-row">
              <input name="enabled" type="checkbox" defaultChecked />
              <Bi zh="启用" en="Enabled" />
            </label>

            <label className="checkbox-row">
              <input name="externalProviderOptIn" type="checkbox" />
              <Bi
                zh="允许调用该外部 HTTPS 提供方"
                en="Allow calls to this external HTTPS provider"
              />
            </label>

            <div className="llm-create-channel-actions">
              <button
                className="submit-button"
                data-tone="secondary"
                onClick={() => setOpen(false)}
                type="button"
              >
                <Bi zh="取消" en="Cancel" />
              </button>
              <button className="submit-button" data-tone="primary" type="submit">
                <Bi zh="创建渠道" en="Create channel" />
              </button>
            </div>
          </form>
        </dialog>
      ) : null}
    </div>
  );
}
