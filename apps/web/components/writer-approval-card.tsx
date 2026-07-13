"use client";

import { Check, ShieldAlert, X } from "lucide-react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

export type WriterApproval = {
  approvalId: string;
  summary: string;
  consequence: string;
  action?: string;
  reversible?: boolean;
};

type WriterApprovalCardProps = {
  locale: Locale;
  approval: WriterApproval;
  /** Progressive-enhancement form action that posts decision + approvalId. */
  decideAction?: (formData: FormData) => Promise<void>;
  disabled?: boolean;
};

/**
 * Explicit consequence card for consequential agent actions (canon write / distillation).
 * Seal-red approve; remains until resolved.
 */
export function WriterApprovalCard({ locale, approval, decideAction, disabled }: WriterApprovalCardProps) {
  return (
    <article className="writer-approval-card" role="region" aria-labelledby={`approval-${approval.approvalId}-title`}>
      <header>
        <span className="writer-approval-icon" aria-hidden="true">
          <ShieldAlert size={18} />
        </span>
        <div>
          <p className="eyebrow"><Bi zh="需要审批" en="Approval required" /></p>
          <h3 id={`approval-${approval.approvalId}-title`}>{approval.summary}</h3>
        </div>
      </header>
      <p className="writer-approval-consequence">{approval.consequence}</p>
      {approval.action ? (
        <p className="writer-approval-action">
          <Bi zh="动作：" en="Action: " />
          {approval.action}
        </p>
      ) : null}
      <p className="form-hint">
        {approval.reversible
          ? tx(locale, "此操作可在版本历史中回退。", "This action can be reversed from version history.")
          : tx(locale, "请确认后再继续；拒绝则不会写入正典。", "Confirm to continue; reject leaves canon unchanged.")}
      </p>
      {decideAction ? (
        <div className="writer-approval-actions">
          <form action={decideAction}>
            <input name="approvalId" type="hidden" value={approval.approvalId} />
            <input name="decision" type="hidden" value="approve" />
            <button type="submit" data-tone="primary" className="writer-approval-approve" disabled={disabled}>
              <Check aria-hidden="true" size={15} />
              <Bi zh="批准继续" en="Approve" />
            </button>
          </form>
          <form action={decideAction}>
            <input name="approvalId" type="hidden" value={approval.approvalId} />
            <input name="decision" type="hidden" value="reject" />
            <button type="submit" disabled={disabled}>
              <X aria-hidden="true" size={15} />
              <Bi zh="拒绝" en="Reject" />
            </button>
          </form>
        </div>
      ) : null}
    </article>
  );
}
