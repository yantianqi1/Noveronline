"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { LogOut, ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { logout } from "@/lib/api/session";
import { avatarInitial } from "@/lib/workspace";
import { DUR, EASE } from "@/lib/motion";
import type { CurrentUser } from "@/lib/api/types";

/** Account disclosure with keyboard entry, dismissal, and visible error recovery. */
export function UserMenu({ currentUser }: { currentUser: CurrentUser }) {
  const router = useRouter();
  const menuId = useId();
  const reduceMotion = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const actionRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    actionRef.current?.focus();
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  async function handleSignOut() {
    if (signingOut) return;
    // Disabling the focused menu item would blur and dismiss the error surface.
    triggerRef.current?.focus();
    setSigningOut(true);
    setError(null);
    try {
      await logout();
      router.push("/login");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "退出登录失败，请重试。");
      setSigningOut(false);
    }
  }

  return (
    <div ref={rootRef} className="relative shrink-0"
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          triggerRef.current?.focus();
        } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          setOpen(true);
          actionRef.current?.focus();
        }
      }}>
      <button ref={triggerRef} type="button" onClick={() => setOpen((value) => !value)}
        aria-label="账户菜单" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
        className="flex min-h-11 items-center gap-2 rounded-control px-2 text-ink transition-colors hover:bg-paper-deep">
        <span className="grid size-8 place-items-center rounded-full bg-paper-deep font-serif text-md font-semibold" aria-hidden>
          {avatarInitial(currentUser)}
        </span>
        <span className="hidden max-w-[160px] truncate text-sm font-medium sm:block">
          {currentUser.user.display_name || currentUser.user.email}
        </span>
        <ChevronDown className={`size-4 text-muted transition-transform duration-160 ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      <AnimatePresence>
        {open ? (
          <motion.div initial={reduceMotion ? false : { opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0 }} transition={{ duration: DUR.fast, ease: EASE }}
            className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(288px,calc(100vw-32px))] rounded-panel border border-line bg-panel shadow-panel">
            <div className="border-b border-line-soft px-4 py-4">
              <p className="break-words text-base font-medium text-ink">{currentUser.user.display_name || "未命名用户"}</p>
              <p className="mt-1 break-all text-caption text-muted">{currentUser.user.email}</p>
            </div>
            <div id={menuId} role="menu" aria-label="账户操作" className="p-1.5">
              <button ref={actionRef} type="button" role="menuitem" onClick={handleSignOut}
                disabled={signingOut} aria-busy={signingOut || undefined}
                className="flex min-h-11 w-full items-center gap-2.5 rounded-control px-3 text-left text-base text-ink transition-colors hover:bg-paper-deep disabled:opacity-55">
                <LogOut className="size-4" aria-hidden />{signingOut ? "正在退出…" : "退出登录"}
              </button>
            </div>
            {error ? <p role="alert" className="px-4 pb-4 text-sm text-danger">{error}</p> : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
