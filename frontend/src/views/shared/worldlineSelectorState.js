export function toggleArchiveSelection(selectedArchives, archive) {
  const index = selectedArchives.findIndex((item) => item.archive_id === archive.archive_id);
  if (index === -1) {
    return [...selectedArchives, archive];
  }
  if (selectedArchives[index].entity_name !== archive.entity_name) {
    const next = [...selectedArchives];
    next[index] = archive;
    return next;
  }
  return selectedArchives.filter((item) => item.archive_id !== archive.archive_id);
}

export function removeArchiveSelection(selectedArchives, archiveId) {
  return selectedArchives.filter((item) => item.archive_id !== archiveId);
}

export function resolveSelectedBranchId(branches, currentBranchId) {
  if (!branches.length) {
    return "";
  }
  return branches.some((item) => item.branch_id === currentBranchId)
    ? currentBranchId
    : branches[0].branch_id;
}

export function toggleCheckedBranchId(checkedBranchIds, branchId) {
  if (!branchId) {
    return [...checkedBranchIds];
  }
  return checkedBranchIds.includes(branchId)
    ? checkedBranchIds.filter((item) => item !== branchId)
    : [...checkedBranchIds, branchId];
}

export function sanitizeCheckedBranchIds(branches, checkedBranchIds) {
  const checkedIdSet = new Set(checkedBranchIds.filter(Boolean));
  return branches
    .map((item) => item.branch_id)
    .filter((branchId) => checkedIdSet.has(branchId));
}

export function buildComparisonBranchIds(checkedBranchIds, currentBranchId) {
  const uniqueCheckedIds = [...new Set(checkedBranchIds.filter(Boolean))];
  if (uniqueCheckedIds.length) {
    return uniqueCheckedIds;
  }
  return currentBranchId ? [currentBranchId] : [];
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
