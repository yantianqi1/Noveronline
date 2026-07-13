"use client";

import { Globe2 } from "lucide-react";
import { useLocale } from "./locale-provider";

export function LanguageSwitcher() {
  const { locale, selectLocale, switching } = useLocale();
  const nextLocale = locale === "en" ? "zh-CN" : "en";
  const label = locale === "en" ? "切换为中文" : "Switch to English";

  return (
    <button
      aria-busy={switching}
      aria-label={label}
      className="language-switcher"
      data-locale={locale}
      data-switching={switching ? "true" : "false"}
      onClick={() => selectLocale(nextLocale)}
      title={label}
      type="button"
    >
      <Globe2 aria-hidden="true" size={19} strokeWidth={1.8} />
    </button>
  );
}
