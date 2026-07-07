import type {
  LLMActivitySummary,
  LLMChannelModelsSummary,
  LLMChannelsSummary,
  LLMModuleBindingsSummary,
  LLMModulesSummary,
  LLMModuleResolutionSummary,
  LLMSettingsSummary,
  LLMUsageSummary,
} from "../lib/api";

type LLMFacilityShellProps = {
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  runId: string;
  selectedChannelId: string;
  bindingStatus: string;
  bindingCode: string;
  bindingMessage: string;
  channelStatus: string;
  channelCode: string;
  channelMessage: string;
  syncStatus: string;
  syncCode: string;
  syncMessage: string;
  bindModuleAction: (formData: FormData) => Promise<void>;
  clearBindingAction: (formData: FormData) => Promise<void>;
  createChannelAction: (formData: FormData) => Promise<void>;
  updateChannelAction: (formData: FormData) => Promise<void>;
  deleteChannelAction: (formData: FormData) => Promise<void>;
  syncChannelAction: (formData: FormData) => Promise<void>;
  resolution: LLMModuleResolutionSummary;
  modules: LLMModulesSummary;
  bindings: LLMModuleBindingsSummary;
  channels: LLMChannelsSummary;
  settingsSnapshot: LLMSettingsSummary;
  models: LLMChannelModelsSummary;
  activity: LLMActivitySummary;
  usage: LLMUsageSummary;
};

