import { Activity, Gauge, HeartPulse, ReceiptText, Save, Trash2 } from "lucide-react";
import type {
  LLMAdminFailure,
  ProviderHealth,
  QuotaPolicy,
  Reconciliation,
  Reservation,
  ResolutionPreview,
} from "../lib/llm-admin-api";

type Result<T> = ({ ok: true } & T) | LLMAdminFailure;
type Locale = "zh-CN" | "en";
type FormAction = (formData: FormData) => Promise<void>;

export function LLMQuotaAdminShell({
  locale,
  tenantSlug,
  projectId,
  moduleKey,
  reservationStatus,
  policies,
  resolution,
  reservations,
  reconciliation,
  health,
  notice,
  createPolicyAction,
  updatePolicyAction,
  deletePolicyAction,
  healthAction,
}: {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  reservationStatus: string;
  policies: Result<{ items: QuotaPolicy[] }>;
  resolution: Result<ResolutionPreview>;
  reservations: Result<{ items: Reservation[] }>;
  reconciliation: Result<{ items: Reconciliation[] }>;
  health?: Result<ProviderHealth>;
  notice?: { status: string; code: string; message: string };
  createPolicyAction: FormAction;
  updatePolicyAction: FormAction;
  deletePolicyAction: FormAction;
  healthAction: FormAction;
}) {
  return (
    <div>
      <header>
        <p className="eyebrow">{t(locale, "LLM 管理", "LLM Administration")}</p>
        <h1><Gauge size={23} aria-hidden="true" /> {t(locale, "配额与账单", "Quota & Billing")}</h1>
        <span className="status-pill">{moduleKey}</span>{" "}
        <a className="status-pill" href={`/${tenantSlug}/projects/${projectId}/llm-facility`}>
          {t(locale, "返回设施", "Facility")}
        </a>
      </header>

      {notice?.message ? <p className={notice.status === "success" ? "success-box" : "error-box"} role="status">{notice.message} <small>{notice.code}</small></p> : null}

      <section className="panel" aria-labelledby="resolution-heading">
        <p className="eyebrow"><Activity size={14} aria-hidden="true" /> {t(locale, "生效预览", "Effective Resolution")}</p>
        <h2 id="resolution-heading">{t(locale, "模块 → 项目 → 工作区", "Module → Project → Workspace")}</h2>
        <form method="get" className="binding-form">
          <label htmlFor="quota-module">{t(locale, "模块键", "Module key")}</label>
          <input id="quota-module" name="moduleKey" defaultValue={moduleKey} required />
          <input type="hidden" name="reservationStatus" value={reservationStatus} />
          <button type="submit">{t(locale, "预览", "Preview")}</button>
        </form>
        {!resolution.ok ? <Failure result={resolution} /> : resolution.status === "unconfigured" ? (
          <p className="error-box">{t(locale, "没有生效的配额策略。Provider 调用会按后端策略显式失败。", "No quota policy is effective. Provider calls fail closed.")}</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t(locale,"范围","Scope")}</th><th>{t(locale,"周期","Period")}</th><th>{t(locale,"Token 剩余","Tokens left")}</th><th>{t(locale,"成本剩余 (μ)","Cost left (μ)")}</th><th>{t(locale,"并发剩余","Concurrency left")}</th></tr></thead>
              <tbody>{resolution.applicable.map((item) => <tr key={item.policy.policy_id}>
                <td><strong>{item.policy.scope_type}</strong>{resolution.limiting_scopes.includes(item.policy.scope_type) ? ` · ${t(locale,"紧约束","limiting")}` : ""}</td>
                <td>{formatPeriod(item.policy.period_seconds)}</td>
                <td>{remaining(item.remaining_tokens)} <small>({item.used_tokens}+{item.reserved_tokens})</small></td>
                <td>{remaining(item.remaining_cost_micros)} <small>({item.used_cost_micros}+{item.reserved_cost_micros})</small></td>
                <td>{remaining(item.remaining_concurrency)} <small>({item.active_reservations})</small></td>
              </tr>)}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="policy-heading">
        <p className="eyebrow"><Save size={14} aria-hidden="true" /> {t(locale, "策略", "Policies")}</p>
        <h2 id="policy-heading">{t(locale, "配额策略管理", "Quota Policy Management")}</h2>
        <PolicyForm action={createPolicyAction} projectId={projectId} moduleKey={moduleKey} locale={locale} />
        {!policies.ok ? <Failure result={policies} /> : policies.items.length === 0 ? <p>{t(locale,"尚无策略。","No policies configured.")}</p> : policies.items.map((policy) => (
          <form action={updatePolicyAction} className="binding-form" key={policy.policy_id} style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginTop: 16 }}>
            <input type="hidden" name="policyId" value={policy.policy_id} />
            <input type="hidden" name="expectedVersion" value={policy.version} />
            <PolicyFields policy={policy} projectId={projectId} moduleKey={moduleKey} locale={locale} />
            <label><input type="checkbox" name="enabled" defaultChecked={policy.enabled} /> {t(locale,"启用","Enabled")}</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="submit"><Save size={16} aria-hidden="true" /> {t(locale,"保存","Save")}</button>
              <button type="submit" formAction={deletePolicyAction} className="danger-button"><Trash2 size={16} aria-hidden="true" /> {t(locale,"删除","Delete")}</button>
            </div>
          </form>
        ))}
      </section>

      <section className="panel" aria-labelledby="reservation-heading">
        <p className="eyebrow"><Gauge size={14} aria-hidden="true" /> {t(locale,"Reservation 诊断","Reservation Diagnostics")}</p>
        <h2 id="reservation-heading">{t(locale,"调用额度占用","Provider Call Reservations")}</h2>
        <form method="get" className="binding-form">
          <input type="hidden" name="moduleKey" value={moduleKey} />
          <label htmlFor="reservation-status">{t(locale,"状态","Status")}</label>
          <select id="reservation-status" name="reservationStatus" defaultValue={reservationStatus}>
            <option value="">{t(locale,"全部","All")}</option><option value="reserved">reserved</option><option value="finalized">finalized</option><option value="released">released</option><option value="expired">expired</option>
          </select>
          <button type="submit">{t(locale,"筛选","Filter")}</button>
        </form>
        {!reservations.ok ? <Failure result={reservations} /> : <ReservationTable locale={locale} items={reservations.items} />}
      </section>

      <section className="panel" aria-labelledby="billing-heading">
        <p className="eyebrow"><ReceiptText size={14} aria-hidden="true" /> {t(locale,"对账","Reconciliation")}</p>
        <h2 id="billing-heading">{t(locale,"Activity / Usage / Provider Call", "Activity / Usage / Provider Call")}</h2>
        {!reconciliation.ok ? <Failure result={reconciliation} /> : <ReconciliationTable locale={locale} items={reconciliation.items} />}
      </section>

      <section className="panel" aria-labelledby="health-heading">
        <p className="eyebrow"><HeartPulse size={14} aria-hidden="true" /> {t(locale,"Provider 健康", "Provider Health")}</p>
        <h2 id="health-heading">{t(locale,"最小健康请求", "Minimal Health Request")}</h2>
        <form action={healthAction} className="binding-form">
          <label htmlFor="health-channel">{t(locale,"渠道 ID","Channel ID")}</label><input id="health-channel" name="channelId" required />
          <label htmlFor="health-model">{t(locale,"模型 ID","Model ID")}</label><input id="health-model" name="modelId" required />
          <button type="submit"><HeartPulse size={16} aria-hidden="true" /> {t(locale,"检查","Check")}</button>
        </form>
        {health ? health.ok ? <p className="success-box">{health.status} · {health.latency_ms} ms · HTTP {health.status_code} · tools {yesNo(health.supports_tools)} · JSON {yesNo(health.supports_json)}</p> : <Failure result={health} /> : null}
      </section>
    </div>
  );
}

