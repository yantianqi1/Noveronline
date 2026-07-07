import type {
  ArchiveMemoryEventsSummary,
  ArchiveMemorySummary,
  AssetFacetsSummary,
  AssetListSummary,
  AssetSearchSummary,
} from "../lib/api";

type AssetLibraryShellProps = {
  tenantSlug: string;
  projectId: string;
  searchQuery: string;
  assetStatus: string;
  assetCode: string;
  assetMessage: string;
  bulkStatus: string;
  bulkCode: string;
  bulkMessage: string;
  ingestionStatus: string;
  ingestionCode: string;
  ingestionMessage: string;
  memoryStatus: string;
  memoryCode: string;
  memoryMessage: string;
  reindexStatus: string;
  reindexCode: string;
  reindexMessage: string;
  styleStatus: string;
  styleCode: string;
  styleMessage: string;
  assets: AssetListSummary;
  facets: AssetFacetsSummary;
  searchResults: AssetSearchSummary | null;
  memoryAssetId: string;
  archiveMemories: ArchiveMemorySummary | null;
  archiveMemoryEvents: ArchiveMemoryEventsSummary | null;
  searchAction: (formData: FormData) => Promise<void>;
  memoryAssetAction: (formData: FormData) => Promise<void>;
  createAssetAction: (formData: FormData) => Promise<void>;
  updateAssetAction: (formData: FormData) => Promise<void>;
  deleteAssetAction: (formData: FormData) => Promise<void>;
  adoptAssetAction: (formData: FormData) => Promise<void>;
  adoptArchiveMemoryAction: (formData: FormData) => Promise<void>;
  rejectArchiveMemoryAction: (formData: FormData) => Promise<void>;
  bulkAssetAction: (formData: FormData) => Promise<void>;
  ingestAssetAction: (formData: FormData) => Promise<void>;
  reindexAssetsAction: (formData: FormData) => Promise<void>;
  extractStyleAction: (formData: FormData) => Promise<void>;
};

