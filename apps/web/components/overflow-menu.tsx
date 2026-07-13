"use client";

import { MoreHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export type OverflowMenuItem = {
  disabled?: boolean;
  href?: string;
  id: string;
  label: ReactNode;
  onSelect?: () => void;
};

type OverflowMenuProps = {
  items: OverflowMenuItem[];
  label: string;
};

/**
 * Secondary actions menu so each screen can keep a single primary action.
 */
export function OverflowMenu({ items, label }: OverflowMenuProps) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="overflow-menu" ref={rootRef}>
      <button
        aria-controls={menuId}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={label}
        className="overflow-menu-trigger"
        onClick={() => setOpen((value) => !value)}
        ref={triggerRef}
        type="button"
      >
        <MoreHorizontal aria-hidden="true" size={18} strokeWidth={1.8} />
      </button>
      {open ? (
        <ul className="overflow-menu-list" id={menuId} role="menu">
          {items.map((item) => (
            <li key={item.id} role="none">
              {item.href ? (
                <a
                  aria-disabled={item.disabled || undefined}
                  className="overflow-menu-item"
                  href={item.disabled ? undefined : item.href}
                  onClick={() => {
                    if (!item.disabled) {
                      setOpen(false);
                    }
                  }}
                  role="menuitem"
                >
                  {item.label}
                </a>
              ) : (
                <button
                  className="overflow-menu-item"
                  disabled={item.disabled}
                  onClick={() => {
                    item.onSelect?.();
                    setOpen(false);
                    triggerRef.current?.focus();
                  }}
                  role="menuitem"
                  type="button"
                >
                  {item.label}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