function PolicyForm({ action, projectId, moduleKey, locale }: { action: FormAction; projectId: string; moduleKey: string; locale: Locale }) {
  return <form action={action} className="binding-form"><PolicyFields projectId={projectId} moduleKey={moduleKey} locale={locale} /><label><input type="checkbox" name="enabled" defaultChecked /> {t(locale,"启用","Enabled")}</label><button type="submit"><Save size={16} aria-hidden="true" /> {t(locale,"创建策略","Create policy")}</button></form>;
}

function PolicyFields({ policy, projectId, moduleKey, locale }: { policy?: QuotaPolicy; projectId: string; moduleKey: string; locale: Locale }) {
  return <>
    <label>{t(locale,"范围","Scope")}</label><select name="scopeType" defaultValue={policy?.scope_type ?? "module"}><option value="module">{t(locale,"模块","Module")}</option><option value="project">{t(locale,"项目","Project")}</option><option value="tenant">{t(locale,"工作区","Workspace")}</option></select>
    <input type="hidden" name="projectId" value={projectId} /><label>{t(locale,"模块键（仅 module）","Module key (module only)")}</label><input name="moduleKey" defaultValue={policy?.module_key ?? moduleKey} />
    <label>{t(locale,"Token 上限","Token limit")}</label><input type="number" min="0" name="tokenLimit" defaultValue={policy?.token_limit ?? ""} />
    <label>{t(locale,"成本上限 (μ)","Cost limit (μ)")}</label><input type="number" min="0" name="costLimitMicros" defaultValue={policy?.cost_limit_micros ?? ""} />
    <label>{t(locale,"并发上限","Concurrency limit")}</label><input type="number" min="1" name="concurrencyLimit" defaultValue={policy?.concurrency_limit ?? ""} />
    <label>{t(locale,"周期（秒）","Period (seconds)")}</label><input type="number" min="1" required name="periodSeconds" defaultValue={policy?.period_seconds ?? 86400} />
  </>;
}

