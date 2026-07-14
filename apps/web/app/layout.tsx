import type { Metadata, Viewport } from "next";
import { LocaleProvider } from "../components/locale-provider";
import { currentRequestLocale } from "../lib/request-locale";
import "./auth-marketing.css";
import "./globals.css";
import "./workbench-polish.css";
import "./mobile-chrome.css";

export const metadata: Metadata = {
  title: "MiroFish Novel",
  description: "长篇小说创作工作台 / Long-form fiction workspace.",
};

export const viewport: Viewport = {
  colorScheme: "light",
  initialScale: 1,
  themeColor: "#f3eee4",
  width: "device-width",
  viewportFit: "cover",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await currentRequestLocale();

  return (
    <html data-scroll-behavior="smooth" lang={locale} suppressHydrationWarning>
      <body>
        <LocaleProvider initialLocale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
