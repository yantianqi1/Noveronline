import { getSessionCSRFToken, type ApiContext } from "./api";
import { currentRequestSessionCookie } from "./request-session";

export async function webApiContext<T extends { tenantId: string }>(input: T): Promise<T & ApiContext> {
  const sessionCookie = currentRequestSessionCookie({ required: true });
  const actorUserId = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();
  const csrfResult = sessionCookie ? await getSessionCSRFToken({ sessionCookie }) : undefined;
  if (sessionCookie && !csrfResult?.ok) {
    throw new Error("WEB_CSRF_TOKEN_UNAVAILABLE");
  }

  return {
    ...input,
    actorUserId: sessionCookie ? undefined : actorUserId,
    sessionCookie,
    csrfToken: csrfResult?.ok ? csrfResult.csrf_token : undefined,
  };
}