export function LLMFacilityShell({
  tenantSlug,
  projectId,
  moduleKey,
  runId,
  selectedChannelId,
  bindingStatus,
  bindingCode,
  bindingMessage,
  channelStatus,
  channelCode,
  channelMessage,
  syncStatus,
  syncCode,
  syncMessage,
  bindModuleAction,
  clearBindingAction,
  createChannelAction,
  updateChannelAction,
  deleteChannelAction,
  syncChannelAction,
  resolution,
  modules,
  bindings,
  channels,
  settingsSnapshot,
  models,
  activity,
  usage,
}: LLMFacilityShellProps) {
  const statusLabel = resolution.ok ? "bound" : "error";

  return (
    <div>
      <header>
        <p className="eyebrow">LLM Facility</p>
        <h1>LLM Facility</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <span className="status-pill">Module: {moduleKey}</span>{" "}
        <span className="status-pill">Status: {statusLabel}</span>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <section
          className={`panel ${resolution.ok ? "" : "error-box"}`}
          aria-labelledby="module-binding-heading"
        >
          <p className="eyebrow">Module binding</p>
          <h2 id="module-binding-heading">writer_composer</h2>
          <ModuleBinding resolution={resolution} moduleKey={moduleKey} />
        </section>

        <section className="panel" aria-labelledby="project-binding-heading">
          <p className="eyebrow">Project Binding</p>
          <h2 id="project-binding-heading">Bind module</h2>
          <ProjectBindingForm
            tenantSlug={tenantSlug}
            projectId={projectId}
            moduleKey={moduleKey}
            selectedChannelId={selectedChannelId}
            bindingStatus={bindingStatus}
            bindingCode={bindingCode}
            bindingMessage={bindingMessage}
            bindModuleAction={bindModuleAction}
            clearBindingAction={clearBindingAction}
            resolution={resolution}
            modules={modules}
            channels={channels}
            models={models}
          />
        </section>

        <section className="panel" aria-labelledby="channel-management-heading">
          <p className="eyebrow">Channel Management</p>
          <h2 id="channel-management-heading">Create channel</h2>
          <ChannelManagement
            channelStatus={channelStatus}
            channelCode={channelCode}
            channelMessage={channelMessage}
            syncStatus={syncStatus}
            syncCode={syncCode}
            syncMessage={syncMessage}
            createChannelAction={createChannelAction}
            updateChannelAction={updateChannelAction}
            deleteChannelAction={deleteChannelAction}
            syncChannelAction={syncChannelAction}
            channels={channels}
          />
        </section>

        <section
          className={`panel ${bindings.ok ? "" : "error-box"}`}
          aria-labelledby="module-bindings-heading"
        >
          <p className="eyebrow">Module Bindings</p>
          <h2 id="module-bindings-heading">Configured modules</h2>
          <ModuleBindingsTable bindings={bindings} />
        </section>

        <section
          className={`panel ${settingsSnapshot.ok ? "" : "error-box"}`}
          aria-labelledby="tenant-settings-heading"
        >
          <p className="eyebrow">Tenant Settings</p>
          <h2 id="tenant-settings-heading">Settings snapshot</h2>
          <TenantSettingsSummary settingsSnapshot={settingsSnapshot} />
        </section>

        <section
          className={`panel ${modules.ok ? "" : "error-box"}`}
          aria-labelledby="module-catalog-heading"
        >
          <p className="eyebrow">Module Catalog</p>
          <h2 id="module-catalog-heading">Registered modules</h2>
          <ModuleCatalogTable modules={modules} />
        </section>

        <section
          className={`panel ${channels.ok ? "" : "error-box"}`}
          aria-labelledby="channels-heading"
        >
          <p className="eyebrow">Channels</p>
          <h2 id="channels-heading">Available channels</h2>
          <ChannelsTable channels={channels} selectedChannelId={selectedChannelId} />
        </section>

        <section className={`panel ${models.ok ? "" : "error-box"}`} aria-labelledby="models-heading">
          <p className="eyebrow">Models</p>
          <h2 id="models-heading">Channel models</h2>
          <ModelsTable models={models} selectedChannelId={selectedChannelId} />
        </section>

        <aside>
          <section className="panel" aria-labelledby="telemetry-filter-heading">
            <p className="eyebrow">Telemetry filter</p>
            <h2 id="telemetry-filter-heading">Filter telemetry</h2>
            <TelemetryFilter
              moduleKey={moduleKey}
              runId={runId}
              selectedChannelId={selectedChannelId}
              modules={modules}
            />
          </section>

          <section
            className={`panel ${activity.ok ? "" : "error-box"}`}
            aria-labelledby="activity-heading"
          >
            <p className="eyebrow">Activity</p>
            <h2 id="activity-heading">Recent calls</h2>
            <ActivityTable activity={activity} />
          </section>

          <section
            className={`panel ${usage.ok ? "" : "error-box"}`}
            aria-labelledby="usage-heading"
          >
            <p className="eyebrow">Usage</p>
            <h2 id="usage-heading">Usage totals</h2>
            <UsageTable usage={usage} />
          </section>
        </aside>
      </div>
    </div>
  );
}

function TelemetryFilter({
  moduleKey,
  runId,
  selectedChannelId,
  modules,
}: {
  moduleKey: string;
  runId: string;
  selectedChannelId: string;
  modules: LLMModulesSummary;
}) {
  return (
    <form className="binding-form" method="get">
      <input type="hidden" name="channelId" value={selectedChannelId} />
      <label htmlFor="telemetry-module">Module</label>
      <select id="telemetry-module" name="moduleKey" defaultValue={moduleKey}>
        {modules.ok
          ? modules.items.map((registeredModule) => (
              <option key={registeredModule.module_key} value={registeredModule.module_key}>
                {registeredModule.module_key}
              </option>
            ))
          : (
              <option value={moduleKey}>{moduleKey}</option>
            )}
      </select>

      <label htmlFor="telemetry-run-id">Run ID</label>
      <input id="telemetry-run-id" name="runId" defaultValue={runId} placeholder="run_..." />

      <button type="submit">Filter telemetry</button>
    </form>
  );
}

