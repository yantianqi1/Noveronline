"use client";

import { LoaderCircle, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import {
  WriterAgentComposer,
  type WriterRunActionResult,
} from "./writer-agent-composer";
import { useWriterRunSession } from "./writer-run-session";

type RecentItem = {
  href: string;
  title: string;
  meta: string;
  kind: "manuscript" | "outline" | "review";
};

type WriterHomeStateProps = {
  locale: Locale;
  selectedChapterId: string;
  selectedSceneId: string;
  writerRunAction: (formData: FormData) => Promise<WriterRunActionResult>;
  contextPickers?: ReactNode;
  recentItems?: RecentItem[];
};

const EXAMPLES = [
  {
    zh: "帮我写第一章的开场，主角在雨夜收到一封没有署名的信，气氛压抑，带一点悬疑。",
    en: "Draft chapter one opening: the protagonist gets an unsigned letter on a rainy night—tense, a touch of mystery.",
    labelZh: "写一个新故事的开场",
    labelEn: "Write a story opening",
  },
  {
    zh: "给这本书列一个 20 章的大纲，主线是主角追查十年前的一桩旧案。",
    en: "Outline 20 chapters; the main line is investigating a decade-old case.",
    labelZh: "给这本书列一个大纲",
    labelEn: "Outline this book",
  },
  {
    zh: "接着上次的章节往下写，保持现在的节奏。",
    en: "Continue from the last chapter; keep the current pace.",
    labelZh: "续写上次的章节",
    labelEn: "Continue the last chapter",
  },
  {
    zh: "帮我审一遍当前正文，重点看人物动机是否连贯。",
    en: "Review the current prose; focus on whether character motives stay coherent.",
    labelZh: "审校已有正文",
    labelEn: "Review existing prose",
  },
] as const;

/**
 * Conversation-first home (docs/refactor-saas/36 W3): one value line, one composer,
 * a few example tasks, and recent artifacts — no rails or tutorials.
 *
 * On submit, shows the user bubble + starting status immediately (before leaving
 * home on successful admission).
 */
export function WriterHomeState({
  locale,
  selectedChapterId,
  selectedSceneId,
  writerRunAction,
  contextPickers,
  recentItems = [],
}: WriterHomeStateProps) {
  const session = useWriterRunSession();
  const pendingInstruction = session?.pendingInstruction;
  const submitting = Boolean(pendingInstruction);

  return (
    <section
      className="writer-home-state"
      aria-label={tx(locale, "开始写作", "Start writing")}
      data-submitting={submitting ? "true" : "false"}
    >
      <div className="writer-home-hero">
        <h1>
          <Bi zh="把你想写的告诉我，剩下的交给写作助手。" en="Tell me what you want to write — the assistant handles the rest." />
        </h1>
        <p>
          <Bi
            zh="它会查阅你的设定、人物与前文，为你起草正文——采用之前，不会动你的手稿。"
            en="It checks your lore, characters, and earlier prose, then drafts — nothing enters the manuscript until you adopt it."
          />
        </p>
      </div>

      {pendingInstruction ? (
        <div className="writer-home-pending-thread" aria-live="polite">
          <article className="writer-message writer-message-user" data-pending-message="true">
            <p>{pendingInstruction}</p>
          </article>
          <p className="writer-agent-working" data-active="true">
            <LoaderCircle aria-hidden="true" className="is-spinning" size={17} />
            <span>
              <Bi zh="正在分析需求…" en="Understanding the request…" />
            </span>
          </p>
        </div>
      ) : null}

      <div className="writer-home-composer">
        <WriterAgentComposer
          locale={locale}
          selectedChapterId={selectedChapterId}
          selectedSceneId={selectedSceneId}
          writerRunAction={writerRunAction}
        >
          {contextPickers}
        </WriterAgentComposer>
      </div>

      {!submitting ? (
        <div className="writer-home-examples" aria-label={tx(locale, "示例任务", "Example tasks")}>
          {EXAMPLES.map((example) => (
            <button
              className="writer-home-example"
              key={example.labelEn}
              onClick={() => fillHomeInstruction(locale === "en" ? example.en : example.zh)}
              type="button"
            >
              <Sparkles aria-hidden="true" size={14} />
              <Bi zh={example.labelZh} en={example.labelEn} />
            </button>
          ))}
        </div>
      ) : null}

      {!submitting && recentItems.length > 0 ? (
        <div className="writer-home-recents">
          <h2>
            <Bi zh="最近" en="Recent" />
          </h2>
          <div className="writer-home-recent-row">
            {recentItems.map((item) => (
              <a className="writer-home-recent-card" href={item.href} key={item.href + item.title}>
                <strong>{item.title}</strong>
                <span>{item.meta}</span>
              </a>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function fillHomeInstruction(text: string) {
  if (typeof document === "undefined") return;
  const field = document.querySelector<HTMLTextAreaElement>(
    '.writer-home-composer textarea[name="instruction"]',
  );
  if (!field) return;
  field.value = text;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.focus();
}
