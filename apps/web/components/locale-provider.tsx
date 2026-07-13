"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useTransition,
} from "react";

import { LOCALE_COOKIE_NAME, parseLocale, type Locale } from "../lib/locale";

type LocaleContextValue = {
  locale: Locale;
  selectLocale: (locale: Locale) => void;
  switching: boolean;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function writeLocaleCookie(locale: Locale) {
  const secure =
    typeof window !== "undefined" && window.location.protocol === "https:" ? "; Secure" : "";
  // Cookie value is plain ASCII (en / zh-CN). Keep Path=/ so every route sees it.
  document.cookie = `${LOCALE_COOKIE_NAME}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}

export function LocaleProvider({
  children,
  initialLocale,
}: {
  children: React.ReactNode;
  initialLocale: Locale;
}) {
  const router = useRouter();
  const [locale, setLocale] = useState(initialLocale);
  const [switching, startTransition] = useTransition();
  // Tracks the locale the user last chose so a stale router.refresh() cannot
  // overwrite a newer selection (e.g. en → zh-CN while an earlier en refresh lands).
  const desiredLocaleRef = useRef<Locale>(initialLocale);

  useEffect(() => {
    if (initialLocale !== desiredLocaleRef.current) {
      return;
    }
    setLocale(initialLocale);
    document.documentElement.lang = initialLocale;
  }, [initialLocale]);

  const selectLocale = useCallback(
    (nextLocale: Locale) => {
      const normalized = parseLocale(nextLocale);
      if (normalized === desiredLocaleRef.current && normalized === locale) {
        return;
      }

      desiredLocaleRef.current = normalized;
      document.documentElement.lang = normalized;
      writeLocaleCookie(normalized);
      setLocale(normalized);
      startTransition(() => {
        router.refresh();
      });
    },
    [locale, router],
  );

  return (
    <LocaleContext.Provider value={{ locale, selectLocale, switching }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return context;
}