export function AssetLibraryShell({
  tenantSlug,
  projectId,
  searchQuery,
  assetStatus,
  assetCode,
  assetMessage,
  bulkStatus,
  bulkCode,
  bulkMessage,
  ingestionStatus,
  ingestionCode,
  ingestionMessage,
  memoryStatus,
  memoryCode,
  memoryMessage,
  reindexStatus,
  reindexCode,
  reindexMessage,
  styleStatus,
  styleCode,
  styleMessage,
  assets,
  facets,
  searchResults,
  memoryAssetId,
  archiveMemories,
  archiveMemoryEvents,
  searchAction,
  memoryAssetAction,
  createAssetAction,
  updateAssetAction,
  deleteAssetAction,
  adoptAssetAction,
  adoptArchiveMemoryAction,
  rejectArchiveMemoryAction,
  bulkAssetAction,
  ingestAssetAction,
  reindexAssetsAction,
  extractStyleAction,
}: AssetLibraryShellProps) {
  return (
    <div>
      <header>
        <p className="eyebrow">Asset Library</p>
        <h1>Asset Library</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <span className="status-pill">Assets: {assets.ok ? assets.items.length : assets.code}</span>{" "}
        <span className="status-pill">Search: {searchResults?.ok ? searchResults.items.length : searchQuery || "idle"}</span>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section className={`panel ${assets.ok ? "" : "error-box"}`} aria-labelledby="assets-heading">
            <p className="eyebrow">Assets</p>
            <h2 id="assets-heading">Project assets</h2>
            <AssetList assets={assets} />
          </section>

          <section
            className={`panel ${searchResults === null || searchResults.ok ? "" : "error-box"}`}
            aria-labelledby="search-heading"
          >
            <p className="eyebrow">Search</p>
            <h2 id="search-heading">Keyword results</h2>
            <form action={searchAction} className="inline-controls">
              <input
                aria-label="Search assets"
                defaultValue={searchQuery}
                name="query"
                placeholder="world rule, character, style"
              />
              <button type="submit">Search</button>
            </form>
            <SearchResults searchResults={searchResults} />
          </section>

          <section
            className={`panel ${archiveMemories === null || archiveMemories.ok ? "" : "error-box"}`}
            aria-labelledby="archive-memory-heading"
          >
            <p className="eyebrow">Archive Memory</p>
            <h2 id="archive-memory-heading">Memory review</h2>
            <StatusLine status={memoryStatus} code={memoryCode} message={memoryMessage} />
            <form action={memoryAssetAction} className="inline-controls">
              <input
                aria-label="Archive asset ID"
                defaultValue={memoryAssetId}
                name="memoryAssetId"
                placeholder="archive asset id"
              />
              <button type="submit">View</button>
            </form>
            <ArchiveMemoryPanel
              memories={archiveMemories}
              events={archiveMemoryEvents}
              adoptAction={adoptArchiveMemoryAction}
              rejectAction={rejectArchiveMemoryAction}
            />
          </section>
        </main>

        <aside>
          <section className={`panel ${facets.ok ? "" : "error-box"}`} aria-labelledby="facets-heading">
            <p className="eyebrow">Facets</p>
            <h2 id="facets-heading">Buckets</h2>
            <FacetSummary facets={facets} />
          </section>

          <section className="panel" aria-labelledby="asset-actions-heading">
            <p className="eyebrow">Asset Actions</p>
            <h2 id="asset-actions-heading">Create asset</h2>
            <StatusLine status={assetStatus} code={assetCode} message={assetMessage} />
            <CreateAssetForm action={createAssetAction} />
          </section>

          <section className="panel" aria-labelledby="asset-update-heading">
            <p className="eyebrow">Asset Actions</p>
            <h2 id="asset-update-heading">Update asset</h2>
            <UpdateAssetForm action={updateAssetAction} />
          </section>

          <section className="panel" aria-labelledby="asset-delete-heading">
            <p className="eyebrow">Asset Actions</p>
            <h2 id="asset-delete-heading">Delete asset</h2>
            <DeleteAssetForm action={deleteAssetAction} />
          </section>

          <section className="panel" aria-labelledby="asset-adoption-heading">
            <p className="eyebrow">Candidate Review</p>
            <h2 id="asset-adoption-heading">Adopt candidate</h2>
            <AdoptAssetForm action={adoptAssetAction} />
          </section>

          <section className="panel" aria-labelledby="asset-bulk-heading">
            <p className="eyebrow">Asset Actions</p>
            <h2 id="asset-bulk-heading">Bulk action</h2>
            <StatusLine status={bulkStatus} code={bulkCode} message={bulkMessage} />
            <BulkAssetActionForm action={bulkAssetAction} />
          </section>

          <section className="panel" aria-labelledby="asset-ingestion-heading">
            <p className="eyebrow">Asset Ingestion</p>
            <h2 id="asset-ingestion-heading">Ingest material</h2>
            <StatusLine status={ingestionStatus} code={ingestionCode} message={ingestionMessage} />
            <IngestAssetForm action={ingestAssetAction} />
          </section>

          <section className="panel" aria-labelledby="asset-reindex-heading">
            <p className="eyebrow">Asset Search</p>
            <h2 id="asset-reindex-heading">Reindex assets</h2>
            <StatusLine status={reindexStatus} code={reindexCode} message={reindexMessage} />
            <ReindexAssetsForm action={reindexAssetsAction} />
          </section>

          <section className="panel" aria-labelledby="style-extraction-heading">
            <p className="eyebrow">Style Extraction</p>
            <h2 id="style-extraction-heading">Extract style</h2>
            <StatusLine status={styleStatus} code={styleCode} message={styleMessage} />
            <ExtractStyleForm action={extractStyleAction} />
          </section>
        </aside>
      </div>
    </div>
  );
}

function StatusLine({ status, code, message }: { status: string; code: string; message: string }) {
  if (!status) {
    return null;
  }
  const statusClass = status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={status}>
      {code}: {message}
    </p>
  );
}

