"use client";

import { useEffect, useRef, type ReactNode, type RefObject } from "react";

import { cn } from "@/lib/utils";

type ModalProps = {
  label: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
  dismissible?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
};

/** Native modal isolation, scroll locking, and focus restoration for short tasks. */
export function Modal({
  label, children, onClose, className, dismissible = true, initialFocusRef,
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const opener = document.activeElement;
    const overflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    initialFocusRef?.current?.focus();
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus({ preventScroll: true });
      }
    };
  }, [initialFocusRef]);

  return (
    <dialog
      ref={dialogRef}
      aria-label={label}
      className={cn(
        "m-auto max-h-[calc(100dvh-32px)] max-w-[calc(100vw-32px)] overflow-y-auto overscroll-contain rounded-modal border border-line bg-panel p-0 text-ink shadow-panel backdrop:bg-ink/45",
        className,
      )}
      onCancel={(event) => {
        event.preventDefault();
        if (dismissible) onClose();
      }}
      onClick={(event) => {
        if (event.target !== event.currentTarget || !dismissible) return;
        const rect = event.currentTarget.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right ||
            event.clientY < rect.top || event.clientY > rect.bottom) onClose();
      }}
    >
      {children}
    </dialog>
  );
}
