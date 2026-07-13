import { redirect } from "next/navigation";

import { devEntryRedirectPath } from "../../lib/dev-access";

export default function LegacyGuidePage() {
  redirect(devEntryRedirectPath());
}
