"use client";

import { AnimatePresence, motion } from "motion/react";
import { LogOut, ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { logout } from "@/lib/api/session";
import { avatarInitial, roleLabel } from "@/lib/workspace";
import type { CurrentUser } from "@/lib/api/types";

/**
 * Top-bar user menu: avatar monogram + name, opening a small paper dropdown
 * with the account email and a sign-out action. Sign-out goes through the BFF
 * (CSRF + DELETE /v1/auth/session), then routes back to /login.
 */
export function UserMenu({ currentUser }: { currentUser: CurrentUser }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await logout();
    } catch {
      // Even if the upstream call fails, send the user back to login — the
      // cookie will be re-validated there. We never leave a half-state.
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  const primaryRole = currentUser.active_tenants[0]?.role ?? "viewer";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2.5 rounded-full border border-line bg-panel py-1.5 pl-1.5 pr-3 shadow-hairline transition-colors hover:border-accent/50 hover:bg-accent-wash"
      >
        <span className="grid size-8 place-items-center rounded-full bg-accent font-serif text-md font-semibold text-panel">
          {avatarInitial(currentUser)}
        </span>
        <span className="max-w-[140px] truncate text-sm font-medium text-ink">
          {currentUser.user.display_name || currentUser.user.email}
        </span>
        <ChevronDown
          className={`size-4 text-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 top-[calc(100%+8px)] z-40 w-[240px] origin-top-right overflow-hidden rounded-modal border border-line bg-panel shadow-panel"
          >
            <div className="border-b border-line-soft px-4 py-3.5">
              <p className="truncate text-sm font-medium text-ink">
                {currentUser.user.display_name || "未命名用户"}
              </p>
              <p className="mt-0.5 truncate text-caption text-muted">{currentUser.user.email}</p>
              <span className="mt-2 inline-flex items-center rounded-full bg-accent-wash px-2 py-0.5 text-caption font-medium text-accent-strong">
                {roleLabel(primaryRole)}
              </span>
            </div>
            <div className="p-1.5">
              <button
                type="button"
                role="menuitem"
                onClick={handleSignOut}
                disabled={signingOut}
                className="flex w-full items-center gap-2.5 rounded-panel px-3 py-2 text-left text-sm text-ink transition-colors hover:bg-accent-wash hover:text-accent-strong disabled:opacity-60"
              >
                <LogOut className="size-4" aria-hidden />
                {signingOut ? "正在退出…" : "退出登录"}
              </button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