function ReservationTable({ items, locale }: { items: Reservation[]; locale: Locale }) {
  if (!items.length) return <p>{t(locale,"没有 reservation。","No reservations.")}</p>;
  return <div className="table-wrap"><table><thead><tr><th>provider_call_id</th><th>{t(locale,"模块 / 模型","Module / Model")}</th><th>{t(locale,"状态","Status")}</th><th>{t(locale,"预留 / 实际 Token","Reserved / actual tokens")}</th><th>{t(locale,"成本 (μ)","Cost (μ)")}</th><th>{t(locale,"过期时间","Expires")}</th></tr></thead><tbody>{items.map((item) => <tr key={item.reservation_id}><td><code>{item.provider_call_id}</code></td><td>{item.module_key}<br/><small>{item.model_id}</small></td><td>{item.status}</td><td>{item.reserved_tokens} / {actualTokens(item)}</td><td>{item.actual_cost_micros ?? t(locale,"不可用","unavailable")}</td><td>{formatDate(item.expires_at)}</td></tr>)}</tbody></table></div>;
}

function ReconciliationTable({ items, locale }: { items: Reconciliation[]; locale: Locale }) {
  if (!items.length) return <p>{t(locale,"没有可对账调用。","No provider calls to reconcile.")}</p>;
  return <div className="table-wrap"><table><thead><tr><th>provider_call_id</th><th>{t(locale,"状态","Status")}</th><th>{t(locale,"Token: 实际 / usage","Tokens: actual / usage")}</th><th>{t(locale,"成本: 实际 / usage","Cost: actual / usage")}</th><th>{t(locale,"问题","Issues")}</th></tr></thead><tbody>{items.map((item) => <tr key={item.provider_call_id}><td><code>{item.provider_call_id}</code><br/><small>{item.module_key} · {item.model_id}</small></td><td>{item.billing_status}<br/><small>{item.pricing_status}</small></td><td>{nullable(item.actual_tokens)} / {nullable(item.usage_tokens)}</td><td>{nullable(item.actual_cost_micros)} / {nullable(item.usage_cost_micros)}</td><td>{item.issues.length ? item.issues.join(", ") : "—"}</td></tr>)}</tbody></table></div>;
}

function Failure({ result }: { result: LLMAdminFailure }) { return <p className="error-box" role="alert">{result.message} <small>{result.code}</small></p>; }
function t(locale: Locale, zh: string, en: string) { return locale === "en" ? en : zh; }
function remaining(value: number | null) { return value === null ? "∞" : String(value); }
function nullable(value: number | null) { return value === null ? "unavailable" : String(value); }
function actualTokens(item: Reservation) { return item.actual_prompt_tokens === null || item.actual_completion_tokens === null ? "—" : item.actual_prompt_tokens + item.actual_completion_tokens; }
function formatPeriod(seconds: number) { return seconds % 86400 === 0 ? `${seconds / 86400}d` : seconds % 3600 === 0 ? `${seconds / 3600}h` : `${seconds}s`; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString(); }
function yesNo(value: boolean) { return value ? "yes" : "no"; }
