import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import "@/components/landing/landing.css";

import LandingNav from "@/components/landing/nav";
import { CapabilitiesSection } from "@/components/landing/sections/capabilities";
import { FinaleSection } from "@/components/landing/sections/finale";
import { HeroSection } from "@/components/landing/sections/hero";
import { ManifestoSection } from "@/components/landing/sections/manifesto";
import { PipelineSection } from "@/components/landing/sections/pipeline";
import { PricingSection } from "@/components/landing/sections/pricing";
import { WorldlineSection } from "@/components/landing/sections/worldline";
import { WriterSection } from "@/components/landing/sections/writer";

export const metadata: Metadata = {
  title: "MiroFish Novel — 长篇小说创作引擎",
  description:
    "上传手稿与设定，MiroFish 读出角色、关系、伏笔与世界规则，在唯一的世界线里推演剧情，再陪你把每一章写成。",
};

export default async function HomePage() {
  // Signed-in users belong in the workspace, not the marketing page: a present
  // session cookie means they've already authenticated, so send them straight
  // to their shelf instead of re-showing the landing hero.
  const session = (await cookies()).get("mirofish_session");
  if (session?.value) {
    redirect("/workspace");
  }

  return (
    <div className="landing" id="top">
      <LandingNav />
      <main>
        <HeroSection />
        <ManifestoSection />
        <PipelineSection />
        <CapabilitiesSection />
        <WriterSection />
        <WorldlineSection />
        <PricingSection />
        <FinaleSection />
      </main>
    </div>
  );
}
