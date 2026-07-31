import type { Metadata } from "next";

import { RecoveryResetForm } from "../recovery-form";

export const metadata: Metadata = {
  title: "重置密码 · MiroFish Novel",
};

type SearchParams = Promise<{ token?: string | string[] }>;

export default async function RecoveryResetPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const token = typeof params.token === "string" ? params.token : params.token?.[0] ?? "";
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-5 py-12">
      <section className="w-full max-w-[440px] rounded-modal border border-line bg-panel p-7 shadow-panel sm:p-9">
        <header className="mb-8">
          <p className="mb-2 text-caption font-medium tracking-label text-muted">账户恢复</p>
          <h1 className="font-brush text-display leading-snug text-ink">设置新密码</h1>
          <p className="mt-2 text-base leading-relaxed text-muted">完成后即可用新密码回到工作台。</p>
        </header>
        <RecoveryResetForm token={token} />
      </section>
    </main>
  );
}
