import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MiroFish Novel",
  description: "SaaS writing control plane for long-form fiction projects.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
