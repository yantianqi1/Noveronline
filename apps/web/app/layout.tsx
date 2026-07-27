import type { Metadata } from "next";
import { Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

/**
 * Self-hosted Chinese type families.
 *
 * Every user of this product writes and reads Chinese, so the two families that
 * carry the interface are loaded rather than left to whatever the OS happens to
 * ship. `preload: false` is required for CJK: Google slices these faces into
 * unicode-range chunks, so the browser fetches only the blocks a page actually
 * uses — preloading all of them would download megabytes nobody reads.
 *
 * Noto Sans SC's Latin is drawn from Source Sans and Noto Serif SC's from
 * Source Serif, so digits and Latin stay in the same design family as the
 * hanzi instead of clashing the way a Western face paired with PingFang does.
 * System faces remain as fallback so first paint is never blocked.
 */
const sans = Noto_Sans_SC({
  weight: ["400", "500", "700"],
  preload: false,
  display: "swap",
  variable: "--font-cn-sans",
  fallback: ["PingFang SC", "Microsoft YaHei", "system-ui", "sans-serif"],
});

const serif = Noto_Serif_SC({
  weight: ["400", "600"],
  preload: false,
  display: "swap",
  variable: "--font-cn-serif",
  fallback: ["Songti SC", "SimSun", "Georgia", "serif"],
});

export const metadata: Metadata = {
  title: "MiroFish Novel",
  description: "长篇小说创作工作台",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" className={`${sans.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
