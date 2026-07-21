import { apiBaseUrl } from "../../lib/config";

/**
 * Minimal login stub.
 * Compose healthcheck probes GET /login — keep this route stable while the
 * rewrite lands auth + workspaces against the Go control plane.
 */
export default function LoginPage() {
  const api = apiBaseUrl();
  return (
    <main className="shell">
      <section className="panel">
        <h1>MiroFish Novel</h1>
        <p>
          前端正在按后端契约重写。当前只保留可启动的最小壳；登录与工作台会逐步接回
          Go API。
        </p>
        <p className="meta">
          API base: <code>{api}</code>
        </p>
      </section>
    </main>
  );
}
