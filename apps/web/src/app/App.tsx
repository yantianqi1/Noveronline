import { Link, Route, Routes } from "react-router-dom";

type RouteItem = {
  path: string;
  title: string;
  description: string;
};

const ROUTES: RouteItem[] = [
  { path: "/", title: "Overview", description: "seed 上传、任务、pipeline 总览骨架" },
  { path: "/guide", title: "Guide", description: "工作流说明与引导状态骨架" },
  { path: "/archive-library", title: "Archive Library", description: "档案、记忆与 timeline 骨架" },
  { path: "/story-graph", title: "Story Graph", description: "graph load/build/template config 骨架" },
  { path: "/worldline", title: "Worldline", description: "prepare/session/director workbench 骨架" },
  { path: "/writer", title: "Writer", description: "context pack / draft / review / finalize 骨架" },
  { path: "/character-console", title: "Character Console", description: "agent roster / dialogue / history 骨架" },
  { path: "/llm-facility", title: "LLM Facility", description: "channel / binding / activity 骨架" }
];

function PlaceholderPage({ title, description }: RouteItem) {
  return (
    <section style={{ padding: 24, border: "1px solid #d7d9df", borderRadius: 16 }}>
      <p style={{ margin: 0, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        Rebuild Shell
      </p>
      <h2 style={{ marginBottom: 8 }}>{title}</h2>
      <p style={{ margin: 0, color: "#3a4454" }}>{description}</p>
    </section>
  );
}

export function App() {
  return (
    <main style={{ margin: "0 auto", maxWidth: 1200, padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ marginBottom: 8 }}>MiroFish-Novel New Frontend Baseline</h1>
        <p style={{ margin: 0, color: "#4d5766" }}>
          React + TypeScript + Vite shell 已建立，后续按 contracts 冻结结果拆入 pages / features / entities / shared。
        </p>
      </header>
      <nav style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginBottom: 24 }}>
        {ROUTES.map((item) => (
          <Link
            key={item.path}
            style={{ padding: 12, borderRadius: 12, textDecoration: "none", border: "1px solid #d7d9df", color: "#13202f" }}
            to={item.path}
          >
            {item.title}
          </Link>
        ))}
      </nav>
      <Routes>
        {ROUTES.map((item) => (
          <Route
            key={item.path}
            path={item.path}
            element={<PlaceholderPage {...item} />}
          />
        ))}
      </Routes>
    </main>
  );
}
