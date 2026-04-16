/**
 * Notification hook — wraps `sonner` toast with typed convenience helpers.
 */

import { toast } from "sonner";

export function useNotification() {
  function notifySuccess(content: string, title = "成功") {
    toast.success(title, { description: content, duration: 3000 });
  }

  function notifyError(content: string, title = "错误") {
    toast.error(title, { description: content, duration: 5000 });
  }

  function notifyWarning(content: string, title = "提示") {
    toast.warning(title, { description: content, duration: 4000 });
  }

  function notifyInfo(content: string, title = "信息") {
    toast.info(title, { description: content, duration: 3000 });
  }

  return { notifySuccess, notifyError, notifyWarning, notifyInfo } as const;
}
