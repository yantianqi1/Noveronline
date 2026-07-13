import { tx, type Locale } from "./locale";

export type ManuscriptCommandKey =
  | "complete_outline"
  | "align_words"
  | "scan_lexicon"
  | "fill_relationships"
  | "continue_chapter";

export const MANUSCRIPT_COMMAND_CHOICES = [
  { choice: "complete-outline", key: "complete_outline" as const, zh: "补全大纲", en: "Complete outline" },
  { choice: "align-words", key: "align_words" as const, zh: "字数对齐", en: "Check word count" },
  { choice: "scan-lexicon", key: "scan_lexicon" as const, zh: "扫描禁用词", en: "Scan forbidden terms" },
  { choice: "fill-relationships", key: "fill_relationships" as const, zh: "补全关系", en: "Fill relationships" },
  { choice: "continue-chapter", key: "continue_chapter" as const, zh: "续写章节", en: "Continue chapter" },
] as const;

export function manuscriptCommandKeyFromChoice(choice: string): ManuscriptCommandKey {
  const match = MANUSCRIPT_COMMAND_CHOICES.find((item) => item.choice === choice);
  return match?.key ?? "complete_outline";
}

export function manuscriptCommandLabel(key: string, locale: Locale): string {
  const match = MANUSCRIPT_COMMAND_CHOICES.find((item) => item.key === key);
  return match ? tx(locale, match.zh, match.en) : key.replaceAll("_", " ");
}

const PLANNING_RUN_LABELS: Record<string, { zh: string; en: string }> = {
  writer_book_plan_generation: { zh: "书籍计划生成", en: "Book plan generation" },
  writer_dedup_extraction: { zh: "去重候选提取", en: "Dedup extraction" },
};

export function planningRunLabel(workflowType: string, locale: Locale): string {
  const match = PLANNING_RUN_LABELS[workflowType];
  return match ? tx(locale, match.zh, match.en) : tx(locale, "后台任务", "Background task");
}