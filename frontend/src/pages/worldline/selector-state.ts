/**
 * Selector state helpers: archive selection toggle, project session options.
 *
 * Ported from: src-vue/views/shared/worldlineSelectorState.js
 */

export interface ArchiveItem {
  archive_id: string;
  entity_name?: string;
  [key: string]: unknown;
}

export function toggleArchiveSelection(
  selectedArchives: ArchiveItem[],
  archive: ArchiveItem,
): ArchiveItem[] {
  const index = selectedArchives.findIndex(
    (item) => item.archive_id === archive.archive_id,
  );
  if (index === -1) return [...selectedArchives, archive];
  if (
    serializeArchiveSnapshot(selectedArchives[index]!) !==
    serializeArchiveSnapshot(archive)
  ) {
    const next = [...selectedArchives];
    next[index] = archive;
    return next;
  }
  return selectedArchives.filter(
    (item) => item.archive_id !== archive.archive_id,
  );
}

export function toggleArchiveExpansion(
  expandedArchiveId: string,
  archiveId: string,
): string {
  if (!archiveId) return "";
  return expandedArchiveId === archiveId ? "" : archiveId;
}

export function isArchiveExpanded(
  expandedArchiveId: string,
  archiveId: string,
): boolean {
  return Boolean(archiveId) && expandedArchiveId === archiveId;
}

export function removeArchiveSelection(
  selectedArchives: ArchiveItem[],
  archiveId: string,
): ArchiveItem[] {
  return selectedArchives.filter((item) => item.archive_id !== archiveId);
}

export interface SessionOption {
  value: string;
  label: string;
}

export function buildProjectSessionOptions(
  sessions: Array<{ project_id?: string; session_scope?: string }>,
): SessionOption[] {
  const projectIds = [
    ...new Set(
      sessions.map((item) => item.project_id).filter(Boolean) as string[],
    ),
  ].sort();
  const hasGlobal = sessions.some((item) => item.session_scope === "global");
  const options: SessionOption[] = [{ value: "", label: "全部会话" }];
  for (const projectId of projectIds) {
    options.push({ value: projectId, label: `项目会话 - ${projectId}` });
  }
  if (hasGlobal) {
    options.push({ value: "__global__", label: "全局混合会话" });
  }
  return options;
}

function serializeArchiveSnapshot(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => serializeArchiveSnapshot(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value as object)
      .sort()
      .map(
        (key) =>
          `${key}:${serializeArchiveSnapshot((value as Record<string, unknown>)[key])}`,
      )
      .join(",")}}`;
  }
  return JSON.stringify(value);
}
