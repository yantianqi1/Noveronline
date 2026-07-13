import type { Metadata } from "next";

import { LandingShell } from "../components/landing-shell";

export const metadata: Metadata = {
  title: "MiroFish-Novel · 长篇小说多智能体创作平台",
  description:
    "把长篇小说变成可检索的世界知识，用图谱、世界线与 Writer Agent 辅助续写与审校。",
};

export default function HomePage() {
  return <LandingShell />;
}
