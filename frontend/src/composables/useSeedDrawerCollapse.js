/**
 * 自动折叠状态机：管理抽屉内步骤和章节的展开/折叠。
 *
 * 规则:
 * - 步骤完成 → 800ms 后自动折叠（若未被锁定）
 * - 用户手动展开 → 10s 锁定期内不自动折叠
 * - 父章节在有活动/锁定步骤时保持展开
 * - 章节最后一步完成后 800ms 折叠（若无活动/锁定步骤）
 * - 手动重展开已折叠章节 → manuallyExpanded = true，不走自动折叠
 */
import { reactive } from "vue";

const STEP_AUTO_COLLAPSE_MS = 1000;
const CHAPTER_AUTO_COLLAPSE_MS = 1200;
const STEP_LOCK_DURATION_MS = 10_000;

// 模块级单例：跨组件 mount/unmount 保持折叠状态
const stepStates = reactive(new Map());
const chapterStates = reactive(new Map());
const timers = new Map();

export function useSeedDrawerCollapse() {

  function getStepState(stepId) {
    if (!stepStates.has(stepId)) {
      stepStates.set(stepId, { collapsed: false, lockedUntil: 0 });
    }
    return stepStates.get(stepId);
  }

  function getChapterState(chapterKey) {
    if (!chapterStates.has(chapterKey)) {
      chapterStates.set(chapterKey, { collapsed: false, manuallyExpanded: false });
    }
    return chapterStates.get(chapterKey);
  }

  function isStepCollapsed(stepId) {
    return getStepState(stepId).collapsed;
  }

  function isChapterCollapsed(chapterKey) {
    return getChapterState(chapterKey).collapsed;
  }

  function expandStep(stepId) {
    const s = getStepState(stepId);
    s.collapsed = false;
    s.lockedUntil = Date.now() + STEP_LOCK_DURATION_MS;
    // 清除该步骤待执行的自动折叠
    clearStepTimer(stepId);
  }

  function collapseStep(stepId) {
    const s = getStepState(stepId);
    s.collapsed = true;
    s.lockedUntil = 0;
    clearStepTimer(stepId);
  }

  function expandChapter(chapterKey) {
    const c = getChapterState(chapterKey);
    c.collapsed = false;
    c.manuallyExpanded = true;
  }

  function collapseChapter(chapterKey) {
    const c = getChapterState(chapterKey);
    c.collapsed = true;
    c.manuallyExpanded = false;
  }

  function onStepCompleted(stepId, chapterKey) {
    const s = getStepState(stepId);
    // 如果在锁定期内，不安排自动折叠
    if (Date.now() < s.lockedUntil) return;
    // 安排 800ms 后自动折叠
    scheduleStepCollapse(stepId, chapterKey);
  }

  function scheduleStepCollapse(stepId, chapterKey) {
    clearStepTimer(stepId);
    const timer = setTimeout(() => {
      const s = getStepState(stepId);
      if (Date.now() < s.lockedUntil) return; // 用户在此期间手动展开了
      s.collapsed = true;
      timers.delete(stepId);
      // 检查父章节是否需要折叠
      maybeCollapseChapter(chapterKey);
    }, STEP_AUTO_COLLAPSE_MS);
    timers.set(stepId, timer);
  }

  function maybeCollapseChapter(chapterKey) {
    const c = getChapterState(chapterKey);
    if (c.manuallyExpanded) return; // 用户手动展开的，不自动折叠

    // 检查是否还有活动或锁定步骤
    const now = Date.now();
    for (const [, s] of stepStates) {
      if (!s.collapsed && now < s.lockedUntil) return; // 有锁定步骤
    }

    // 章节折叠延迟比步骤更长，形成视觉序列感
    const timerKey = `ch:${chapterKey}`;
    clearStepTimer(timerKey);
    const timer = setTimeout(() => {
      const cc = getChapterState(chapterKey);
      if (cc.manuallyExpanded) return;
      cc.collapsed = true;
      timers.delete(timerKey);
    }, CHAPTER_AUTO_COLLAPSE_MS);
    timers.set(timerKey, timer);
  }

  function clearStepTimer(key) {
    if (timers.has(key)) {
      clearTimeout(timers.get(key));
      timers.delete(key);
    }
  }

  function reset() {
    for (const key of timers.keys()) {
      clearTimeout(timers.get(key));
    }
    timers.clear();
    stepStates.clear();
    chapterStates.clear();
  }

  return {
    isStepCollapsed,
    isChapterCollapsed,
    expandStep,
    collapseStep,
    expandChapter,
    collapseChapter,
    onStepCompleted,
    reset,
  };
}
