/**
 * Keyboard shortcut provider for the writer workbench.
 *
 * Self-built over document.addEventListener("keydown") — no third-party
 * dep (react-hotkeys-hook is not pulled in for ~4 keys). Subscribers
 * register via useWriterShortcuts(); the provider dedupes and scopes
 * handlers to this subtree so shortcuts don't leak globally.
 */

import * as React from "react";

export type ShortcutKey =
  | "mod+b"
  | "mod+m"
  | "mod+l"
  | "mod+k"
  | "mod+shift+l";
export type ShortcutHandler = (e: KeyboardEvent) => void;

export interface ShortcutRegistration {
  key: ShortcutKey;
  handler: ShortcutHandler;
  enabled?: boolean;
}

interface ShortcutContextValue {
  register: (reg: ShortcutRegistration) => () => void;
}

const ShortcutContext = React.createContext<ShortcutContextValue | null>(null);

function keyMatches(event: KeyboardEvent, key: ShortcutKey): boolean {
  const parts = key.toLowerCase().split("+");
  const needsMod = parts.includes("mod");
  const needsShift = parts.includes("shift");
  const needsAlt = parts.includes("alt");
  const target = parts[parts.length - 1];

  const modOk = needsMod ? event.metaKey || event.ctrlKey : !event.metaKey && !event.ctrlKey;
  const shiftOk = needsShift ? event.shiftKey : !event.shiftKey;
  const altOk = needsAlt ? event.altKey : !event.altKey;
  const keyOk = event.key.toLowerCase() === target;

  return modOk && shiftOk && altOk && keyOk;
}

export interface KeyboardShortcutProviderProps {
  children: React.ReactNode;
}

export function KeyboardShortcutProvider({ children }: KeyboardShortcutProviderProps) {
  const registrationsRef = React.useRef<Set<ShortcutRegistration>>(new Set());

  const register = React.useCallback((reg: ShortcutRegistration) => {
    registrationsRef.current.add(reg);
    return () => {
      registrationsRef.current.delete(reg);
    };
  }, []);

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      // Ignore shortcuts when typing in inputs/textareas/contentEditable.
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      const editable =
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        target?.isContentEditable;
      // Still allow mod-based shortcuts while editing so ⌘B doesn't lock up.
      const modOnly = event.metaKey || event.ctrlKey;
      if (editable && !modOnly) return;

      for (const reg of registrationsRef.current) {
        if (reg.enabled === false) continue;
        if (keyMatches(event, reg.key)) {
          event.preventDefault();
          reg.handler(event);
          break;
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <ShortcutContext.Provider value={{ register }}>
      {children}
    </ShortcutContext.Provider>
  );
}

export function useWriterShortcuts(registrations: ShortcutRegistration[]): void {
  const ctx = React.useContext(ShortcutContext);
  React.useEffect(() => {
    if (!ctx) return;
    const offs = registrations.map((r) => ctx.register(r));
    return () => {
      for (const off of offs) off();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx, JSON.stringify(registrations.map((r) => ({ k: r.key, e: r.enabled })))]);
}
