"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createProject, renameProject } from "../../../../../lib/project-admin-api";
import { webApiContext } from "../../../../../lib/server-auth";
import { workspaceBasePathForProject } from "../../../../../lib/workspace-route";

export type ProjectActionState = { ok: boolean; error?: string };

export async function createProjectAction(
  tenantSlug: string,
  _previousState: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const title = textField(formData, "title");
  if (!title) {
    return { ok: false, error: "VALIDATION_FAILED" };
  }
  let context;
  try {
    context = await webApiContext({ tenantId: tenantSlug });
  } catch {
    return { ok: false, error: "SESSION_REQUIRED" };
  }
  const result = await createProject({ ...context, title });
  if (!result.ok) {
    return { ok: false, error: result.code };
  }
  revalidatePath("/", "layout");
  redirect(workspaceBasePathForProject([], { tenant_id: result.project.tenant_id, project_id: result.project.project_id, name: result.project.title }));
}

export async function renameProjectAction(
  tenantSlug: string,
  projectId: string,
  _previousState: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const title = textField(formData, "title");
  if (!title) {
    return { ok: false, error: "VALIDATION_FAILED" };
  }
  let context;
  try {
    context = await webApiContext({ tenantId: tenantSlug });
  } catch {
    return { ok: false, error: "SESSION_REQUIRED" };
  }
  const result = await renameProject({ ...context, projectId, title });
  if (!result.ok) {
    return { ok: false, error: result.code };
  }
  revalidatePath("/", "layout");
  return { ok: true };
}

function textField(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}
