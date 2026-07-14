import type { Locale } from "./locale";

const BEIJING_TIME_ZONE = "Asia/Shanghai";

/**
 * Format API timestamps for overview/task surfaces in Beijing time (UTC+8).
 * Accepts ISO strings or Postgres-style `2026-07-14 04:56:36.19514+00`.
 */
export function formatBeijingTime(locale: Locale, value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = parseApiTimestamp(value);
  if (!date) {
    return value;
  }
  const tag = locale === "zh-CN" ? "zh-CN" : "en-US";
  return new Intl.DateTimeFormat(tag, {
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(date)
    .replace(/\//g, "-");
}

/** Compact display with optional Beijing label for zh. */
export function formatBeijingTimeLabel(locale: Locale, value: string | null | undefined): string {
  const formatted = formatBeijingTime(locale, value);
  if (!formatted) {
    return "";
  }
  if (locale === "zh-CN") {
    return `${formatted}（北京时间）`;
  }
  return `${formatted} (Beijing)`;
}

function parseApiTimestamp(value: string): Date | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  // Postgres often returns "2026-07-14 04:56:36.19514+00" — normalize for Date.
  const normalized = trimmed
    .replace(" ", "T")
    .replace(/\+(\d{2})$/, "+$1:00")
    .replace(/\.(\d{3})\d+/, ".$1");
  const date = new Date(normalized);
  if (!Number.isNaN(date.getTime())) {
    return date;
  }
  const fallback = new Date(trimmed);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}
