import { useNotification } from "naive-ui";

let _notification = null;

export function useAppNotification() {
  _notification = useNotification();

  function notifySuccess(content, title = "成功") {
    _notification.success({ title, content, duration: 3000 });
  }

  function notifyError(content, title = "错误") {
    _notification.error({ title, content, duration: 5000 });
  }

  function notifyWarning(content, title = "提示") {
    _notification.warning({ title, content, duration: 4000 });
  }

  function notifyInfo(content, title = "信息") {
    _notification.info({ title, content, duration: 3000 });
  }

  return { notifySuccess, notifyError, notifyWarning, notifyInfo };
}
