import type { Metadata } from "next";

import { RecoveryRequestForm } from "./recovery-form";

export const metadata: Metadata = {
  title: "找回密码 · MiroFish Novel",
};

export default function RecoveryPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-5 py-12">
      <section className="w-full max-w-[440px] rounded-modal border border-line bg-panel p-7 shadow-panel sm:p-9">
        <header className="mb-8">
          <p className="mb-2 text-caption font-medium tracking-label text-muted">账户恢复</p>
          <h1 className="font-brush text-display leading-snug text-ink">找回密码</h1>
          <p className="mt-2 text-base leading-relaxed text-muted">
            输入你的登录邮箱，我们会发送安全的重置链接。
          </p>
        </header>
        <RecoveryRequestForm />
      </section>
    </main>
  );
}
