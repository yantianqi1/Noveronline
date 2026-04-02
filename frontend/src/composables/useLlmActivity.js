/**
 * 全局 LLM 活动监控 composable（单例模式）。
 *
 * 以 2 秒间隔轮询 GET /api/llm/activity，维护 reactive 状态供
 * LlmActivityIndicator 组件消费。
 */

import { reactive, readonly } from "vue";
import { getLlmActivity } from "../api/llm.js";

const POLL_INTERVAL_MS = 2000;

const state = reactive({
  calls: [],
  channels: {},
  totalActive: 0,
  error: null,
  lastUpdated: null,
});

let _pollTimer = null;
let _refCount = 0;

function _applySnapshot(data) {
  state.calls = data.calls ?? [];
  state.channels = data.channels ?? {};
  state.totalActive = data.total_active ?? 0;
  state.lastUpdated = Date.now();
  state.error = null;
}

async function _fetchOnce() {
  try {
    const response = await getLlmActivity();
    _applySnapshot(response.data);
  } catch {
    // 后台监控不应破坏 UI —— 静默保留旧数据
    state.error = "poll_failed";
  }
}

function _startPolling() {
  if (_pollTimer) return;
  _fetchOnce();
  _pollTimer = setInterval(_fetchOnce, POLL_INTERVAL_MS);
}

function _stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

export function useLlmActivity() {
  return {
    state: readonly(state),
    mount() {
      _refCount++;
      if (_refCount === 1) _startPolling();
    },
    unmount() {
      _refCount = Math.max(0, _refCount - 1);
      if (_refCount === 0) _stopPolling();
    },
  };
}
