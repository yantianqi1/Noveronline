import { GuideShell } from "../../../../../../components/guide-shell";

export default async function GuidePage({
  params,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
}) {
  const { tenantSlug, projectId } = await params;

  return <GuideShell projectId={projectId} tenantSlug={tenantSlug} />;
}
