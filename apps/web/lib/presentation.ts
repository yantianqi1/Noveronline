import type { Locale } from "./locale";

export function publicLoadFailure(locale: Locale) {
  return locale === "zh-CN"
    ? "暂时无法加载这部分内容。请稍后重试。"
    : "This content is temporarily unavailable. Try again shortly.";
}

export function publicActionFailure(locale: Locale) {
  return locale === "zh-CN"
    ? "操作未完成。请检查输入后重试。"
    : "The action was not completed. Check the input and try again.";
}

export function publicUnavailableTitle(locale: Locale) {
  return locale === "zh-CN" ? "内容暂不可用" : "Content unavailable";
}
