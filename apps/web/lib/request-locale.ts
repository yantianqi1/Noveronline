import "server-only";

import { cookies } from "next/headers";

import { LOCALE_COOKIE_NAME, parseLocale } from "./locale";

export async function currentRequestLocale() {
  const cookieStore = await cookies();
  return parseLocale(cookieStore.get(LOCALE_COOKIE_NAME)?.value);
}
