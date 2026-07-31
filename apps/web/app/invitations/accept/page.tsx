import type { Metadata } from "next";

import { InvitationAcceptForm } from "./invitation-accept-form";

export const metadata: Metadata = {
  title: "接受邀请 · MiroFish Novel",
};

type SearchParams = Promise<{ token?: string | string[] }>;

export default async function InvitationAcceptPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const token = typeof params.token === "string" ? params.token : params.token?.[0] ?? "";
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-5 py-12">
      <section className="w-full max-w-[440px] rounded-modal border border-line bg-panel p-7 shadow-panel sm:p-9">
        <header className="mb-8">
          <p className="mb-2 text-caption font-medium tracking-label text-muted">工作区邀请</p>
          <h1 className="font-brush text-display leading-snug text-ink">加入创作空间</h1>
          <p className="mt-2 text-base leading-relaxed text-muted">登录后即可接受邀请并进入对应工作区。</p>
        </header>
        <InvitationAcceptForm token={token} />
      </section>
    </main>
  );
}