function ChannelManagement({
  channelStatus,
  channelCode,
  channelMessage,
  syncStatus,
  syncCode,
  syncMessage,
  createChannelAction,
  updateChannelAction,
  deleteChannelAction,
  syncChannelAction,
  channels,
}: {
  channelStatus: string;
  channelCode: string;
  channelMessage: string;
  syncStatus: string;
  syncCode: string;
  syncMessage: string;
  createChannelAction: (formData: FormData) => Promise<void>;
  updateChannelAction: (formData: FormData) => Promise<void>;
  deleteChannelAction: (formData: FormData) => Promise<void>;
  syncChannelAction: (formData: FormData) => Promise<void>;
  channels: LLMChannelsSummary;
}) {
  const channelStatusClass = channelStatus === "success" ? "success-box" : "error-box";
  const syncStatusClass = syncStatus === "success" ? "success-box" : "error-box";

  return (
    <div className="binding-stack">
      {channelStatus ? (
        <p className={`form-status ${channelStatusClass}`} data-status={channelStatus}>
          {channelCode}: {channelMessage}
        </p>
      ) : null}
      {syncStatus ? (
        <p className={`form-status ${syncStatusClass}`} data-status={syncStatus}>
          {syncCode}: {syncMessage}
        </p>
      ) : null}

      <form action={createChannelAction} className="binding-form">
        <label htmlFor="channel-name">Name</label>
        <input id="channel-name" name="name" required placeholder="Draft Channel" />

        <label htmlFor="channel-provider">Provider</label>
        <select id="channel-provider" name="provider" defaultValue="openai-compatible">
          <option value="openai-compatible">openai-compatible</option>
          <option value="openai">openai</option>
        </select>

        <label htmlFor="channel-base-url">Base URL</label>
        <input
          id="channel-base-url"
          name="baseUrl"
          required
          placeholder="https://api.example.com/v1"
          type="url"
        />

        <label htmlFor="channel-api-key">API key</label>
        <input id="channel-api-key" name="apiKey" required type="password" />

        <label htmlFor="channel-concurrency">Max concurrency</label>
        <input id="channel-concurrency" min="1" name="maxConcurrency" required type="number" defaultValue="1" />

        <label className="checkbox-row">
          <input name="enabled" type="checkbox" defaultChecked />
          Enabled
        </label>

        <button type="submit">Create channel</button>
      </form>

      {channels.ok && channels.items.some((channel) => channel.scope === "tenant") ? (
        <div className="compact-action-list">
          {channels.items
            .filter((channel) => channel.scope === "tenant")
            .map((channel) => (
              <div className="channel-edit-row" key={channel.channel_id}>
                <form action={updateChannelAction} className="binding-form">
                  <input type="hidden" name="channelId" value={channel.channel_id} />
                  <label htmlFor={`channel-name-${channel.channel_id}`}>Update channel</label>
                  <input id={`channel-name-${channel.channel_id}`} name="name" defaultValue={channel.name} required />
                  <label htmlFor={`channel-base-${channel.channel_id}`}>Base URL</label>
                  <input
                    id={`channel-base-${channel.channel_id}`}
                    name="baseUrl"
                    defaultValue={channel.base_url}
                    required
                    type="url"
                  />
                  <label htmlFor={`channel-key-${channel.channel_id}`}>Rotate API key</label>
                  <input id={`channel-key-${channel.channel_id}`} name="apiKey" type="password" />
                  <label htmlFor={`channel-limit-${channel.channel_id}`}>Max concurrency</label>
                  <input
                    id={`channel-limit-${channel.channel_id}`}
                    min="1"
                    name="maxConcurrency"
                    required
                    type="number"
                    defaultValue={String(channel.max_concurrency || 1)}
                  />
                  <label className="checkbox-row">
                    <input name="enabled" type="checkbox" defaultChecked={channel.enabled} />
                    Enabled
                  </label>
                  <button type="submit">Update channel</button>
                </form>
                <form action={deleteChannelAction} className="inline-action-form">
                  <input type="hidden" name="channelId" value={channel.channel_id} />
                  <span>{channel.name}</span>
                  <button type="submit" disabled={!channel.enabled}>
                    Disable
                  </button>
                </form>
                <form action={syncChannelAction} className="inline-action-form">
                  <input type="hidden" name="channelId" value={channel.channel_id} />
                  <span>{channel.last_sync_status || "not synced"}</span>
                  <button type="submit" disabled={!channel.enabled}>
                    Sync models
                  </button>
                </form>
              </div>
            ))}
        </div>
      ) : null}

      <p className="form-hint">Credential material is encrypted by the API and never returned to this page.</p>
    </div>
  );
}

