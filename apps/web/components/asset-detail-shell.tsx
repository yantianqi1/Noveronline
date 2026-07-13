import Link from "next/link";
import { ArrowDown, ArrowLeft, ArrowUp, BookOpen, FolderPlus, History, RotateCcw, Save, Trash2, X } from "lucide-react";
import type { AssetCatalogFailure, AssetCollection, AssetDetail, AssetVersion } from "../lib/asset-detail-api";
import { PublicErrorNotice } from "./public-error-notice";
import styles from "./asset-detail-shell.module.css";

type Action = (formData: FormData) => Promise<void>;
type Props = {
  asset?: AssetDetail;
  versions?: AssetVersion[];
  collections?: AssetCollection[];
  failure?: AssetCatalogFailure;
  status?: string;
  errorCode?: string;
  updateAction?: Action;
  restoreAction?: Action;
  createCollectionAction?: Action;
  addMembershipAction?: Action;
  removeMembershipAction?: Action;
  deleteCollectionAction?: Action;
  reorderCollectionAction?: Action;
};

export function AssetDetailShell(props: Props) {
  if (props.failure || !props.asset) {
    return (
      <main className={styles.failure}>
        <BookOpen size={24} />
        <PublicErrorNotice
          message="This asset is temporarily unavailable. Try again from the asset library."
          recovery="Return to the library and open the asset again."
          title="Asset unavailable"
        />
        <Link className={styles.back} href="../">Back to assets</Link>
      </main>
    );
  }
  const { asset } = props;
  const versions = props.versions ?? [];
  const collections = props.collections ?? [];
  const memberships = new Set(asset.collections.map((item) => item.collection_id));
  const available = collections.filter((collection) => !memberships.has(collection.collection_id));

  return <main className={styles.workspace} data-testid="asset-detail-workspace">
    <header className={styles.header}>
      <Link className={styles.back} href={`../`} aria-label="Back to assets"><ArrowLeft size={18}/></Link>
      <div><div className={styles.eyebrow}>{asset.asset_type} / {asset.lifecycle}</div><h1>{asset.title}</h1><p>{asset.summary || "No summary"}</p></div>
      <div className={styles.version}>Current version <strong>{asset.current_version}</strong></div>
    </header>

    {props.status === "updated" && <div className={styles.notice} role="status">Changes saved and refreshed.</div>}
    {props.status === "error" && (
      <PublicErrorNotice
        message="The change could not be saved. Your current view may be out of date."
        recovery="Refresh the page, then try the action again."
        title="Operation incomplete"
      />
    )}

    <div className={styles.grid}>
      <section className={styles.primary}>
        <div className={styles.sectionHead}><div><h2>Asset record</h2><p>Metadata and permission-scoped content</p></div></div>
        <dl className={styles.metadata}>
          <div><dt>Source</dt><dd>{humanizeSourceKind(asset.source.kind)}</dd></div>
          <div><dt>Category</dt><dd>{asset.category || "Uncategorized"}</dd></div>
          <div><dt>State</dt><dd>{asset.enabled ? "Enabled" : "Disabled"}{asset.pinned ? " / Pinned" : ""}</dd></div>
          <div><dt>Updated</dt><dd>{formatDate(asset.updated_at)}</dd></div>
        </dl>
        <div className={styles.tags}>{asset.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>

        {asset.capabilities.mutate && props.updateAction ? <form action={props.updateAction} className={styles.form} data-testid="asset-update-form">
          <input type="hidden" name="expectedVersion" value={asset.current_version}/>
          <label>Title<input name="title" defaultValue={asset.title} required maxLength={240}/></label>
          <label>Summary<textarea name="summary" defaultValue={asset.summary ?? ""} rows={3}/></label>
          <label>Tags<input name="tags" defaultValue={asset.tags.join(", ")} placeholder="world, canon"/></label>
          {asset.capabilities.read_private && <label>Private content<textarea name="contentText" defaultValue={asset.private?.content_text ?? ""} rows={12} data-testid="private-content"/></label>}
          <div className={styles.toggles}><label><input type="checkbox" name="enabled" defaultChecked={asset.enabled}/> Enabled</label><label><input type="checkbox" name="pinned" defaultChecked={asset.pinned}/> Pinned</label></div>
          <button className={styles.primaryButton} type="submit"><Save size={16}/> Save new version</button>
        </form> : <div className={styles.readOnly}>Viewer access. Mutation controls are unavailable.</div>}
      </section>

      <aside className={styles.rail}>
        <section className={styles.panel}>
          <div className={styles.sectionHead}><div><h2><History size={17}/> Version history</h2><p>Immutable metadata snapshots</p></div></div>
          <ol className={styles.timeline} data-testid="version-timeline">
            {versions.length === 0 && <li className={styles.empty}>No prior versions</li>}
            {versions.map((version) => <li key={version.version_id}>
              <div><strong>v{version.version_number}</strong><span>{version.title || "Untitled"}</span><time>{formatDate(version.created_at)}</time></div>
              {asset.capabilities.mutate && props.restoreAction && <details><summary><RotateCcw size={14}/> Restore</summary><form action={props.restoreAction}>
                <input type="hidden" name="expectedVersion" value={asset.current_version}/><input type="hidden" name="versionNumber" value={version.version_number}/>
                <label className={styles.confirm}><input type="checkbox" required/> Create a new current version from v{version.version_number}</label>
                <button type="submit">Confirm restore</button>
              </form></details>}
            </li>)}
          </ol>
        </section>

        <section className={styles.panel}>
          <div className={styles.sectionHead}><div><h2><FolderPlus size={17}/> Collections</h2><p>Ordered knowledge sets</p></div></div>
          {asset.capabilities.manage_collections && props.addMembershipAction && available.length > 0 && <form action={props.addMembershipAction} className={styles.inlineForm}>
            <select name="collectionId" aria-label="Collection to add">{available.map((collection) => <option key={collection.collection_id} value={collection.collection_id}>{collection.title}</option>)}</select>
            <button type="submit">Add</button>
          </form>}
          <div className={styles.collectionList} data-testid="collection-memberships">
            {collections.filter((collection) => memberships.has(collection.collection_id)).map((collection) => <CollectionRow key={collection.collection_id} collection={collection} asset={asset} {...props}/>) }
            {asset.collections.length === 0 && <p className={styles.empty}>Not in a collection</p>}
          </div>
          {asset.capabilities.manage_collections && props.createCollectionAction && <details className={styles.create}><summary>New collection</summary><form action={props.createCollectionAction} className={styles.form}>
            <label>Title<input name="title" required maxLength={240}/></label><label>Summary<input name="summary"/></label><button type="submit"><FolderPlus size={15}/> Create</button>
          </form></details>}
        </section>
      </aside>
    </div>
  </main>;
}

function CollectionRow({ collection, asset, removeMembershipAction, deleteCollectionAction, reorderCollectionAction }: Props & { collection: AssetCollection; asset: AssetDetail }) {
  const index = collection.items.findIndex((item) => item.asset_id === asset.asset_id);
  const order = (direction: -1 | 1) => { const ids = collection.items.map((item) => item.asset_id); const next = index + direction; if (index < 0 || next < 0 || next >= ids.length) return ids; [ids[index], ids[next]] = [ids[next], ids[index]]; return ids; };
  return <article className={styles.collection}>
    <div><strong>{collection.title}</strong><span>{collection.items.length} assets</span></div>
    {asset.capabilities.manage_collections && <div className={styles.iconActions}>
      {[-1, 1].map((direction) => <form action={reorderCollectionAction!} key={direction}><input type="hidden" name="collectionId" value={collection.collection_id}/><input type="hidden" name="assetIds" value={order(direction as -1 | 1).join(",")}/><button type="submit" disabled={(direction === -1 && index <= 0) || (direction === 1 && index >= collection.items.length - 1)} aria-label={direction === -1 ? "Move asset up" : "Move asset down"}>{direction === -1 ? <ArrowUp size={15}/> : <ArrowDown size={15}/>}</button></form>)}
      <form action={removeMembershipAction!}><input type="hidden" name="collectionId" value={collection.collection_id}/><button type="submit" aria-label="Remove from collection"><X size={15}/></button></form>
      <form action={deleteCollectionAction!}><input type="hidden" name="collectionId" value={collection.collection_id}/><button type="submit" aria-label="Delete collection"><Trash2 size={15}/></button></form>
    </div>}
  </article>;
}

function humanizeSourceKind(kind: string) {
  if (!kind) {
    return "Unknown";
  }
  return kind.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value: string) { return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
