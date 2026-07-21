"use client";

import type {
  Chapter,
  ManuscriptBlock,
  ManuscriptVersion,
  PrivateManuscriptBlock,
  Scene,
} from "../lib/writer-workspace-api";

/**
 * Browser-side reader for the writer workspace BFF proxy. Returns parsed
 * payloads or throws on failure so callers can render an inline error rather
 * than navigating away. Mirrors the metadata shapes from writer-workspace-api.
 */

type Envelope<T> = { ok: boolean; data?: T; code?: string };

function base(tenantSlug: string, projectId: string) {
  return `/api/writer-workspace/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(projectId)}`;
}

async function read<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store", credentials: "same-origin" });
  const payload = (await response.json().catch(() => null)) as Envelope<T> | null;
  if (!response.ok || !payload?.ok) {
    throw new Error(payload?.code ?? "WRITER_WORKSPACE_UNAVAILABLE");
  }
  return payload.data as T;
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

export async function fetchChapters(tenantSlug: string, projectId: string): Promise<Chapter[]> {
  const data = await read<{ data?: Chapter[] | null } | Chapter[]>(`${base(tenantSlug, projectId)}?resource=chapters`);
  // chapters use the envelope { data: [...] } shape
  if (Array.isArray(data)) return data;
  return asArray((data as { data?: Chapter[] | null }).data);
}

export async function fetchScenes(tenantSlug: string, projectId: string, chapterId: string): Promise<Scene[]> {
  const data = await read<{ data?: Scene[] | null } | Scene[]>(
    `${base(tenantSlug, projectId)}?resource=scenes&chapterId=${encodeURIComponent(chapterId)}`,
  );
  if (Array.isArray(data)) return data;
  return asArray((data as { data?: Scene[] | null }).data);
}

export async function fetchBlocks(tenantSlug: string, projectId: string): Promise<ManuscriptBlock[]> {
  const data = await read<{ blocks?: ManuscriptBlock[] | null }>(`${base(tenantSlug, projectId)}?resource=blocks`);
  return asArray(data.blocks);
}

export async function fetchPrivateBlock(
  tenantSlug: string,
  projectId: string,
  blockId: string,
): Promise<PrivateManuscriptBlock | null> {
  const data = await read<PrivateManuscriptBlock | null>(
    `${base(tenantSlug, projectId)}?resource=block&blockId=${encodeURIComponent(blockId)}`,
  );
  return data ?? null;
}

export async function fetchBlockVersions(
  tenantSlug: string,
  projectId: string,
  blockId: string,
): Promise<ManuscriptVersion[]> {
  const data = await read<{ versions?: ManuscriptVersion[] | null }>(
    `${base(tenantSlug, projectId)}?resource=versions&blockId=${encodeURIComponent(blockId)}`,
  );
  return asArray(data.versions);
}
