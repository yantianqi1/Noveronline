import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { AssetDetailShell } from "../../../../../../../components/asset-detail-shell";
import {
  createAssetCollection,
  deleteAssetCollection,
  getAssetCollections,
  getAssetDetail,
  getAssetVersions,
  removeAssetMembership,
  reorderAssetCollection,
  restoreAssetVersion,
  setAssetMembership,
  updateAssetDetail,
} from "../../../../../../../lib/asset-detail-api";

export const dynamic = "force-dynamic";

export default async function AssetDetailPage({ params, searchParams }: {
  params: Promise<{ tenantSlug: string; projectId: string; assetId: string }>;
  searchParams?: Promise<{ status?: string; code?: string }>;
}) {
  const { tenantSlug, projectId, assetId } = await params;
  const query = searchParams ? await searchParams : {};
  const context = { tenantId: tenantSlug, projectId, assetId };
  const [detail, versions, collections] = await Promise.all([
    getAssetDetail(context), getAssetVersions(context), getAssetCollections(context),
  ]);
  if (!detail.ok && detail.code === "NOT_FOUND") notFound();
  if (!detail.ok) return <AssetDetailShell failure={detail} />;

  const route = `/${tenantSlug}/projects/${projectId}/assets/${assetId}`;
  async function finish(result: { ok: boolean; code?: string }) {
    "use server";
    if (result.ok) { revalidatePath(route); redirect(`${route}?status=updated`); }
    redirect(`${route}?status=error&code=${encodeURIComponent(result.code ?? "ASSET_CATALOG_FAILED")}`);
  }
  async function updateAction(formData: FormData) {
    "use server";
    const result = await updateAssetDetail(context, {
      expected_version: Number(formData.get("expectedVersion")),
      title: String(formData.get("title") ?? "").trim(),
      summary: String(formData.get("summary") ?? "").trim(),
      content_text: String(formData.get("contentText") ?? ""),
      tags: String(formData.get("tags") ?? "").split(",").map((tag) => tag.trim()).filter(Boolean),
      pinned: formData.get("pinned") === "on",
      enabled: formData.get("enabled") === "on",
    });
    await finish(result);
  }
  async function restoreAction(formData: FormData) {
    "use server";
    const result = await restoreAssetVersion(context, { expected_version: Number(formData.get("expectedVersion")), version_number: Number(formData.get("versionNumber")) });
    await finish(result);
  }
  async function createCollectionAction(formData: FormData) {
    "use server";
    const result = await createAssetCollection(context, { title: String(formData.get("title") ?? "").trim(), summary: String(formData.get("summary") ?? "").trim(), lifecycle: "material", metadata: {} });
    await finish(result);
  }
  async function addMembershipAction(formData: FormData) {
    "use server";
    const result = await setAssetMembership(context, String(formData.get("collectionId") ?? ""));
    await finish(result);
  }
  async function removeMembershipAction(formData: FormData) {
    "use server";
    const result = await removeAssetMembership(context, String(formData.get("collectionId") ?? ""));
    await finish(result);
  }
  async function deleteCollectionAction(formData: FormData) {
    "use server";
    const result = await deleteAssetCollection(context, String(formData.get("collectionId") ?? ""));
    await finish(result);
  }
  async function reorderCollectionAction(formData: FormData) {
    "use server";
    const result = await reorderAssetCollection(context, String(formData.get("collectionId") ?? ""), String(formData.get("assetIds") ?? "").split(",").filter(Boolean));
    await finish(result);
  }

  return <AssetDetailShell
    asset={detail.value}
    versions={versions.ok ? versions.value : []}
    collections={collections.ok ? collections.value : []}
    status={query.status}
    errorCode={query.code}
    updateAction={updateAction}
    restoreAction={restoreAction}
    createCollectionAction={createCollectionAction}
    addMembershipAction={addMembershipAction}
    removeMembershipAction={removeMembershipAction}
    deleteCollectionAction={deleteCollectionAction}
    reorderCollectionAction={reorderCollectionAction}
  />;
}