function AssetList({ assets }: { assets: AssetListSummary }) {
  if (!assets.ok) {
    return <p className="form-status error-box">{assets.code}: {assets.message}</p>;
  }
  if (assets.items.length === 0) {
    return <p className="form-hint">No assets returned.</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Type</th>
            <th>Lifecycle</th>
            <th>Source</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {assets.items.map((asset) => (
            <tr key={asset.asset_id}>
              <td>
                <strong>{asset.title}</strong>
                <br />
                <span className="form-hint">{asset.asset_id}</span>
              </td>
              <td>{asset.asset_type}</td>
              <td>{asset.lifecycle}</td>
              <td>{asset.source_kind}</td>
              <td>{asset.updated_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SearchResults({ searchResults }: { searchResults: AssetSearchSummary | null }) {
  if (searchResults === null) {
    return <p className="form-hint">No search submitted.</p>;
  }
  if (!searchResults.ok) {
    return <p className="form-status error-box">{searchResults.code}: {searchResults.message}</p>;
  }
  if (searchResults.items.length === 0) {
    return <p className="form-hint">No search results returned.</p>;
  }
  return (
    <div className="trace-list" style={{ marginTop: 12 }}>
      {searchResults.items.map((item) => (
        <article className="trace-event" key={item.search_document_id}>
          <div className="trace-event-header">
            <strong>{item.title}</strong>
            <span className="trace-redaction">{item.entity_type || item.source}</span>
          </div>
          <p className="trace-meta">{item.source}:{item.source_ref}</p>
          <p className="trace-meta">
            Versions: {item.version.count}
            {item.version.latest_version > 0 ? ` · latest v${item.version.latest_version}` : ""} · Collections:{" "}
            {item.collections.length}
            {item.collections.length > 0 ? ` · ${item.collections.map((collection) => collection.title).join(", ")}` : ""}
          </p>
          {item.tags.length > 0 ? <p className="trace-meta">Tags: {item.tags.join(", ")}</p> : null}
        </article>
      ))}
    </div>
  );
}

function ArchiveMemoryPanel({
  memories,
  events,
  adoptAction,
  rejectAction,
}: {
  memories: ArchiveMemorySummary | null;
  events: ArchiveMemoryEventsSummary | null;
  adoptAction: (formData: FormData) => Promise<void>;
  rejectAction: (formData: FormData) => Promise<void>;
}) {
  if (memories === null) {
    return <p className="form-hint">No archive asset selected.</p>;
  }
  if (!memories.ok) {
    return <p className="form-status error-box">{memories.code}: {memories.message}</p>;
  }
  return (
    <div className="trace-list" style={{ marginTop: 12 }}>
      {memories.items.length === 0 ? (
        <p className="form-hint">No memories returned.</p>
      ) : (
        memories.items.map((memory) => (
          <article className="trace-event" key={memory.memory_id}>
            <div className="trace-event-header">
              <strong>{memory.memory_type}</strong>
              <span className="trace-redaction">{memory.status}</span>
            </div>
            <p className="trace-meta">{memory.source_kind}:{memory.source_ref}</p>
            <p>{memory.summary}</p>
            {memory.status === "candidate" ? (
              <div className="inline-controls">
                <form action={adoptAction}>
                  <input name="memoryId" type="hidden" value={memory.memory_id} />
                  <button type="submit">Adopt memory</button>
                </form>
                <form action={rejectAction}>
                  <input name="memoryId" type="hidden" value={memory.memory_id} />
                  <button type="submit">Reject memory</button>
                </form>
              </div>
            ) : null}
          </article>
        ))
      )}
      <ArchiveMemoryEvents events={events} />
    </div>
  );
}

function ArchiveMemoryEvents({ events }: { events: ArchiveMemoryEventsSummary | null }) {
  if (events === null) {
    return null;
  }
  if (!events.ok) {
    return <p className="form-status error-box">{events.code}: {events.message}</p>;
  }
  return (
    <div className="compact-action-list">
      <strong>Events</strong>
      {events.items.length === 0 ? (
        <span className="status-pill">empty</span>
      ) : (
        events.items.map((event) => (
          <span className="status-pill" key={event.event_id}>
            {event.event_type}: {event.status}
          </span>
        ))
      )}
    </div>
  );
}

function FacetSummary({ facets }: { facets: AssetFacetsSummary }) {
  if (!facets.ok) {
    return <p className="form-status error-box">{facets.code}: {facets.message}</p>;
  }
  return (
    <div className="compact-action-list">
      <FacetGroup label="Types" items={facets.asset_types} />
      <FacetGroup label="Categories" items={facets.categories} />
      <FacetGroup label="Lifecycles" items={facets.lifecycles} />
      <FacetGroup label="Sources" items={facets.sources} />
      <FacetGroup label="Tags" items={facets.tags} />
    </div>
  );
}

function FacetGroup({ label, items }: { label: string; items: { value: string; count: number }[] }) {
  return (
    <div>
      <strong>{label}</strong>
      <div className="facet-pills">
        {items.length === 0 ? (
          <span className="status-pill">empty</span>
        ) : (
          items.map((item) => (
            <span className="status-pill" key={`${label}-${item.value}`}>
              {item.value}: {item.count}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

function CreateAssetForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="asset-title">Title</label>
      <input id="asset-title" name="title" required />

      <label htmlFor="asset-type">Asset type</label>
      <input id="asset-type" name="assetType" required defaultValue="note" />

      <label htmlFor="asset-category">Category</label>
      <input id="asset-category" name="category" defaultValue="material" />

      <label htmlFor="asset-lifecycle">Lifecycle</label>
      <select id="asset-lifecycle" name="lifecycle" defaultValue="material">
        <option value="material">material</option>
        <option value="canon">canon</option>
        <option value="candidate">candidate</option>
        <option value="archived">archived</option>
      </select>

      <label htmlFor="asset-summary">Summary</label>
      <textarea id="asset-summary" name="summary" rows={3} />

      <label htmlFor="asset-content">Private content</label>
      <textarea id="asset-content" name="contentText" rows={4} />

      <label htmlFor="asset-tags">Tags</label>
      <input id="asset-tags" name="tags" placeholder="style, rule, note" />

      <label htmlFor="asset-payload">Payload JSON</label>
      <textarea id="asset-payload" name="payload" rows={4} defaultValue="{}" />

      <label htmlFor="asset-source-kind">Source kind</label>
      <input id="asset-source-kind" name="sourceKind" defaultValue="manual" />

      <label htmlFor="asset-source-ref">Source ref</label>
      <input id="asset-source-ref" name="sourceRef" placeholder="optional" />

      <label className="checkbox-row">
        <input name="enabled" type="checkbox" defaultChecked />
        Enabled
      </label>
      <label className="checkbox-row">
        <input name="pinned" type="checkbox" />
        Pinned
      </label>

      <button type="submit">Create asset</button>
    </form>
  );
}

function UpdateAssetForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="update-asset-id">Asset ID</label>
      <input id="update-asset-id" name="assetId" required />

      <label htmlFor="update-title">Title</label>
      <input id="update-title" name="title" />

      <label htmlFor="update-lifecycle">Lifecycle</label>
      <select id="update-lifecycle" name="lifecycle" defaultValue="">
        <option value="">unchanged</option>
        <option value="material">material</option>
        <option value="canon">canon</option>
        <option value="candidate">candidate</option>
        <option value="archived">archived</option>
      </select>

      <label htmlFor="update-summary">Summary</label>
      <textarea id="update-summary" name="summary" rows={3} />

      <label htmlFor="update-content">Private content</label>
      <textarea id="update-content" name="contentText" rows={3} />

      <label htmlFor="update-tags">Tags</label>
      <input id="update-tags" name="tags" />

      <label htmlFor="update-payload">Payload JSON</label>
      <textarea id="update-payload" name="payload" rows={3} />

      <label className="checkbox-row">
        <input name="enabled" type="checkbox" defaultChecked />
        Enabled
      </label>
      <label className="checkbox-row">
        <input name="pinned" type="checkbox" />
        Pinned
      </label>

      <button type="submit">Update asset</button>
    </form>
  );
}

function DeleteAssetForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="inline-action-form">
      <input aria-label="Asset ID to delete" name="assetId" required placeholder="asset id" />
      <button className="danger-action" type="submit">Delete asset</button>
    </form>
  );
}

function AdoptAssetForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="adopt-asset-id">Asset ID</label>
      <input id="adopt-asset-id" name="assetId" required />

      <label htmlFor="adopt-target">Target lifecycle</label>
      <select id="adopt-target" name="targetLifecycle" defaultValue="canon">
        <option value="canon">canon</option>
        <option value="material">material</option>
      </select>

      <button type="submit">Adopt candidate</button>
    </form>
  );
}

function BulkAssetActionForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="bulk-asset-ids">Asset IDs</label>
      <textarea id="bulk-asset-ids" name="assetIds" required rows={3} />

      <label htmlFor="bulk-action">Action</label>
      <select id="bulk-action" name="bulkAction" defaultValue="disable">
        <option value="disable">disable</option>
        <option value="enable">enable</option>
        <option value="set_lifecycle">set_lifecycle</option>
        <option value="categorize">categorize</option>
        <option value="pin">pin</option>
        <option value="unpin">unpin</option>
      </select>

      <label htmlFor="bulk-target-lifecycle">Target lifecycle</label>
      <select id="bulk-target-lifecycle" name="targetLifecycle" defaultValue="">
        <option value="">unchanged</option>
        <option value="material">material</option>
        <option value="canon">canon</option>
        <option value="candidate">candidate</option>
        <option value="archived">archived</option>
      </select>

      <label htmlFor="bulk-category">Category</label>
      <input id="bulk-category" name="category" placeholder="optional" />

      <label htmlFor="bulk-enabled">Enabled override</label>
      <select id="bulk-enabled" name="enabled" defaultValue="">
        <option value="">unchanged</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>

      <label htmlFor="bulk-pinned">Pinned override</label>
      <select id="bulk-pinned" name="pinned" defaultValue="">
        <option value="">unchanged</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>

      <button type="submit">Apply bulk action</button>
    </form>
  );
}

function IngestAssetForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="ingest-hint">Hint type</label>
      <select id="ingest-hint" name="hintType" defaultValue="note">
        <option value="note">note</option>
        <option value="writing_style">writing_style</option>
        <option value="world_rule">world_rule</option>
        <option value="character_archetype">character_archetype</option>
        <option value="plot_template">plot_template</option>
      </select>

      <label htmlFor="ingest-scope">Scope</label>
      <select id="ingest-scope" name="scope" defaultValue="project">
        <option value="project">project</option>
        <option value="tenant">tenant</option>
      </select>

      <label htmlFor="ingest-material">Material</label>
      <textarea id="ingest-material" name="materialText" required rows={5} />

      <button type="submit">Ingest material</button>
    </form>
  );
}

function ReindexAssetsForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="reindex-scope">Scope</label>
      <select id="reindex-scope" name="scope" defaultValue="project">
        <option value="project">project</option>
        <option value="tenant">tenant</option>
      </select>

      <label htmlFor="reindex-mode">Mode</label>
      <select id="reindex-mode" name="mode" defaultValue="keyword">
        <option value="keyword">keyword</option>
        <option value="hybrid">hybrid</option>
      </select>

      <button type="submit">Start reindex</button>
    </form>
  );
}

function ExtractStyleForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="style-source-asset">Source asset ID</label>
      <input id="style-source-asset" name="sourceAssetId" placeholder="optional" />

      <label htmlFor="style-scope">Scope</label>
      <select id="style-scope" name="scope" defaultValue="project">
        <option value="project">project</option>
        <option value="tenant">tenant</option>
      </select>

      <label htmlFor="style-material">Material</label>
      <textarea id="style-material" name="materialText" rows={5} />

      <button type="submit">Extract style</button>
    </form>
  );
}
