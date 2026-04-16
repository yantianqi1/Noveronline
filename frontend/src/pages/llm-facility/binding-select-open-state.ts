const LLM_SETTINGS_POLL_INTERVAL_MS = 2000;

export function nextOpenBindingSelectKey(
  currentKey: string,
  changedKey: string,
  open: boolean,
): string {
  if (open) return changedKey;
  if (currentKey !== changedKey) return currentKey;
  return "";
}

export function getLlmSettingsRefetchInterval(
  openSelectKey: string,
): number | false {
  return openSelectKey ? false : LLM_SETTINGS_POLL_INTERVAL_MS;
}

export { LLM_SETTINGS_POLL_INTERVAL_MS };
