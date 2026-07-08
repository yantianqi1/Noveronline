import { cookies } from "next/headers";

import { getSessionCSRFToken, type ApiContext } from "./api";

export async function webApiContext<T extends { tenantId: string }>(input: T): Promise<T & ApiContext> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  const actorUserId = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();
  const csrfResult = sessionCookie ? await getSessionCSRFToken({ sessionCookie }) : undefined;

  return {
    ...input,
    actorUserId: sessionCookie ? undefined : actorUserId,
    sessionCookie,
    csrfToken: csrfResult?.ok ? csrfResult.csrf_token : undefined,
  };
}