function ProjectBindingForm({
  tenantSlug,
  projectId,
  moduleKey,
  selectedChannelId,
  bindingStatus,
  bindingCode,
  bindingMessage,
  bindModuleAction,
  clearBindingAction,
  resolution,
  modules,
  channels,
  models,
}: {
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  selectedChannelId: string;
  bindingStatus: string;
  bindingCode: string;
  bindingMessage: string;
  bindModuleAction: (formData: FormData) => Promise<void>;
  clearBindingAction: (formData: FormData) => Promise<void>;
  resolution: LLMModuleResolutionSummary;
  modules: LLMModulesSummary;
  channels: LLMChannelsSummary;
  models: LLMChannelModelsSummary;
}) {
  const canBind = channels.ok && models.ok && channels.items.length > 0 && models.items.length > 0;
  const bindingStatusClass = bindingStatus === "success" ? "success-box" : "error-box";
  const moduleMaxConcurrency = resolution.ok ? positiveIntegerSetting(resolution.settings, "max_concurrency") : "";

  return (
    <div className="binding-stack">
      {bindingStatus ? (
        <p className={`form-status ${bindingStatusClass}`} data-status={bindingStatus}>
          {bindingCode}: {bindingMessage}
        </p>
      ) : null}

      <form className="binding-form" method="get">
        <input type="hidden" name="moduleKey" value={moduleKey} />
        <label htmlFor="catalog-channel">Channel catalog</label>
        <div className="inline-controls">
          <select
            id="catalog-channel"
            name="channelId"
            defaultValue={selectedChannelId}
            disabled={!channels.ok || channels.items.length === 0}
          >
            {channels.ok
              ? channels.items.map((channel) => (
                  <option key={channel.channel_id} value={channel.channel_id}>
                    {channel.name} ({channel.scope})
                  </option>
                ))
              : null}
          </select>
          <button type="submit" disabled={!channels.ok || channels.items.length === 0}>
            Load models
          </button>
        </div>
      </form>

      <form action={bindModuleAction} className="binding-form">
        <label htmlFor="module-key">Module</label>
        <select id="module-key" name="moduleKey" defaultValue={moduleKey}>
          {modules.ok
            ? modules.items.map((registeredModule) => (
                <option key={registeredModule.module_key} value={registeredModule.module_key}>
                  {registeredModule.module_key}
                </option>
              ))
            : (
                <option value={moduleKey}>{moduleKey}</option>
              )}
        </select>

        <label htmlFor="binding-channel">Channel</label>
        <select
          id="binding-channel"
          name="channelId"
          defaultValue={selectedChannelId}
          disabled={!channels.ok || channels.items.length === 0}
        >
          {channels.ok
            ? channels.items.map((channel) => (
                <option key={channel.channel_id} value={channel.channel_id}>
                  {channel.name} / {channel.provider}
                </option>
              ))
            : null}
        </select>

        <label htmlFor="binding-model">Model</label>
        <select id="binding-model" name="modelId" disabled={!models.ok || models.items.length === 0}>
          {models.ok
            ? models.items.map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {model.model_id}
                </option>
              ))
            : null}
        </select>

        <label htmlFor="binding-module-concurrency">Module max concurrency</label>
        <input
          id="binding-module-concurrency"
          min="1"
          name="moduleMaxConcurrency"
          type="number"
          defaultValue={moduleMaxConcurrency}
        />

        <button type="submit" disabled={!canBind}>
          Bind module
        </button>
      </form>

      <form action={clearBindingAction} className="inline-action-form">
        <input type="hidden" name="moduleKey" value={moduleKey} />
        <span>{moduleKey} project override</span>
        <button type="submit">Clear override</button>
      </form>

      {!channels.ok ? (
        <p className="form-hint">
          API error {channels.code}: {channels.message}
        </p>
      ) : null}
      {channels.ok && channels.items.length === 0 ? <p className="form-hint">No channels available.</p> : null}
      {!models.ok ? (
        <p className="form-hint">
          API error {models.code}: {models.message}
        </p>
      ) : null}
      {models.ok && models.items.length === 0 ? <p className="form-hint">No models available.</p> : null}
      {!modules.ok ? (
        <p className="form-hint">
          API error {modules.code}: {modules.message}
        </p>
      ) : null}
      <p className="form-hint">
        Project override for {tenantSlug}/{projectId}; credential material stays server-side.
      </p>
    </div>
  );
}

