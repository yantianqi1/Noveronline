/**
 * The Writer prompt catalog is intentionally code-owned for now, but every
 * system prompt has a stable key/version. The version is included in the
 * prompt snapshot so traces can be compared and a later registry migration
 * can roll back a prompt without guessing which text a run used.
 */
export const WRITER_PROMPT_VERSIONS = Object.freeze({
  retrieval_planner: "1",
  rerank: "1",
  consistency: "1",
  orchestrator: "2",
  composer: "2",
} as const);

export type WriterPromptKey = keyof typeof WRITER_PROMPT_VERSIONS;

export function versionWriterPrompt(key: WriterPromptKey, prompt: string): string {
  const version = WRITER_PROMPT_VERSIONS[key];
  return `${prompt}\n\nPrompt contract: ${key}@${version}`;
}
