import type { Locale } from "./locale";
import {
  publicActionFailure,
  publicLoadFailure,
  publicUnavailableTitle,
} from "./presentation";

export type PublicErrorKind = "load" | "action" | "unavailable" | "submit" | "network";

export type PublicErrorView = {
  kind: PublicErrorKind;
  title: string;
  message: string;
  recoveryHint: string;
};

/**
 * Map internal failures to author-safe public errors.
 * Never expose internal codes, stack traces, provider bodies, or UUIDs.
 */
export function mapPublicError(
  locale: Locale,
  kind: PublicErrorKind,
  options?: {
    impact?: string;
    recovery?: string;
  },
): PublicErrorView {
  const isZh = locale === "zh-CN";

  const base: Record<PublicErrorKind, PublicErrorView> = {
    load: {
      kind: "load",
      title: publicUnavailableTitle(locale),
      message: publicLoadFailure(locale),
      recoveryHint: isZh ? "请稍后刷新页面重试。" : "Refresh the page and try again shortly.",
    },
    action: {
      kind: "action",
      title: isZh ? "操作未完成" : "Action incomplete",
      message: publicActionFailure(locale),
      recoveryHint: isZh ? "请检查输入后重试。" : "Check your input and try again.",
    },
    unavailable: {
      kind: "unavailable",
      title: publicUnavailableTitle(locale),
      message: publicLoadFailure(locale),
      recoveryHint: isZh ? "稍后再试，或从侧栏切换到其他模块。" : "Try again later, or switch modules from the sidebar.",
    },
    submit: {
      kind: "submit",
      title: isZh ? "提交未完成" : "Submit incomplete",
      message: isZh
        ? "这次提交没有完成。页面状态已保留，可以再次提交。"
        : "This submission did not finish. Your page state is kept so you can submit again.",
      recoveryHint: isZh ? "确认网络正常后重试。" : "Confirm the network is available, then retry.",
    },
    network: {
      kind: "network",
      title: isZh ? "连接中断" : "Connection interrupted",
      message: isZh
        ? "暂时无法联系创作服务。当前页面内容仍然可用。"
        : "The creative service is temporarily unreachable. Content already on the page remains available.",
      recoveryHint: isZh ? "检查网络后刷新或重试。" : "Check your network, then refresh or retry.",
    },
  };

  const view = base[kind];
  return {
    ...view,
    message: options?.impact?.trim() || view.message,
    recoveryHint: options?.recovery?.trim() || view.recoveryHint,
  };
}

/** Strip internal codes from accidental user-facing strings. */
export function sanitizeAuthorErrorMessage(message: string): string {
  return message
    .replace(/\b[A-Z][A-Z0-9_]{5,}\b/g, "")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}
