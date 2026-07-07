import Link from "next/link";

export default function HomePage() {
  return (
    <main className="app-main">
      <section className="panel">
        <p className="eyebrow">MiroFish SaaS</p>
        <h1>项目工作区</h1>
        <p>选择租户和项目后进入写作台、资产库、图谱和世界线。</p>
        <p>
          <Link className="status-pill" href="/demo/projects/demo-project/writer">
            打开 Writer Workbench
          </Link>
        </p>
      </section>
    </main>
  );
}
