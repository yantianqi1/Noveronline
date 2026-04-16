/**
 * Worldline layout hook — re-exports the persisted Zustand layout store.
 */

import { useLayoutStore } from "@/stores/layout-store";

export function useWorldlineLayout() {
  return useLayoutStore();
}
