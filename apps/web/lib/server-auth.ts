import { devActorUserId, isDevLoginBypassEnabled } from "./dev-access";
import { getSessionCSRFToken, type ApiContext } from "./api";
import { currentRequestSessionCookie } from "./request-session";

function webSessionContext<T extends { tenantId: string }>(input: T): T & ApiContext {
  const sessionCookie = currentRequestSessionCookie({
    required: !isDevLoginBypassEnabled(),
  });
  const actorUserId = devActorUserId();

  return {
    ...input,
    actorUserId: sessionCookie ? undefined : actorUserId,
    sessionCookie,
  };
}

export function webReadApiContext<T extends { tenantId: string }>(input: T): T & ApiContext {
  return webSessionContext(input);
}

export async function webApiContext<T extends { tenantId: string }>(input: T): Promise<T & ApiContext> {
  const context = webSessionContext(input);
  const { sessionCookie } = context;
  const csrfResult = sessionCookie ? await getSessionCSRFToken({ sessionCookie }) : undefined;
  if (sessionCookie && !csrfResult?.ok) {
    throw new Error("WEB_CSRF_TOKEN_UNAVAILABLE");
  }

  return {
    ...context,
    csrfToken: csrfResult?.ok ? csrfResult.csrf_token : undefined,
  };
}