function positiveIntegerSetting(settings: Record<string, unknown>, key: string): string {
  const value = settings[key];
  const numberValue = typeof value === "number" || typeof value === "string" ? Number(value) : NaN;
  return Number.isInteger(numberValue) && numberValue > 0 ? String(numberValue) : "";
}

function ModuleCatalogTable({ modules }: { modules: LLMModulesSummary }) {
  if (!modules.ok) {
    return (
      <p>
        API error {modules.code}: {modules.message}
      </p>
    );
  }

  if (modules.items.length === 0) {
    return <p>No registered LLM modules.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Group</th>
            <th>Module</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          {modules.items.map((item) => (
            <tr key={item.module_key}>
              <td>{item.group}</td>
              <td>{item.module_key}</td>
              <td>{item.label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChannelsTable({
  channels,
  selectedChannelId,
}: {
  channels: LLMChannelsSummary;
  selectedChannelId: string;
}) {
  if (!channels.ok) {
    return (
      <p>
        API error {channels.code}: {channels.message}
      </p>
    );
  }

  if (channels.items.length === 0) {
    return <p>No LLM channels configured.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Provider</th>
            <th>Scope</th>
            <th>Status</th>
            <th>Sync</th>
          </tr>
        </thead>
        <tbody>
          {channels.items.map((item) => (
            <tr key={item.channel_id}>
              <td>{item.channel_id === selectedChannelId ? `${item.name} *` : item.name}</td>
              <td>{item.provider}</td>
              <td>{item.scope}</td>
              <td>{item.enabled ? "enabled" : "disabled"}</td>
              <td>{item.last_sync_status ? `${item.last_sync_status} ${item.last_sync_at || ""}` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelsTable({
  models,
  selectedChannelId,
}: {
  models: LLMChannelModelsSummary;
  selectedChannelId: string;
}) {
  if (!models.ok) {
    return (
      <p>
        API error {models.code}: {models.message}
      </p>
    );
  }

  if (models.items.length === 0) {
    return <p>No models cached for {selectedChannelId || "this channel"}.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Model</th>
            <th>Context</th>
            <th>Tools</th>
            <th>JSON</th>
          </tr>
        </thead>
        <tbody>
          {models.items.map((item) => (
            <tr key={item.model_id}>
              <td>{item.model_id}</td>
              <td>{item.context_window || "-"}</td>
              <td>{item.supports_tools ? "yes" : "no"}</td>
              <td>{item.supports_json ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModuleBindingsTable({ bindings }: { bindings: LLMModuleBindingsSummary }) {
  if (!bindings.ok) {
    return (
      <p>
        API error {bindings.code}: {bindings.message}
      </p>
    );
  }

  if (bindings.items.length === 0) {
    return <p>No module bindings configured.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Module</th>
            <th>Scope</th>
            <th>Channel</th>
            <th>Model</th>
          </tr>
        </thead>
        <tbody>
          {bindings.items.map((item) => (
            <tr key={`${item.scope}-${item.module_key}`}>
              <td>{item.module_key}</td>
              <td>{item.scope}</td>
              <td>{item.channel_name || item.channel_id}</td>
              <td>{item.model_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TenantSettingsSummary({ settingsSnapshot }: { settingsSnapshot: LLMSettingsSummary }) {
  if (!settingsSnapshot.ok) {
    return (
      <p>
        API error {settingsSnapshot.code}: {settingsSnapshot.message}
      </p>
    );
  }

  return (
    <div className="binding-stack">
      <dl>
        <dt>Registered modules</dt>
        <dd>{settingsSnapshot.modules.length}</dd>
        <dt>Visible channels</dt>
        <dd>{settingsSnapshot.channels.length}</dd>
        <dt>Tenant defaults</dt>
        <dd>{settingsSnapshot.tenant_bindings.length}</dd>
      </dl>
      {settingsSnapshot.tenant_bindings.length === 0 ? (
        <p>No tenant default bindings configured.</p>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Module</th>
                <th>Channel</th>
                <th>Model</th>
              </tr>
            </thead>
            <tbody>
              {settingsSnapshot.tenant_bindings.map((binding) => (
                <tr key={`tenant-settings-${binding.module_key}`}>
                  <td>{binding.module_key}</td>
                  <td>{binding.channel_name || binding.channel_id}</td>
                  <td>{binding.model_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ModuleBinding({
  resolution,
  moduleKey,
}: {
  resolution: LLMModuleResolutionSummary;
  moduleKey: string;
}) {
  if (!resolution.ok) {
    return (
      <p>
        API error {resolution.code}: {resolution.message}
      </p>
    );
  }

  return (
    <dl>
      <dt>Module</dt>
      <dd>{resolution.module_key || moduleKey}</dd>
      <dt>Provider</dt>
      <dd>{resolution.provider}</dd>
      <dt>Channel</dt>
      <dd>{resolution.channel_id}</dd>
      <dt>Model</dt>
      <dd>{resolution.model_id}</dd>
      <dt>Base URL</dt>
      <dd>{resolution.base_url}</dd>
      <dt>Tools</dt>
      <dd>{resolution.supports_tools ? "supported" : "not supported"}</dd>
      <dt>JSON</dt>
      <dd>{resolution.supports_json ? "supported" : "not supported"}</dd>
    </dl>
  );
}

function ActivityTable({ activity }: { activity: LLMActivitySummary }) {
  if (!activity.ok) {
    return (
      <p>
        API error {activity.code}: {activity.message}
      </p>
    );
  }

  if (activity.items.length === 0) {
    return <p>No activity recorded.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Run</th>
            <th>Tokens</th>
            <th>Latency</th>
          </tr>
        </thead>
        <tbody>
          {activity.items.map((item) => (
            <tr key={item.activity_id}>
              <td>{item.status}</td>
              <td>{item.run_id || "-"}</td>
              <td>{item.prompt_tokens + item.completion_tokens}</td>
              <td>{item.latency_ms ? `${item.latency_ms}ms` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UsageTable({ usage }: { usage: LLMUsageSummary }) {
  if (!usage.ok) {
    return (
      <p>
        API error {usage.code}: {usage.message}
      </p>
    );
  }

  if (usage.items.length === 0) {
    return <p>No usage recorded.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Quantity</th>
            <th>Unit</th>
          </tr>
        </thead>
        <tbody>
          {usage.items.map((item) => (
            <tr key={`${item.usage_type}-${item.module_key}-${item.run_id}`}>
              <td>{item.usage_type}</td>
              <td>{item.quantity}</td>
              <td>{item.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
