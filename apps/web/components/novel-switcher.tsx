"use client";

import Link from "next/link";
import { BookOpenText, Check, ChevronDown, FolderKanban, Pencil, Plus } from "lucide-react";
import { useActionState, useEffect, useRef, useState } from "react";
import { useFormStatus } from "react-dom";

import { Bi } from "./bilingual-text";
import type { ProjectActionState } from "../app/(app)/[tenantSlug]/projects/[projectId]/project-actions";

type NovelOption = { projectId: string; name: string; href: string };

type NovelSwitcherProps = {
  currentName: string;
  currentProjectId: string;
  workspaceLabel: React.ReactNode;
  novels: NovelOption[];
  onSwitch: (event: { preventDefault: () => void }, href: string) => void;
  createAction: (state: ProjectActionState, formData: FormData) => Promise<ProjectActionState>;
  renameAction: (state: ProjectActionState, formData: FormData) => Promise<ProjectActionState>;
};

const INITIAL_STATE: ProjectActionState = { ok: false };

export function NovelSwitcher({
  currentName,
  currentProjectId,
  workspaceLabel,
  novels,
  onSwitch,
  createAction,
  renameAction,
}: NovelSwitcherProps) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"list" | "create" | "rename">("list");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setMode("list");
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="novel-switcher" ref={containerRef}>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={currentName || "当前小说 / Current novel"}
        className="novel-switcher-trigger"
        onClick={() => setOpen((value) => !value)}
        title={currentName || "当前小说 / Current novel"}
        type="button"
      >
        <span className="novel-switcher-icon" aria-hidden="true">
          <BookOpenText size={17} strokeWidth={1.8} />
        </span>
        <span className="novel-switcher-labels">
          <strong>{currentName || <Bi zh="当前小说" en="Current novel" />}</strong>
          <small>{workspaceLabel}</small>
        </span>
        <ChevronDown aria-hidden="true" className="novel-switcher-caret" data-open={open ? "true" : undefined} size={16} />
      </button>

      {open ? (
        <div className="novel-switcher-panel" role="menu">
          {mode === "list" ? (
            <>
              <p className="eyebrow"><Bi zh="我的小说" en="My novels" /></p>
              <div className="novel-switcher-list">
                {novels.map((novel) => {
                  const current = novel.projectId === currentProjectId;
                  return (
                    <Link
                      aria-current={current ? "page" : undefined}
                      className="novel-switcher-item"
                      href={novel.href}
                      key={novel.projectId}
                      onNavigate={(event) => {
                        setOpen(false);
                        onSwitch(event, novel.href);
                      }}
                      role="menuitem"
                    >
                      <FolderKanban aria-hidden="true" size={15} />
                      <span>{novel.name}</span>
                      {current ? <Check aria-hidden="true" className="novel-switcher-check" size={15} /> : null}
                    </Link>
                  );
                })}
              </div>
              <div className="novel-switcher-actions">
                <button className="novel-switcher-action" onClick={() => setMode("create")} type="button">
                  <Plus aria-hidden="true" size={15} />
                  <Bi zh="新建小说" en="New novel" />
                </button>
                <button className="novel-switcher-action" onClick={() => setMode("rename")} type="button">
                  <Pencil aria-hidden="true" size={15} />
                  <Bi zh="重命名当前小说" en="Rename current" />
                </button>
              </div>
            </>
          ) : null}

          {mode === "create" ? (
            <NovelForm
              action={createAction}
              cancelLabel={<Bi zh="返回" en="Back" />}
              onCancel={() => setMode("list")}
              placeholder="输入新作品名称"
              submitLabel={<Bi zh="创建" en="Create" />}
              title={<Bi zh="新建小说" en="New novel" />}
            />
          ) : null}

          {mode === "rename" ? (
            <NovelForm
              action={renameAction}
              cancelLabel={<Bi zh="返回" en="Back" />}
              closeOnSuccess
              defaultValue={currentName}
              onCancel={() => setMode("list")}
              onSuccess={() => setOpen(false)}
              placeholder="输入新的作品名称"
              submitLabel={<Bi zh="保存" en="Save" />}
              title={<Bi zh="重命名当前小说" en="Rename novel" />}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function NovelForm({
  action,
  cancelLabel,
  closeOnSuccess,
  defaultValue,
  onCancel,
  onSuccess,
  placeholder,
  submitLabel,
  title,
}: {
  action: (state: ProjectActionState, formData: FormData) => Promise<ProjectActionState>;
  cancelLabel: React.ReactNode;
  closeOnSuccess?: boolean;
  defaultValue?: string;
  onCancel: () => void;
  onSuccess?: () => void;
  placeholder: string;
  submitLabel: React.ReactNode;
  title: React.ReactNode;
}) {
  const [state, formAction] = useActionState(action, INITIAL_STATE);

  useEffect(() => {
    if (closeOnSuccess && state.ok) {
      onSuccess?.();
    }
  }, [closeOnSuccess, state.ok, onSuccess]);

  return (
    <form action={formAction} className="novel-switcher-form">
      <p className="eyebrow">{title}</p>
      <input
        aria-label="作品名称 / Novel title"
        autoComplete="off"
        defaultValue={defaultValue}
        maxLength={200}
        name="title"
        placeholder={placeholder}
        required
        type="text"
      />
      {state.error ? (
        <p className="novel-switcher-error" role="alert">
          {errorMessage(state.error)}
        </p>
      ) : null}
      <div className="novel-switcher-form-actions">
        <button className="novel-switcher-secondary" onClick={onCancel} type="button">
          {cancelLabel}
        </button>
        <NovelFormSubmit label={submitLabel} />
      </div>
    </form>
  );
}

function NovelFormSubmit({ label }: { label: React.ReactNode }) {
  const { pending } = useFormStatus();
  return (
    <button aria-busy={pending} className="novel-switcher-primary" disabled={pending} type="submit">
      {pending ? <Bi zh="处理中…" en="Working…" /> : label}
    </button>
  );
}

function errorMessage(code: string): React.ReactNode {
  switch (code) {
    case "VALIDATION_FAILED":
      return <Bi zh="请输入 1 到 200 个字符的作品名称。" en="Enter a title between 1 and 200 characters." />;
    case "ACCESS_DENIED":
      return <Bi zh="你没有管理该工作区小说的权限。" en="You do not have permission to manage novels in this workspace." />;
    case "SESSION_REQUIRED":
      return <Bi zh="登录状态已失效，请重新登录。" en="Your session has expired. Please sign in again." />;
    case "PROJECT_NOT_FOUND":
      return <Bi zh="未找到该小说。" en="Novel was not found." />;
    default:
      return <Bi zh="操作失败，请稍后重试。" en="The action failed. Please try again." />;
  }
}
