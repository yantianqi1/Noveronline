import { cookies } from "next/headers";

import type { ApiContext } from "./api";

export async function webApiContext<T extends { tenantId: string }>(input: T): Promise<T & ApiContext> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  const actorUserId = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();

  return {
    ...input,
    actorUserId: sessionCookie ? undefined : actorUserId,
    sessionCookie,
  };
}
