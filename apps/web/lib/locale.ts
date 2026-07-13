export const LOCALE_COOKIE_NAME = "mirofish_locale";

export type Locale = "zh-CN" | "en";

export function parseLocale(value: string | null | undefined): Locale {
  if (!value) {
    return "zh-CN";
  }

  let decoded = value.trim();
  try {
    decoded = decodeURIComponent(decoded).trim();
  } catch {
    // Keep the raw value when it is not URI-encoded.
  }

  const normalized = decoded.toLowerCase();
  if (normalized === "en" || normalized === "en-us" || normalized.startsWith("en-")) {
    return "en";
  }
  if (
    normalized === "zh" ||
    normalized === "zh-cn" ||
    normalized === "zh-hans" ||
    normalized.startsWith("zh")
  ) {
    return "zh-CN";
  }

  // Unknown values fall back to Chinese so a bad cookie cannot lock users in English.
  return "zh-CN";
}

export function tx(locale: Locale, zh: string, en: string) {
  return locale === "en" ? en : zh;
}
