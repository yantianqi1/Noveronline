import { Feather } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { CoverMasthead } from "./cover-masthead";
import { LoginForm } from "./login-form";

export const metadata: Metadata = {
  title: "登录 · MiroFish Novel",
};

/**
 * Editorial split-screen sign-in.
 * Left: a full-bleed vermilion plate with vertical calligraphy and a seal —
 *       the "cover" of the product.
 * Right: a floating paper card holding the form — the "page" you write on.
 * The form logic lives in LoginForm (unchanged); this file is pure chrome.
 */
export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen bg-paper">
      {/* ── Vermilion cover (left plate) ─────────────────────────────── */}
      <aside
        aria-hidden
        className="relative hidden w-[46%] overflow-hidden bg-accent lg:flex lg:flex-col lg:justify-between"
      >
        {/* paper-grain + brush texture */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.16] mix-blend-overlay"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")",
          }}
        />
        {/* deep vignette to seat the color */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(120% 90% at 20% 0%, rgba(255,255,255,0.14), transparent 45%), radial-gradient(120% 120% at 90% 100%, rgba(60,8,6,0.55), transparent 55%)",
          }}
        />
        {/* faint oversized seal ring */}
        <div className="pointer-events-none absolute -bottom-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/12" />
        <div className="pointer-events-none absolute -bottom-24 -left-24 h-[360px] w-[360px] rounded-full border border-white/10" />

        {/* animated brand row + vertical masthead + colophon */}
        <CoverMasthead />
      </aside>

      {/* ── Paper page (right form column) ───────────────────────────── */}
      <section className="relative flex min-h-screen flex-1 items-center justify-center overflow-hidden px-5 py-12 sm:px-10">
        {/* soft paper wash on the right too */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(900px 500px at 90% -5%, rgba(143,33,27,0.05), transparent 60%), radial-gradient(700px 500px at 0% 105%, rgba(181,133,74,0.08), transparent 55%)",
          }}
        />

        <div className="relative w-full max-w-[400px] animate-fade-up">
          {/* compact brand for small screens (cover hidden) */}
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="grid size-11 place-items-center rounded-modal bg-accent text-panel shadow-accent">
              <Feather className="size-5" aria-hidden />
            </span>
            <div>
              <p className="font-brush text-xl leading-tight tracking-wide text-ink">
                墨鱼小说
              </p>
              <p className="text-caption tracking-label text-muted">长篇小说工作台</p>
            </div>
          </div>

          {/* floating paper card */}
          <div className="rounded-modal border border-line bg-panel p-7 shadow-panel sm:p-9">
            <header className="mb-8">
              <p className="mb-2 text-caption font-medium tracking-label text-muted">
                登录
              </p>
              <h2 className="font-brush text-display leading-snug text-ink">
                欢迎回来
              </h2>
              <p className="mt-2 text-base leading-relaxed text-muted">
                继续你的写作与故事世界。
              </p>
            </header>

            <Suspense fallback={<div className="min-h-[248px]" aria-hidden />}>
              <LoginForm />
            </Suspense>

            <div className="mt-7 flex items-center gap-3 text-caption text-muted">
              <span className="h-px flex-1 bg-line-soft" />
              <span>还没有账号？</span>
              <span className="h-px flex-1 bg-line-soft" />
            </div>
            <p className="mt-3 text-center text-sm text-muted">
              请联系你的工作区管理员开通，或使用邀请链接加入。
            </p>
          </div>

          <footer className="mt-7 flex items-center justify-center gap-2 text-caption text-muted">
            <span>为长篇小说创作者而设的工作台</span>
          </footer>
        </div>
      </section>
    </main>
  );
}
