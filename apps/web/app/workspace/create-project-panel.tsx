"use client";

import { AnimatePresence, motion } from "motion/react";
import { Plus, X } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createProject, ProjectAdminError } from "@/lib/api/projects";
import { fetchCsrfToken } from "@/lib/api/session";
import type { TenantMembershipSummary } from "@/lib/api/types";

type CreateProjectPanelProps = {
  tenants: TenantMembershipSummary[];
  open: boolean;
  onClose: () => void;
  onCreated: (project: { tenant_id: string; project_id: string; title: string }) => void;
};

/**
 * Inline create form for a new novel on the shelf.
 * Tenant owner/admin only — the parent only mounts this when manageableTenants
 * is non-empty. Body is strictly `{ title }` to match Go projectadmin.
 */
export function CreateProjectPanel({ tenants, open, onClose, onCreated }: CreateProjectPanelProps) {
  const titleId = useId();
  const tenantSelectId = useId();
  const [title, setTitle] = useState("");
  const [selectedTenantId, setSelectedTenantId] = useState(tenants[0]?.tenant_id ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle("");
    setError(null);
    setSubmitting(false);
    setSelectedTenantId(tenants[0]?.tenant_id ?? "");
  }, [open, tenants]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      setError("请填写作品名称");
      return;
    }
    if (!selectedTenantId) {
      setError("请选择工作区");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const csrfToken = await fetchCsrfToken();
      const project = await createProject(selectedTenantId, csrfToken, trimmed);
      onCreated({
        tenant_id: project.tenant_id,
        project_id: project.project_id,
        title: project.title,
      });
    } catch (err) {
      const message =
        err instanceof ProjectAdminError
          ? err.message
          : err instanceof Error
            ? err.message
            : "创建失败，请重试。";
      setError(message);
      setSubmitting(false);
    }
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.section
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="mb-9 rounded-card border border-line bg-panel p-5 shadow-[0_1px_2px_rgba(23,26,27,0.05)]"
          aria-labelledby={titleId}
        >
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <p className="text-[12px] font-medium tracking-[0.22em] text-accent">新 作 品</p>
              <h2 id={titleId} className="mt-1 font-serif text-[20px] font-semibold text-ink">
                创建一部小说
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="grid size-8 place-items-center rounded-[8px] text-muted transition-colors hover:bg-paper-deep hover:text-ink"
              aria-label="关闭"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`${titleId}-input`}>作品名称</Label>
              <Input
                id={`${titleId}-input`}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="例如：雨夜长卷"
                maxLength={200}
                autoFocus
                disabled={submitting}
                invalid={Boolean(error) && !title.trim()}
              />
            </div>

            {tenants.length > 1 ? (
              <div className="space-y-2">
                <Label htmlFor={tenantSelectId}>工作区</Label>
                <select
                  id={tenantSelectId}
                  value={selectedTenantId}
                  onChange={(event) => setSelectedTenantId(event.target.value)}
                  disabled={submitting}
                  className="flex h-11 w-full rounded-[10px] border border-line bg-panel px-3.5 text-[15px] text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/25 disabled:opacity-55"
                >
                  {tenants.map((tenant) => (
                    <option key={tenant.tenant_id} value={tenant.tenant_id}>
                      {tenant.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}

            {error ? (
              <p className="text-[13px] text-accent-strong" role="alert">
                {error}
              </p>
            ) : null}

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Button type="submit" loading={submitting}>
                <Plus className="size-4" aria-hidden />
                创建并进入
              </Button>
              <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
                取消
              </Button>
            </div>
          </form>
        </motion.section>
      ) : null}
    </AnimatePresence>
  );
}
