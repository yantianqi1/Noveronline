"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";
import { useWriterWorkbench, type WriterDrawer } from "./writer-workbench-context";

type DrawerSpec = {
  id: Exclude<WriterDrawer, null>;
  zhTitle: string;
  enTitle: string;
  zhHint: string;
  enHint: string;
  body: ReactNode;
};

/**
 * The slide-up drawer shell. Each drawer is a lid over the paper: click the
 * handle (or backdrop / Esc) to dismiss. Content is server-rendered and passed
 * in as children so forms/actions keep working without client data fetching.
 */
export function WriterDrawers({
  locale,
  structure,
  tools,
  library,
}: {
  locale: Locale;
  structure: ReactNode;
  tools: ReactNode;
  library: ReactNode;
}) {
  const workbench = useWriterWorkbench();
  const drawer = workbench?.drawer ?? null;

  const specs: DrawerSpec[] = [
    {
      id: "structure",
      zhTitle: "结构",
      enTitle: "Structure",
      zhHint: "章节 · 场景 · 片段，点任意项稿纸即跳转",
      enHint: "Chapters, scenes and sections — click to jump the paper",
      body: structure,
    },
    {
      id: "tools",
      zhTitle: "工具",
      enTitle: "Tools",
      zhHint: "按你想做的事分组，展开才看到表单",
      enHint: "Grouped by what you want to do — expand a card to see its form",
      body: tools,
    },
    {
      id: "library",
      zhTitle: "资料",
      enTitle: "Library",
      zhHint: "人物、设定与世界线路径；勾选在右侧输入框上方",
      enHint: "Characters, settings and paths — pick them above the composer",
      body: library,
    },
  ];

  return (
    <>
      {specs.map((spec) => {
        const open = drawer === spec.id;
        return (
          <div
            aria-hidden={!open}
            className={`writer-drawer ${open ? "is-open" : ""}`}
            key={spec.id}
            onClick={(event) => {
              if (event.target === event.currentTarget) workbench?.setDrawer(null);
            }}
            role="presentation"
          >
            <div
              aria-label={tx(locale, spec.zhTitle, spec.enTitle)}
              className="writer-drawer-sheet"
              role="dialog"
            >
              <div className="writer-drawer-head">
                <h2>{tx(locale, spec.zhTitle, spec.enTitle)}</h2>
                <p>{tx(locale, spec.zhHint, spec.enHint)}</p>
                <button
                  aria-label={tx(locale, "关闭", "Close")}
                  className="writer-drawer-close"
                  onClick={() => workbench?.setDrawer(null)}
                  type="button"
                >
                  <X aria-hidden="true" size={18} />
                </button>
              </div>
              <div className="writer-drawer-body">{open ? spec.body : null}</div>
            </div>
          </div>
        );
      })}
    </>
  );
}
