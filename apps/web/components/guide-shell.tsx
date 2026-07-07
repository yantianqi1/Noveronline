type GuideShellProps = {
  tenantSlug: string;
  projectId: string;
};

const workflowRows = [
  {
    label: "Writer-first",
    status: "implemented",
    detail: "Writer runs, explicit draft adoption, recovered events, and redacted trace export.",
  },
  {
    label: "Phase 4",
    status: "in progress",
    detail: "LLM Facility hardening, telemetry, trace privacy, secure key handoff, and concurrency.",
  },
  {
    label: "Phase 5",
    status: "in progress",
    detail: "Seed, asset, archive, search, and story graph skeletons with fail-closed runtime gaps.",
  },
  {
    label: "Phase 6",
    status: "pending",
    detail: "Worldline and Character Console runtimes are not yet wired beyond explicit shell states.",
  },
];

const moduleRows = [
  ["Overview", "Source files, Seed run admission, replay, cancel, and retry surfaces"],
  ["Assets", "Asset CRUD, search, facets, archive memory review, ingestion, reindex, style extraction"],
  ["Story Graph", "Snapshot reads, graph build admission, evidence gating, and bond generation shell"],
  ["Worldline", "Saved path reference read side with runtime pending state"],
  ["Character Console", "Interaction workspace shell blocked on worldline session runtime"],
  ["Writer", "Writer run control, context pickers, trace, event replay, and draft adoption"],
  ["LLM Facility", "Channel management, model sync, project bindings, activity, usage, and settings"],
];

export function GuideShell({ tenantSlug, projectId }: GuideShellProps) {
  return (
    <div>
      <header>
        <p className="eyebrow">Guide</p>
        <h1>Guide</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <div className="status-row">
          <span className="status-pill">SAAS_GUIDE_RUNTIME_PENDING</span>
          <span className="status-pill">Writer-first mainline</span>
        </div>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section className="panel" aria-labelledby="guide-status-heading">
            <p className="eyebrow">Onboarding status</p>
            <h2 id="guide-status-heading">Refactor progress</h2>
            <div className="binding-stack">
              {workflowRows.map((row) => (
                <article className="reference-card" key={row.label}>
                  <div className="status-row">
                    <span className="status-pill">{row.label}</span>
                    <span className="status-pill">{row.status}</span>
                  </div>
                  <p className="form-hint">{row.detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="panel" aria-labelledby="guide-modules-heading">
            <p className="eyebrow">Project modules</p>
            <h2 id="guide-modules-heading">Workspace coverage</h2>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Module</th>
                    <th>Current SaaS surface</th>
                  </tr>
                </thead>
                <tbody>
                  {moduleRows.map(([module, surface]) => (
                    <tr key={module}>
                      <td>{module}</td>
                      <td>{surface}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </main>

        <aside>
          <section className="panel error-box" aria-labelledby="guide-runtime-heading">
            <p className="eyebrow">Runtime</p>
            <h2 id="guide-runtime-heading">Onboarding runtime</h2>
            <p className="form-hint">
              SAAS_GUIDE_RUNTIME_PENDING: project-aware tutorials and migration checklists are not
              backed by persisted onboarding state in this slice.
            </p>
          </section>

          <section className="panel" aria-labelledby="guide-boundaries-heading">
            <p className="eyebrow">Boundaries</p>
            <h2 id="guide-boundaries-heading">Fail-closed status</h2>
            <p className="form-hint">
              Missing backends remain visible as explicit error states. Agent output still requires
              user adoption before it becomes manuscript or canon data.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
