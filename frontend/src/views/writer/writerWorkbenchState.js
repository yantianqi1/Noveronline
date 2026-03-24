export function deriveWriterDefaults(options = {}) {
  const firstChapter = options.chapters?.[0] || {};
  return {
    chapterOrder: firstChapter.order || 0,
    chapterId: firstChapter.chapter_id || "",
    povCharacter: options.pov_characters?.[0] || "",
  };
}

export function buildWriterRequestPayload(form = {}) {
  const payload = {
    scope_type: form.scopeType,
    project_id: form.projectId,
    pov_character: form.povCharacter,
    writing_goal: form.writingGoal,
    scene_focus: form.sceneFocus,
    include_candidates: Boolean(form.includeCandidates),
  };
  if (form.scopeType === "worldline_branch") {
    payload.session_id = form.sessionId;
    payload.branch_id = form.branchId || "main";
    return payload;
  }
  if (form.chapterId) {
    payload.chapter_id = form.chapterId;
  }
  if (form.chapterOrder) {
    payload.chapter_order = Number(form.chapterOrder);
  }
  return payload;
}

export function resolveWriterPovOptions(scopeType, projectPovs = [], worldlineAgents = []) {
  if (scopeType === "worldline_branch" && worldlineAgents.length) {
    return [...new Set(
      worldlineAgents
        .filter((item) => item.agent_kind !== "relationship")
        .map((item) => item.display_name)
        .filter(Boolean),
    )];
  }
  return [...new Set(projectPovs.filter(Boolean))];
}

export function findContextItem(pack, selectedItem) {
  if (!pack || !selectedItem?.item_id) {
    return null;
  }
  const items = [
    ...(pack.must_know || []),
    ...(pack.should_know || []),
    ...(pack.warnings || []),
  ];
  return items.find((item) => item.item_id === selectedItem.item_id) || null;
}
