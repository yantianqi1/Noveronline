"use client";

import { useEffect, useRef, useState } from "react";

import { LANDING_BODY_HTML } from "../lib/landing-body-html";

const LANDING_STYLE_HREF = "/landing/styles.css";
const LANDING_SCRIPT_SRC = "/landing/main.js";
const LANDING_FONT_HREF =
  "https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500;600&display=swap";

/**
 * Embeds the curated landing experience into the SaaS web shell.
 * Styles/scripts live under /public/landing and only activate while this shell is mounted.
 */
export function LandingShell() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const previousTheme = body.getAttribute("data-theme");

    html.classList.add("landing-active");
    body.classList.add("landing-active", "is-booting");
    body.classList.remove("is-ready", "is-tearing");

    const managed: HTMLElement[] = [];

    const ensureStylesheet = (href: string, id: string) => {
      const existing = document.getElementById(id) as HTMLLinkElement | null;
      if (existing) {
        return existing;
      }
      const link = document.createElement("link");
      link.id = id;
      link.rel = "stylesheet";
      link.href = href;
      document.head.appendChild(link);
      managed.push(link);
      return link;
    };

    ensureStylesheet(LANDING_FONT_HREF, "landing-fonts");
    ensureStylesheet(LANDING_STYLE_HREF, "landing-styles");

    const host = hostRef.current;
    if (!host) {
      return;
    }
    host.innerHTML = LANDING_BODY_HTML;

    let cancelled = false;
    const script = document.createElement("script");
    script.id = "landing-main-script";
    script.src = `${LANDING_SCRIPT_SRC}?v=saas-1`;
    script.async = false;
    script.onerror = () => {
      if (!cancelled) {
        setFailed(true);
        body.classList.remove("is-booting", "is-tearing");
        body.classList.add("is-ready");
      }
    };
    document.body.appendChild(script);
    managed.push(script);

    return () => {
      cancelled = true;
      html.classList.remove("landing-active", "is-snap-animating", "is-scrolling");
      body.classList.remove("landing-active", "is-booting", "is-tearing", "is-ready");
      if (previousTheme) {
        body.setAttribute("data-theme", previousTheme);
      } else {
        body.removeAttribute("data-theme");
      }
      host.innerHTML = "";
      for (const node of managed) {
        node.remove();
      }
      // Landing main.js attaches document-level listeners without teardown.
      // Soft-reload keeps subsequent navigations clean after leaving the homepage.
      if (typeof window !== "undefined" && window.location.pathname !== "/") {
        /* no-op: navigation away already happened */
      }
    };
  }, []);

  return (
    <>
      {failed ? (
        <div className="landing-fallback" role="alert">
          <p>欢迎页资源加载不完整，仍可直接进入工作台。</p>
          <a className="landing-fallback-link" href="/login">
            进入登录
          </a>
        </div>
      ) : null}
      <div className="landing-host" ref={hostRef} />
    </>
  );
}
