/**
 * Adoption state machine for tool-render cards.
 *
 * Every card has the same three states:
 *   - idle       : the card is showing a draft proposal
 *   - adopting   : an API call is in flight
 *   - adopted    : the call succeeded; card switches to read-only summary
 *   - error      : the call failed; card remains interactive
 *
 * Cards supply an async `onAdopt()` that performs whatever API call the
 * card needs (scene create, block update, chapter create, etc.). The hook
 * wraps the call, dispatches toasts, and swaps the UI state.
 */

import * as React from "react";

import { useNotification } from "@/hooks/use-notification";

export type AdoptState = "idle" | "adopting" | "adopted" | "error";

export interface UseRenderAdoptOptions<T = unknown> {
  /** Required async action. Should throw on failure. */
  action: () => Promise<T>;
  /** Called once the action resolves. */
  onSuccess?: (result: T) => void;
  successMessage?: string;
  errorMessage?: string;
}

export interface UseRenderAdoptReturn {
  state: AdoptState;
  error: string | null;
  /** Invoke the action. Safe to call multiple times; in-flight calls are de-duped. */
  run: () => Promise<void>;
  reset: () => void;
}

export function useRenderAdopt<T = unknown>(
  options: UseRenderAdoptOptions<T>,
): UseRenderAdoptReturn {
  const { action, onSuccess, successMessage, errorMessage } = options;
  const [state, setState] = React.useState<AdoptState>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const inFlight = React.useRef(false);
  const notify = useNotification();

  const run = React.useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState("adopting");
    setError(null);
    try {
      const result = await action();
      setState("adopted");
      if (successMessage) notify.notifySuccess(successMessage);
      onSuccess?.(result);
    } catch (exc) {
      const msg = exc instanceof Error ? exc.message : String(exc);
      setState("error");
      setError(msg);
      notify.notifyError(errorMessage ?? `采纳失败: ${msg}`);
    } finally {
      inFlight.current = false;
    }
  }, [action, onSuccess, successMessage, errorMessage, notify]);

  const reset = React.useCallback(() => {
    setState("idle");
    setError(null);
  }, []);

  return { state, error, run, reset };
}
