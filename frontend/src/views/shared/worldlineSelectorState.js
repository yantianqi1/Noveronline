export function toggleArchiveSelection(selectedArchives, archive) {
  const index = selectedArchives.findIndex((item) => item.archive_id === archive.archive_id);
  if (index === -1) {
    return [...selectedArchives, archive];
  }
  if (serializeArchiveSnapshot(selectedArchives[index]) !== serializeArchiveSnapshot(archive)) {
    const next = [...selectedArchives];
    next[index] = archive;
    return next;
  }
  return selectedArchives.filter((item) => item.archive_id !== archive.archive_id);
}

export function toggleArchiveExpansion(expandedArchiveId, archiveId) {
  if (!archiveId) {
    return "";
  }
  return expandedArchiveId === archiveId ? "" : archiveId;
}

export function isArchiveExpanded(expandedArchiveId, archiveId) {
  return Boolean(archiveId) && expandedArchiveId === archiveId;
}

export function removeArchiveSelection(selectedArchives, archiveId) {
  return selectedArchives.filter((item) => item.archive_id !== archiveId);
}

export function buildProjectSessionOptions(sessions) {
  const projectIds = [...new Set(sessions.map((item) => item.project_id).filter(Boolean))].sort();
  const hasGlobal = sessions.some((item) => item.session_scope === "global");
  const options = [{ value: "", label: "全部会话" }];
  for (const projectId of projectIds) {
    options.push({ value: projectId, label: `项目会话 · ${projectId}` });
  }
  if (hasGlobal) {
    options.push({ value: "__global__", label: "全局混合会话" });
  }
  return options;
}

function serializeArchiveSnapshot(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => serializeArchiveSnapshot(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${key}:${serializeArchiveSnapshot(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
