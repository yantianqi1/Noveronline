"use client";

import { Plus, X } from "lucide-react";
import Link from "next/link";
import { useId, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { createProject, ProjectAdminError } from "@/lib/api/projects";
import { fetchCsrfToken, SessionError } from "@/lib/api/session";
import type { TenantMembershipSummary } from "@/lib/api/types";

import "./shelf-create.css";

type CreateProjectPanelProps = {
  tenants: TenantMembershipSummary[];
  onClose: () => void;
  onCreated: (project: { tenant_id: string; project_id: string; title: string }) => void;
};

/** The Go project-admin creation contract accepts { title }; /me exposes name. */
export function CreateProjectPanel({ tenants, onClose, onCreated }: CreateProjectPanelProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [tenantId, setTenantId] = useState(tenants[0]?.tenant_id ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    if (!title.trim()) {
      setError("请填写作品名称。");
      inputRef.current?.focus();
      return;
    }
    if (!tenantId) {
      setError("请选择工作区。");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSessionExpired(false);
    try {
      const csrfToken = await fetchCsrfToken();
      onCreated(await createProject(tenantId, csrfToken, title.trim()));
    } catch (err) {
      const knownError = err instanceof ProjectAdminError || err instanceof SessionError;
      const expired = knownError && err.status === 401;
      setSessionExpired(expired);
      setError(expired ? "登录已过期，请重新登录后再创建作品。" : knownError ? err.message : "创建失败，请重试。");
      setSubmitting(false);
    }
  }

  return (
    <Modal label="创建一部小说" onClose={onClose} dismissible={!submitting}
      initialFocusRef={inputRef} className="shelf-create w-[480px]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-serif text-xl font-semibold">创建一部小说</h2>
          <p className="mt-2 text-base text-muted">先取个名字，再慢慢展开你的故事。</p>
        </div>
        <IconButton label="关闭创建窗口" className="size-11 shrink-0" onClick={onClose} disabled={submitting}>
          <X className="size-4" aria-hidden />
        </IconButton>
      </div>
      <form onSubmit={handleSubmit} className="mt-6 space-y-5">
        <div className="space-y-2">
          <Label htmlFor={`${id}-title`}>作品名称</Label>
          <Input id={`${id}-title`} name="title" ref={inputRef} value={title}
            onChange={(event) => { setTitle(event.target.value); if (!sessionExpired) setError(null); }} placeholder="例如：雨夜长卷"
            maxLength={200} autoComplete="off" required disabled={submitting}
            invalid={Boolean(error) && !title.trim()}
            aria-describedby={error ? `${id}-error` : undefined} />
        </div>
        {tenants.length > 1 ? (
          <div className="space-y-2">
            <Label htmlFor={`${id}-tenant`}>工作区</Label>
            <div className="shelf-create-select">
              <Select id={`${id}-tenant`} name="tenant" value={tenantId}
                onChange={(event) => setTenantId(event.target.value)} disabled={submitting} className="h-11 text-md">
                {tenants.map((tenant) => <option key={tenant.tenant_id} value={tenant.tenant_id}>{tenant.name}</option>)}
              </Select>
            </div>
          </div>
        ) : <p className="text-sm text-muted">创建到 {tenants[0]?.name}</p>}
        {error ? <p id={`${id}-error`} className="text-sm text-danger" role="alert">{error}</p> : null}
        {sessionExpired ? <Link href="/login?returnTo=%2Fworkspace"
          className="inline-flex min-h-11 items-center rounded-control text-sm font-medium text-accent underline underline-offset-4">
          重新登录
        </Link> : null}
        <div className="shelf-create-actions">
          <Button type="button" variant="ghost" onClick={onClose} disabled={submitting} className="h-11">取消</Button>
          <Button type="submit" loading={submitting} className="h-11">
            {!submitting ? <Plus className="size-4" aria-hidden /> : null}
            {submitting ? "正在创建…" : "创建并进入"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
