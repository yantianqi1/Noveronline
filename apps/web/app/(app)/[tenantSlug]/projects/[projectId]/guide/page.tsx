import { redirect } from "next/navigation";

export default async function GuidePage({
  params,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
}) {
  const { tenantSlug, projectId } = await params;

  redirect(`/${tenantSlug}/projects/${projectId}/overview`);
}
