/**
 * LLM activity monitor hook — polls GET /api/llm/activity every 2 seconds
 * via TanStack Query. Polling automatically pauses when the component unmounts.
 */

import { useQuery } from "@tanstack/react-query";

import { getLlmActivity } from "@/api/llm";
import type { LlmActiveCall, LlmChannelActivity } from "@/types/llm";

const POLL_INTERVAL_MS = 2000;

export function useLlmActivity() {
  const { data, isLoading } = useQuery({
    queryKey: ["llm-activity"],
    queryFn: async () => {
      const response = await getLlmActivity();
      const raw = response.data as
        | {
            calls?: LlmActiveCall[];
            channels?: Record<string, LlmChannelActivity>;
            total_active?: number;
          }
        | undefined;
      return {
        calls: raw?.calls ?? [],
        channels: raw?.channels ?? {},
        totalActive: raw?.total_active ?? 0,
      };
    },
    refetchInterval: POLL_INTERVAL_MS,
  });

  return {
    calls: data?.calls ?? [],
    channels: data?.channels ?? {},
    totalActive: data?.totalActive ?? 0,
    isLoading,
  } as const;
}
