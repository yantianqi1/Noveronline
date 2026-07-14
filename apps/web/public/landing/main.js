(() => {
  const bootScreen = document.getElementById("boot-screen");
  const previousBootScreen = window.__MIROFISH_LANDING_BOOTED__;
  if (previousBootScreen === bootScreen && bootScreen?.isConnected) return;
  window.__MIROFISH_LANDING_BOOTED__ = bootScreen;
  /**
   * 手机端（≤768px）使用竖屏 9:16 插画与视频素材，对齐「首页-手机端」设计稿；
   * 桌面仍用横版 cinematic 素材，互不覆盖。
   */
  const isMobileLanding = window.matchMedia("(max-width: 768px)").matches;
  const ASSET_PREFIX = "/landing/assets/";
  const MOBILE_ASSET_PREFIX = "/landing/assets/mobile/";

  function resolveLandingAsset(path) {
    if (!path || typeof path !== "string") return path;
    if (!isMobileLanding) return path;
    if (path.startsWith(MOBILE_ASSET_PREFIX)) return path;
    if (path.startsWith(ASSET_PREFIX)) {
      return MOBILE_ASSET_PREFIX + path.slice(ASSET_PREFIX.length);
    }
    return path;
  }

  function applyMobileAssetSources() {
    if (!isMobileLanding) return;
    document.documentElement.classList.add("landing-mobile-assets");

    document.querySelectorAll(".scene-video-stack[data-video-src]").forEach((stack) => {
      const src = stack.getAttribute("data-video-src");
      if (src) stack.setAttribute("data-video-src", resolveLandingAsset(src));
    });

    document.querySelectorAll("video[poster]").forEach((video) => {
      const poster = video.getAttribute("poster");
      if (poster) video.setAttribute("poster", resolveLandingAsset(poster));
    });

    document.querySelectorAll("[data-reveal-src]").forEach((el) => {
      const src = el.getAttribute("data-reveal-src");
      if (src) el.setAttribute("data-reveal-src", resolveLandingAsset(src));
    });

    document.querySelectorAll(".scene-reveal-img[style]").forEach((el) => {
      const style = el.getAttribute("style") || "";
      const next = style.replace(
        /url\((['"]?)(\/landing\/assets\/(?!mobile\/)[^'")]+)\1\)/g,
        (_m, q, url) => `url(${q || ""}${resolveLandingAsset(url)}${q || ""})`,
      );
      if (next !== style) el.setAttribute("style", next);
    });
  }

  applyMobileAssetSources();

  /**
   * 开屏只预载「首幕关键资源」，其余按需加载。
   * 禁止把整段视频 fetch 成 Blob（易 OOM，Chrome 报错/崩溃 错误代码 5）。
   */
  const BOOT_IMAGES = [
    resolveLandingAsset("/landing/assets/scene-0-hero.jpg"),
    resolveLandingAsset("/landing/assets/scene-0-reveal.jpg"),
  ];
  const LAZY_IMAGES = [
    resolveLandingAsset("/landing/assets/scene-1-pain.jpg"),
    resolveLandingAsset("/landing/assets/scene-1-reveal.jpg"),
    resolveLandingAsset("/landing/assets/scene-2-pipeline.jpg"),
    resolveLandingAsset("/landing/assets/scene-2-reveal.jpg"),
    resolveLandingAsset("/landing/assets/scene-3-caps.jpg"),
    resolveLandingAsset("/landing/assets/scene-3-reveal.jpg"),
    resolveLandingAsset("/landing/assets/scene-4-workbench.jpg"),
    resolveLandingAsset("/landing/assets/scene-4-reveal.jpg"),
    resolveLandingAsset("/landing/assets/scene-5-finale.jpg"),
    resolveLandingAsset("/landing/assets/scene-5-reveal.jpg"),
    // 手机端装饰层（桌面路径不存在时 load 会静默失败，可接受）
    "/landing/assets/mobile/decor/constellation-graph.jpg",
    "/landing/assets/mobile/decor/vermilion-seal.jpg",
    "/landing/assets/mobile/decor/floating-note-cards.jpg",
    "/landing/assets/mobile/decor/pipeline-node-icons.jpg",
    "/landing/assets/mobile/decor/book-cover-shanhai.jpg",
    "/landing/assets/mobile/decor/character-portrait-hanfu.jpg",
  ];

  const bootFill = document.getElementById("boot-bar-fill");
  const bootPct = document.getElementById("boot-pct");
  const bootLabel = document.getElementById("boot-label");
  const scenes = Array.from(document.querySelectorAll(".scene"));
  const dots = Array.from(document.querySelectorAll(".rail-dot"));
  const track = document.getElementById("track");
  const sceneIndexEl = document.getElementById("scene-index");
  const railProgress = document.getElementById("rail-progress");
  const total = scenes.length;

  if (!total || !track) return;

  let current = 0;
  let locked = false;
  let ready = false;
  let settleTimer = 0;
  let scrollFrame = 0;
  let snapFrame = 0;
  let snapLocked = false;
  let snapTarget = -1;
  let activeStack = null;
  let sceneMetrics = [];
  let metricsFrame = 0;
  /** @type {Map<Element, ReturnType<typeof createSeamlessStack>>} */
  const videoStacks = new Map();

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  /**
   * 手机端立体叠层 deck：不用文档滚动，手势/滚轮驱动 3D 切幕
   * 前进：旧幕沉入深处消失，新幕自上方「映射」落位；
   * 后退：镜像路径（旧幕沉入深处，前一幕自下方映回）。
   */
  const useSpatialDeck = isMobileLanding;
  if (useSpatialDeck) {
    document.documentElement.classList.add("landing-spatial");
  }
  const SNAP_DURATION = useSpatialDeck ? 640 : 480;
  /** 全行程切幕时长：略短更「跟手」，曲线用 ease 保证不跳 */
  const SPATIAL_DURATION = reducedMotion ? 0 : 520;
  let spatialScrubPx = Math.max(140, Math.min(240, (window.innerHeight || 640) * 0.28));
  /** 缓存视口高度，避免每帧读 layout */
  let spatialVh = window.innerHeight || 640;
  /** 当前过渡对，便于只清理这两个节点 */
  let spatialSourceEl = null;
  let spatialTargetEl = null;

  function refreshSpatialMetrics() {
    spatialVh = window.innerHeight || 640;
    spatialScrubPx = Math.max(140, Math.min(240, spatialVh * 0.28));
  }

  scenes.forEach((scene) => {
    scene.querySelectorAll("[data-reveal]").forEach((el, i) => {
      el.style.setProperty("--reveal-i", String(i));
    });
  });

  /* ───────── Preload：轻量、有超时、不 OOM ───────── */

  function setBootProgress(ratio, label) {
    const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)));
    if (bootFill) bootFill.style.width = `${pct}%`;
    if (bootPct) bootPct.textContent = String(pct);
    if (label && bootLabel) bootLabel.textContent = label;
  }

  function withTimeout(promise, ms, fallback) {
    let timer = 0;
    return Promise.race([
      Promise.resolve(promise).catch(() => fallback),
      new Promise((resolve) => {
        timer = window.setTimeout(() => resolve(fallback), ms);
      }),
    ]).finally(() => window.clearTimeout(timer));
  }

  function loadImageFromUrl(url, timeoutMs = 3000) {
    return new Promise((resolve) => {
      const img = new Image();
      let settled = false;
      const done = () => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve(img);
      };
      const timer = window.setTimeout(done, timeoutMs);
      img.onload = done;
      img.onerror = done;
      img.src = url;
    });
  }

  function prefetchLazyImages() {
    let next = 0;
    const scheduleNext = () => {
      if (next >= LAZY_IMAGES.length) return;
      const loadNext = () => {
        const img = new Image();
        img.decoding = "async";
        img.fetchPriority = "low";
        img.src = LAZY_IMAGES[next];
        next += 1;
        window.setTimeout(scheduleNext, 120);
      };
      if ("requestIdleCallback" in window) {
        window.requestIdleCallback(loadNext, { timeout: 2500 });
      } else {
        window.setTimeout(loadNext, 180);
      }
    };
    window.setTimeout(scheduleNext, 800);
  }

  /**
   * 双路视频无缝循环。
   * 原生 loop 在片尾 seek→0 时会闪一帧/卡顿；这里用两路交叉淡入抹平断点。
   */
  function createSeamlessStack(stack) {
    const src = stack.dataset.videoSrc;
    if (!src) return null;

    const existing = Array.from(stack.querySelectorAll("video.scene-video"));
    const poster = existing[0]?.getAttribute("poster") || "";
    const template = existing[0] || null;
    // 用 poster 作栈底，避免未解码时整幕纯色空背景
    if (poster) {
      stack.style.backgroundImage = `url("${poster}")`;
    }

    const makeVideo = (isPrimary) => {
      const video = template && isPrimary ? template : document.createElement("video");
      video.className = isPrimary ? "scene-video is-on" : "scene-video";
      video.muted = true;
      video.defaultMuted = true;
      video.playsInline = true;
      video.autoplay = false;
      video.controls = false;
      video.disablePictureInPicture = true;
      video.setAttribute("muted", "");
      video.setAttribute("playsinline", "");
      video.setAttribute("webkit-playsinline", "");
      video.setAttribute("data-scene-video", "");
      // 禁用原生 loop：由双缓冲接管
      video.loop = false;
      video.removeAttribute("loop");
      video.preload = isPrimary ? "auto" : "metadata";
      if (poster) video.setAttribute("poster", poster);
      // 直接设 src，避免 clone 后 <source> 不重新加载
      if (video.getAttribute("src") !== src) {
        video.querySelectorAll("source").forEach((node) => node.remove());
        video.src = src;
      }
      try {
        video.setAttribute("fetchpriority", isPrimary ? "high" : "low");
      } catch {
        /* ignore */
      }
      return video;
    };

    const a = makeVideo(true);
    const b = makeVideo(false);
    if (!a.isConnected) stack.appendChild(a);
    if (!b.isConnected) stack.appendChild(b);
    // 清理多余 video（只保留双路）
    Array.from(stack.querySelectorAll("video.scene-video")).forEach((node) => {
      if (node !== a && node !== b) node.remove();
    });

    const videos = [a, b];
    let active = 0;
    let running = false;
    let swapping = false;
    let swapTimer = 0;
    let rafId = 0;
    let vfcId = 0;

    // 片尾前多少秒启动交叉；交叉时长与 CSS transition 对齐
    const LEAD_S = 0.28;
    const FADE_MS = 260;

    const hardMute = (video) => {
      video.muted = true;
      video.defaultMuted = true;
      video.volume = 0;
    };

    const safePlay = (video) => {
      hardMute(video);
      video.playsInline = true;
      try {
        video.playbackRate = 1;
      } catch {
        /* ignore */
      }
      const tryPlay = () => {
        const p = video.play();
        if (p && typeof p.catch === "function") {
          p.catch(() => {
            /* autoplay / interrupted — ignore */
          });
        }
      };
      tryPlay();
      // 尚未缓冲完时，等到可播再补一次 play，避免后幕一直停在 poster
      if (video.readyState < 2) {
        const onReady = () => {
          video.removeEventListener("canplay", onReady);
          video.removeEventListener("loadeddata", onReady);
          if (running && video === videos[active]) tryPlay();
        };
        video.addEventListener("canplay", onReady, { once: true });
        video.addEventListener("loadeddata", onReady, { once: true });
      }
    };

    const cancelWatch = () => {
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
      if (vfcId && videos[active] && typeof videos[active].cancelVideoFrameCallback === "function") {
        try {
          videos[active].cancelVideoFrameCallback(vfcId);
        } catch {
          /* ignore */
        }
      }
      vfcId = 0;
    };

    const finishSwap = (fromIdx, toIdx) => {
      const from = videos[fromIdx];
      const to = videos[toIdx];
      from.classList.remove("is-on", "is-incoming");
      to.classList.add("is-on");
      to.classList.remove("is-incoming");
      try {
        from.pause();
        // 预 seek 到起点，下一次接力几乎零延迟
        if (from.readyState >= 1) from.currentTime = 0;
      } catch {
        /* ignore */
      }
      active = toIdx;
      swapping = false;
      if (running) armWatch(to);
    };

    const beginCrossfade = () => {
      if (!running || swapping) return;
      const fromIdx = active;
      const toIdx = 1 - active;
      const from = videos[fromIdx];
      const to = videos[toIdx];
      const duration = from.duration;
      if (!Number.isFinite(duration) || duration <= 0) return;

      swapping = true;
      cancelWatch();

      try {
        // 不要 load()：会丢已缓冲帧并引发主线程尖峰
        if (to.currentTime > 0.02) to.currentTime = 0;
      } catch {
        /* ignore */
      }
      hardMute(to);
      to.preload = "auto";
      safePlay(to);
      // from 保持 is-on 垫底；to 以 is-incoming 顶层淡入
      from.classList.add("is-on");
      from.classList.remove("is-incoming");
      to.classList.add("is-incoming");

      if (swapTimer) window.clearTimeout(swapTimer);
      swapTimer = window.setTimeout(() => {
        swapTimer = 0;
        finishSwap(fromIdx, toIdx);
      }, FADE_MS);
    };

    const checkNearEnd = (video, mediaTime) => {
      if (!running || swapping || video !== videos[active]) return;
      const duration = video.duration;
      if (!Number.isFinite(duration) || duration < 0.5) return;
      const t = Number.isFinite(mediaTime) ? mediaTime : video.currentTime;
      // 接近片尾，或已到达/越过结尾（部分浏览器 ended 前 currentTime 卡在 duration）
      if (t >= duration - LEAD_S || video.ended) {
        beginCrossfade();
      }
    };

    const armWatch = (video) => {
      cancelWatch();
      if (!running || !video) return;

      if (typeof video.requestVideoFrameCallback === "function") {
        const onFrame = (_now, meta) => {
          if (!running || swapping || video !== videos[active]) return;
          checkNearEnd(video, meta?.mediaTime);
          if (!running || swapping || video !== videos[active]) return;
          vfcId = video.requestVideoFrameCallback(onFrame);
        };
        vfcId = video.requestVideoFrameCallback(onFrame);
        return;
      }

      const tick = () => {
        if (!running || swapping || video !== videos[active]) return;
        checkNearEnd(video, video.currentTime);
        if (!running || swapping || video !== videos[active]) return;
        rafId = requestAnimationFrame(tick);
      };
      rafId = requestAnimationFrame(tick);
    };

    const onEnded = (event) => {
      if (!running) return;
      if (event.target === videos[active] && !swapping) beginCrossfade();
    };

    videos.forEach((video) => {
      hardMute(video);
      video.addEventListener("ended", onEnded);
      // 部分浏览器 timeupdate 间隔大，作为 rVFC 失败时的兜底
      video.addEventListener("timeupdate", () => {
        if (video === videos[active]) checkNearEnd(video, video.currentTime);
      });
    });

    let primeTimer = 0;
    const primeStandby = (video) => {
      hardMute(video);
      video.preload = "auto";
      // 静默解码第 0 帧，避免接力时首帧黑一下；opacity:0 不可见
      const kick = video.play();
      if (kick && typeof kick.then === "function") {
        kick
          .then(() => {
            if (running && video === videos[active]) return;
            try {
              video.pause();
              if (video.currentTime > 0.01) video.currentTime = 0;
            } catch {
              /* ignore */
            }
          })
          .catch(() => {});
      } else {
        try {
          video.pause();
        } catch {
          /* ignore */
        }
      }
    };

    const schedulePrimeStandby = () => {
      if (primeTimer) window.clearTimeout(primeTimer);
      // 错开主轨开播，避免双路同时抢解码器造成起播卡顿
      primeTimer = window.setTimeout(() => {
        primeTimer = 0;
        if (!running) return;
        const standby = videos[1 - active];
        if (standby && standby.paused) primeStandby(standby);
      }, 500);
    };

    return {
      stack,
      videos,
      warm() {
        videos.forEach((video) => {
          hardMute(video);
          video.preload = "auto";
          try {
            // 触发缓冲，不强制 load() 清掉已有数据
            if (video.readyState < 2 && !video.src) video.src = src;
          } catch {
            /* ignore */
          }
        });
      },
      play() {
        if (running && !videos[active].paused && !videos[active].ended) {
          armWatch(videos[active]);
          return;
        }
        running = true;
        swapping = false;
        if (swapTimer) {
          window.clearTimeout(swapTimer);
          swapTimer = 0;
        }
        videos.forEach((video, i) => {
          hardMute(video);
          video.preload = "auto";
          video.classList.toggle("is-on", i === active);
          video.classList.remove("is-incoming");
          if (i !== active) {
            try {
              video.pause();
            } catch {
              /* ignore */
            }
          }
        });
        const current = videos[active];
        try {
          // 若卡在片尾，重置
          if (current.ended || (current.duration && current.currentTime >= current.duration - 0.05)) {
            current.currentTime = 0;
          }
        } catch {
          /* ignore */
        }
        safePlay(current);
        armWatch(current);
        schedulePrimeStandby();
      },
      pause({ keepFrame = true } = {}) {
        running = false;
        swapping = false;
        cancelWatch();
        if (swapTimer) {
          window.clearTimeout(swapTimer);
          swapTimer = 0;
        }
        if (primeTimer) {
          window.clearTimeout(primeTimer);
          primeTimer = 0;
        }
        videos.forEach((video) => {
          try {
            if (!video.paused) video.pause();
          } catch {
            /* ignore */
          }
          video.classList.remove("is-incoming");
          // keepFrame：保留最后一帧作封面，不 seek 避免黑闪
          if (!keepFrame) {
            try {
              video.currentTime = 0;
            } catch {
              /* ignore */
            }
          }
        });
      },
      destroy() {
        this.pause({ keepFrame: true });
        videos.forEach((video) => {
          video.removeEventListener("ended", onEnded);
        });
      },
    };
  }

  function ensureVideoStack(stack) {
    if (!stack) return null;
    let controller = videoStacks.get(stack);
    if (controller) return controller;
    controller = createSeamlessStack(stack);
    if (controller) videoStacks.set(stack, controller);
    return controller;
  }

  /**
   * 视频栈懒创建：手机端只建当前±1，避免 6 幕 × 双路 = 12 个 video 同时占解码/内存。
   * 桌面仍可全量预建（滚动路径需要）。
   */
  function initVideoStacks({ eagerAll = !useSpatialDeck } = {}) {
    if (eagerAll) {
      document.querySelectorAll(".scene-video-stack[data-video-src]").forEach((stack) => {
        ensureVideoStack(stack);
      });
      return;
    }
    // 手机：只建首幕，邻幕在 warm 时再建
    ensureVideoStack(stackForScene(0));
  }

  function pauseAllVideos() {
    videoStacks.forEach((controller) => controller.pause({ keepFrame: true }));
    activeStack = null;
  }

  function stackForScene(index) {
    return scenes[index]?.querySelector(".scene-video-stack[data-video-src]") || null;
  }

  function warmNeighborVideos(index) {
    // 只预热当前 + 下一幕（优先前进方向），控制同时解码路数
    const neighbors = useSpatialDeck
      ? [index, index + 1, index - 1]
      : [index - 1, index, index + 1];
    neighbors.forEach((i) => {
      if (i < 0 || i >= total) return;
      const stack = stackForScene(i);
      ensureVideoStack(stack)?.warm();
    });
  }

  function playSceneVideo(index) {
    const stack = stackForScene(index);
    const controller = ensureVideoStack(stack);
    videoStacks.forEach((ctrl, key) => {
      if (key !== stack) ctrl.pause({ keepFrame: true });
    });
    activeStack = stack;
    // 延后邻幕 warm，避免与起播抢同一帧
    if (useSpatialDeck) {
      window.setTimeout(() => {
        if (current === index && !snapLocked) warmNeighborVideos(index);
      }, 120);
    } else {
      warmNeighborVideos(index);
    }
    if (!controller) return;
    controller.play();
  }

  function syncSceneMedia(index, { sliding = false } = {}) {
    if (sliding) {
      // 保留已解码的最后一帧，只暂停解码；切幕时调用 load() 会造成主线程尖峰和黑闪。
      if (activeStack) {
        videoStacks.get(activeStack)?.pause({ keepFrame: true });
      }
      // 滑动中只 ensure 目标栈，不 warm 全邻域
      ensureVideoStack(stackForScene(index));
      return;
    }
    playSceneVideo(index);
  }

  async function preloadAllAssets() {
    const units = BOOT_IMAGES.length + 1;
    let completed = 0;
    const bump = (label) => {
      completed += 1;
      setBootProgress(Math.min(completed / units, 0.99), label);
    };

    setBootProgress(0.08, "铺开书页…");
    try {
      if (document.fonts?.ready) {
        await withTimeout(document.fonts.ready, 600, null);
      }
    } catch {
      /* ignore */
    }
    bump("字体就绪");

    await Promise.all(
      BOOT_IMAGES.map(async (url) => {
        try {
          await loadImageFromUrl(url, 2000);
        } catch {
          /* ignore */
        } finally {
          bump("缓存序章画面…");
        }
      })
    );

    // 初始化双路栈并预热首幕，不阻塞进站
    initVideoStacks();
    const heroStack = document.querySelector("#scene-0 .scene-video-stack[data-video-src]");
    if (heroStack) {
      const controller = videoStacks.get(heroStack);
      controller?.warm();
    }

    setBootProgress(1, "准备就绪");
  }

  function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  /** 首幕标题拆成词组，做 blur → 清晰入场 */
  function buildHeroTitle() {
    const title = document.getElementById("hero-title");
    if (!title) return;

    const lines = [
      { parts: ["把", "长篇", "小说"], accent: false },
      { parts: ["变成", "可推演的", "世界"], accent: true },
    ];

    title.textContent = "";
    let delay = 0.12;
    lines.forEach((line, lineIndex) => {
      if (lineIndex > 0) {
        title.appendChild(document.createElement("br"));
      }
      line.parts.forEach((part) => {
        const span = document.createElement("span");
        span.className = line.accent ? "word-reveal is-accent" : "word-reveal";
        span.textContent = part;
        span.style.animationDelay = `${delay}s`;
        title.appendChild(span);
        delay += 0.07;
      });
    });
  }

  function playHeroIntro() {
    buildHeroTitle();

    const staged = [
      { el: document.getElementById("hero-eyebrow"), delay: 80 },
      { el: document.getElementById("hero-lede"), delay: 520 },
      { el: document.getElementById("hero-actions"), delay: 680 },
      { el: document.getElementById("hero-scroll-hint"), delay: 980 },
    ];

    staged.forEach(({ el, delay }) => {
      if (!el) return;
      el.classList.add("hero-intro-item");
      window.setTimeout(() => {
        el.classList.add("is-in");
        // CTA 额外弹入
        if (el.id === "hero-actions") {
          const pill = el.querySelector(".cta-pill-hero");
          if (pill) {
            pill.classList.add("is-in");
            pill.style.opacity = "0";
            requestAnimationFrame(() => {
              pill.style.opacity = "";
            });
          }
        }
      }, reducedMotion ? 0 : delay);
    });
  }

  function bindParallax() {
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    if (!finePointer.matches || reducedMotion) return;

    const revealRoots = Array.from(document.querySelectorAll("[data-scene-reveal]"));
    if (!revealRoots.length) return;

    let raf = 0;
    let spotX = window.innerWidth * 0.42;
    let spotY = window.innerHeight * 0.4;
    let goalX = spotX;
    let goalY = spotY;
    let spotlightOn = false;
    let activeReveal = null;

    const getRevealParts = (rootEl) => {
      if (!rootEl) return null;
      return {
        root: rootEl,
        win: rootEl.querySelector(".scene-reveal-window"),
        img: rootEl.querySelector(".scene-reveal-img"),
        glow: rootEl.querySelector(".scene-reveal-glow"),
        scene: rootEl.closest(".scene"),
      };
    };
    const revealParts = new Map(revealRoots.map((rootEl) => [rootEl, getRevealParts(rootEl)]));

    const bindActiveReveal = () => {
      const scene = scenes[current];
      const next = scene ? scene.querySelector("[data-scene-reveal]") : null;
      if (activeReveal && activeReveal !== next) {
        activeReveal.classList.remove("is-lit");
        const prevScene = activeReveal.closest(".scene");
        if (prevScene) prevScene.classList.remove("has-spot-veil");
      }
      activeReveal = next;
      return revealParts.get(activeReveal) || null;
    };

    const applySpot = (x, y, parts) => {
      if (!parts?.win || !parts?.img) return;
      const tWin = `translate3d(${x}px, ${y}px, 0) translate3d(-50%, -50%, 0)`;
      parts.win.style.transform = tWin;
      parts.img.style.transform = `translate3d(${-x}px, ${-y}px, 0)`;
      if (parts.glow) parts.glow.style.transform = tWin;
    };

    const tick = () => {
      raf = 0;
      if (!ready || locked) return;

      spotX += (goalX - spotX) * 0.14;
      spotY += (goalY - spotY) * 0.14;

      const parts = revealParts.get(activeReveal) || null;
      applySpot(spotX, spotY, parts);

      if (Math.abs(goalX - spotX) > 0.4 || Math.abs(goalY - spotY) > 0.4) {
        raf = requestAnimationFrame(tick);
      }
    };

    const requestTick = () => {
      if (!raf) raf = requestAnimationFrame(tick);
    };

    const turnOffSpotlight = () => {
      spotlightOn = false;
      document.body.classList.remove("has-spotlight");
      revealRoots.forEach((el) => {
        el.classList.remove("is-lit");
        const sc = el.closest(".scene");
        if (sc) sc.classList.remove("has-spot-veil");
      });
      if (raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    };

    window.addEventListener(
      "pointermove",
      (event) => {
        if (!ready || locked) return;

        goalX = event.clientX;
        goalY = event.clientY;

        const parts = bindActiveReveal();
        if (!parts?.win) return;

        if (!spotlightOn) {
          spotlightOn = true;
          document.body.classList.add("has-spotlight");
          spotX = goalX;
          spotY = goalY;
        }

        if (activeReveal) {
          activeReveal.classList.add("is-lit");
          parts.scene?.classList.add("has-spot-veil");
        }

        applySpot(spotX, spotY, parts);
        requestTick();
      },
      { passive: true }
    );

    window.addEventListener("pointerleave", turnOffSpotlight, { passive: true });

    // 切幕时重置当前柔光层
    const syncRevealOnSceneChange = () => {
      turnOffSpotlight();
      bindActiveReveal();
    };

    // 暴露给 goTo 使用
    window.__landingResetSpotlight = syncRevealOnSceneChange;
  }

  async function playSplashThenReady() {
    if (!bootScreen) {
      document.body.classList.remove("is-booting");
      document.body.classList.add("is-ready");
      return;
    }

    if (reducedMotion) {
      bootScreen.classList.add("is-done");
      bootScreen.setAttribute("aria-busy", "false");
      document.body.classList.remove("is-booting");
      document.body.classList.add("is-ready");
      window.setTimeout(() => bootScreen.remove(), 200);
      return;
    }

    // 卡片收起 → 露出首页 → 色块上下撕开
    bootScreen.classList.add("is-tearing");
    document.body.classList.add("is-tearing", "is-ready");
    await wait(1150);
    document.body.classList.remove("is-booting", "is-tearing");
    bootScreen.classList.add("is-done");
    bootScreen.setAttribute("aria-busy", "false");
    await wait(350);
    bootScreen.remove();
  }

  /* ───────── Stage runtime ───────── */

  function measureSceneMetrics() {
    metricsFrame = 0;
    if (useSpatialDeck) {
      // 立体 deck 为固定叠层，不再依赖文档 scroll offset
      refreshSpatialMetrics();
      sceneMetrics = scenes.map(() => ({ top: 0, height: spatialVh || 1 }));
      return;
    }
    sceneMetrics = scenes.map((scene) => ({
      top: scene.offsetTop,
      height: scene.offsetHeight,
    }));
  }

  function queueSceneMeasurement() {
    sceneMetrics = [];
    if (metricsFrame) return;
    metricsFrame = requestAnimationFrame(measureSceneMetrics);
  }

  function sceneMetric(index) {
    if (sceneMetrics.length !== total) measureSceneMetrics();
    return sceneMetrics[index];
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function setTheme(index) {
    document.body.dataset.theme = scenes[index]?.dataset.theme || "warm";
  }

  function updateChrome(index) {
    dots.forEach((dot, i) => {
      dot.classList.toggle("is-active", i === index);
    });
    if (sceneIndexEl) sceneIndexEl.textContent = pad(index + 1);
    if (railProgress) {
      const fill = total <= 1 ? 100 : (index / (total - 1)) * 100;
      railProgress.style.setProperty("--rail-fill", `${fill}%`);
    }
  }

  function markNeighbors(index) {
    for (let i = 0; i < total; i += 1) {
      const scene = scenes[i];
      const dist = Math.abs(i - index);
      scene.classList.toggle("is-active", i === index);
      scene.classList.toggle("is-prev", i === index - 1);
      scene.classList.toggle("is-next", i === index + 1);
      scene.classList.remove("is-settled");
      scene.toggleAttribute("data-far", dist > 1);
    }
  }

  function markSnapScenes(index) {
    scenes.forEach((scene) => scene.classList.remove("is-snap-source", "is-snap-target"));
    scenes[current]?.classList.add("is-snap-source");
    scenes[index]?.classList.add("is-snap-target");
  }

  function clearSpatialPaint() {
    const pair = [spatialSourceEl, spatialTargetEl];
    spatialSourceEl = null;
    spatialTargetEl = null;
    // 优先只清过渡对；兜底扫一遍去掉残留 class（极少路径）
    const nodes = pair[0] || pair[1] ? pair.filter(Boolean) : scenes;
    nodes.forEach((scene) => {
      if (!scene) return;
      scene.classList.remove("is-spatial-source", "is-spatial-target", "is-spatial-scrubbing");
      scene.style.transform = "";
      scene.style.opacity = "";
      scene.style.zIndex = "";
      scene.style.willChange = "";
      scene.style.transformOrigin = "";
    });
  }

  /**
   * 单一缓动。禁止 animate 与 paint 叠两层 ease。
   * 使用纯多项式，避免 Math.pow 在热路径上的额外开销（影响可忽略，但更可预测）。
   */
  function spatialEase(t) {
    const x = t < 0 ? 0 : t > 1 ? 1 : t;
    // easeOutCubic
    const inv = 1 - x;
    return 1 - inv * inv * inv;
  }

  /**
   * 切幕插值：只写 transform + opacity（GPU 友好）。
   * 去掉 rotateX / filter / box-shadow —— 带 video 的大层上 3D 旋转是掉帧主因。
   * 景深感用 scale + translateY + 轻微 translateZ 表达。
   */
  function paintSpatialFrame(source, target, dir, e) {
    const p = e < 0 ? 0 : e > 1 ? 1 : e;
    const vh = spatialVh;
    const s = source.style;
    const t = target.style;

    if (dir > 0) {
      // 旧幕：缩小 + 微下沉 + 淡出（往「深处」）
      const sy = p * vh * 0.035;
      const ss = 1 - p * 0.14;
      const so = 1 - p * 0.9;
      s.transform = `translate3d(0,${sy | 0}px,0) scale(${ss})`;
      s.opacity = so < 0.02 ? "0" : String((so * 1000 | 0) / 1000);

      // 新幕：自上方映入
      const ty = -(1 - p) * vh * 0.88;
      const ts = 0.97 + p * 0.03;
      const to = 0.15 + p * 0.85;
      t.transform = `translate3d(0,${ty | 0}px,0) scale(${ts})`;
      t.opacity = String((to * 1000 | 0) / 1000);
    } else {
      const sy = -p * vh * 0.035;
      const ss = 1 - p * 0.12;
      const so = 1 - p * 0.9;
      s.transform = `translate3d(0,${sy | 0}px,0) scale(${ss})`;
      s.opacity = so < 0.02 ? "0" : String((so * 1000 | 0) / 1000);

      const ty = (1 - p) * vh * 0.88;
      const ts = 0.97 + p * 0.03;
      const to = 0.15 + p * 0.85;
      t.transform = `translate3d(0,${ty | 0}px,0) scale(${ts})`;
      t.opacity = String((to * 1000 | 0) / 1000);
    }
  }

  /** 开始一对幕的过渡：类名 / will-change / z-index 只打一次 */
  function armSpatialPair(source, target, dir) {
    spatialSourceEl = source;
    spatialTargetEl = target;
    source.classList.add("is-spatial-source");
    source.classList.remove("is-spatial-target");
    target.classList.add("is-spatial-target", "is-active");
    target.classList.remove("is-spatial-source");
    target.removeAttribute("data-far");
    source.style.willChange = "transform, opacity";
    target.style.willChange = "transform, opacity";
    source.style.zIndex = "2";
    target.style.zIndex = "6";
    source.style.transformOrigin = "50% 50%";
    target.style.transformOrigin = dir > 0 ? "50% 0%" : "50% 100%";
  }

  function finishSlide() {
    scenes.forEach((scene) => scene.classList.remove("is-snap-source", "is-snap-target"));
    clearSpatialPaint();
    document.documentElement.classList.remove("is-scrolling");
    locked = false;
  }

  function nearestSceneIndex() {
    if (useSpatialDeck) return current;
    const pageTop = window.scrollY || document.documentElement.scrollTop || 0;
    let nearest = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    if (sceneMetrics.length !== total) measureSceneMetrics();
    sceneMetrics.forEach((metric, index) => {
      const distance = Math.abs(metric.top - pageTop);
      if (distance < nearestDistance) {
        nearest = index;
        nearestDistance = distance;
      }
    });
    return nearest;
  }

  function resetSpotlight() {
    if (typeof window.__landingResetSpotlight === "function") {
      window.__landingResetSpotlight();
    } else {
      document.body.classList.remove("has-spotlight");
    }
  }

  function setActiveScene(next, { force = false, updateTheme = true } = {}) {
    if (next < 0 || next >= total) return false;
    const changed = next !== current;
    if (!changed && !force) return false;
    current = next;
    markNeighbors(next);
    updateChrome(next);
    if (updateTheme) setTheme(next);
    resetSpotlight();
    return changed;
  }

  function settleStageScroll() {
    if (useSpatialDeck) return;
    window.clearTimeout(settleTimer);
    settleTimer = 0;
    if (snapLocked) return;
    setActiveScene(nearestSceneIndex(), { force: true });
    scenes[current]?.classList.add("is-settled");
    syncSceneMedia(current, { sliding: false });
    finishSlide();
  }

  function queueStageSettle() {
    if (useSpatialDeck || snapLocked) return;
    window.clearTimeout(settleTimer);
    settleTimer = window.setTimeout(settleStageScroll, reducedMotion ? 0 : 80);
  }

  function handleStageScroll() {
    if (useSpatialDeck || !ready || snapLocked) return;
    if (!locked) {
      locked = true;
      document.documentElement.classList.add("is-scrolling");
      resetSpotlight();
      syncSceneMedia(current, { sliding: true });
    }
    queueStageSettle();
    if (scrollFrame) return;

    scrollFrame = requestAnimationFrame(() => {
      scrollFrame = 0;
      setActiveScene(nearestSceneIndex(), { updateTheme: false });
    });
  }

  function snapProgress(value) {
    const t = Math.max(0, Math.min(1, value));
    if (t < 0.55) {
      const local = t / 0.55;
      return 0.88 * (1 - Math.pow(1 - local, 3));
    }
    if (t < 0.78) {
      const local = (t - 0.55) / 0.23;
      const smooth = local * local * (3 - 2 * local);
      return 0.88 + 0.08 * smooth;
    }
    const local = (t - 0.78) / 0.22;
    const smooth = local * local * (3 - 2 * local);
    return 0.96 + 0.04 * smooth;
  }

  function stopSnapFrame() {
    if (snapFrame) cancelAnimationFrame(snapFrame);
    snapFrame = 0;
  }

  function completeSnap(index) {
    stopSnapFrame();
    window.clearTimeout(settleTimer);
    settleTimer = 0;
    if (!useSpatialDeck) {
      window.scrollTo({ top: sceneMetric(index).top, behavior: "auto" });
    }

    // 动画最后一帧已接近 identity；立刻落位并解锁，避免连滑时卡一拍
    setActiveScene(index, { force: true });
    scenes[index]?.classList.add("is-settled");
    clearSpatialPaint();
    document.documentElement.classList.remove("is-snap-animating", "is-scrolling");
    snapLocked = false;
    snapTarget = -1;
    locked = false;
    scenes.forEach((scene) => scene.classList.remove("is-snap-source", "is-snap-target"));

    // 视频起播延后一帧，不和切幕最后几帧抢解码
    requestAnimationFrame(() => {
      if (current === index && !snapLocked) {
        syncSceneMedia(index, { sliding: false });
      }
    });
  }

  function cancelSpatialToCurrent(source, target, dir, fromProgress) {
    // 弹回当前幕：同样用单层 ease，终点再清
    const start = Math.max(0, Math.min(1, fromProgress));
    const duration = reducedMotion ? 0 : Math.max(180, Math.round(SPATIAL_DURATION * (0.4 + start * 0.5)));
    snapLocked = true;
    snapTarget = current;
    locked = true;
    document.documentElement.classList.add("is-snap-animating");

    if (duration <= 0 || start < 0.01) {
      clearSpatialPaint();
      setActiveScene(current, { force: true });
      scenes[current]?.classList.add("is-settled");
      syncSceneMedia(current, { sliding: false });
      snapLocked = false;
      snapTarget = -1;
      document.documentElement.classList.remove("is-snap-animating", "is-scrolling");
      locked = false;
      return;
    }

    let startedAt = 0;
    const step = (now) => {
      if (!startedAt) startedAt = now;
      const u = Math.min(1, (now - startedAt) / duration);
      const progress = start * (1 - spatialEase(u));
      paintSpatialFrame(source, target, dir, progress);
      if (u < 1) {
        snapFrame = requestAnimationFrame(step);
        return;
      }
      clearSpatialPaint();
      setActiveScene(current, { force: true });
      scenes[current]?.classList.add("is-settled");
      syncSceneMedia(current, { sliding: false });
      snapLocked = false;
      snapTarget = -1;
      document.documentElement.classList.remove("is-snap-animating", "is-scrolling");
      locked = false;
    };
    snapFrame = requestAnimationFrame(step);
  }

  /**
   * 从当前进度插值到 1（提交）或 0（取消）。
   * 注意：fromProgress 是「视觉进度」0→1，与 paint 公式一致；只在时间轴上做一次 ease。
   */
  function animateSpatialProgress(index, fromProgress, commit, dir) {
    stopSnapFrame();
    const source = scenes[current];
    const target = scenes[index];
    if (!source || !target) {
      clearSpatialPaint();
      snapLocked = false;
      snapTarget = -1;
      finishSlide();
      return false;
    }

    armSpatialPair(source, target, dir);

    if (!commit) {
      cancelSpatialToCurrent(source, target, dir, fromProgress);
      return true;
    }

    const start = Math.max(0, Math.min(1, fromProgress));
    const remain = 1 - start;
    // 剩余路程越短时长越短；带一点速度下限保证顺滑
    const duration = reducedMotion
      ? 0
      : Math.max(200, Math.round(SPATIAL_DURATION * (0.28 + remain * 0.72)));

    snapLocked = true;
    snapTarget = index;
    locked = true;
    document.documentElement.classList.add("is-snap-animating");
    paintSpatialFrame(source, target, dir, start);

    if (duration <= 0 || remain < 0.01) {
      completeSnap(index);
      return true;
    }

    let startedAt = 0;
    const step = (now) => {
      if (!startedAt) startedAt = now;
      const u = Math.min(1, (now - startedAt) / duration);
      // 单层 ease：视觉进度 = start + remain * ease(u)
      const progress = start + remain * spatialEase(u);
      paintSpatialFrame(source, target, dir, progress);

      if (u < 1) {
        snapFrame = requestAnimationFrame(step);
        return;
      }
      // 落到精确 1，再 complete（避免 0.999 与 identity 差一帧）
      paintSpatialFrame(source, target, dir, 1);
      completeSnap(index);
    };

    snapFrame = requestAnimationFrame(step);
    return true;
  }

  function animateSpatialToScene(index, { fromProgress = 0 } = {}) {
    stopSnapFrame();
    if (scrollFrame) cancelAnimationFrame(scrollFrame);
    scrollFrame = 0;
    window.clearTimeout(settleTimer);
    settleTimer = 0;

    const from = current;
    if (index === from) return false;
    const dir = index > from ? 1 : -1;
    const source = scenes[from];
    const target = scenes[index];
    if (!source || !target) return false;

    snapLocked = true;
    snapTarget = index;
    locked = true;
    resetSpotlight();
    markSnapScenes(index);
    armSpatialPair(source, target, dir);
    // 过渡中只暖机，不立刻 play，减少解码卡顿
    warmNeighborVideos(index);
    syncSceneMedia(index, { sliding: true });
    document.documentElement.classList.add("is-snap-animating");

    if (reducedMotion || SPATIAL_DURATION <= 0) {
      completeSnap(index);
      return true;
    }

    return animateSpatialProgress(index, fromProgress, true, dir);
  }

  function animateToScene(index) {
    if (useSpatialDeck) {
      return animateSpatialToScene(index);
    }

    stopSnapFrame();
    if (scrollFrame) cancelAnimationFrame(scrollFrame);
    scrollFrame = 0;
    window.clearTimeout(settleTimer);
    settleTimer = 0;

    const startY = window.scrollY || document.documentElement.scrollTop || 0;
    const targetY = sceneMetric(index).top;
    const distance = targetY - startY;

    snapLocked = true;
    snapTarget = index;
    locked = true;
    resetSpotlight();
    markSnapScenes(index);
    syncSceneMedia(index, { sliding: true });
    document.documentElement.classList.add("is-snap-animating");

    if (reducedMotion || Math.abs(distance) < 1) {
      completeSnap(index);
      return true;
    }

    let startedAt = 0;
    const step = (now) => {
      if (!startedAt) startedAt = now;
      const elapsed = now - startedAt;
      const progress = Math.min(1, elapsed / SNAP_DURATION);
      window.scrollTo({ top: startY + distance * snapProgress(progress), behavior: "auto" });

      if (progress < 1) {
        snapFrame = requestAnimationFrame(step);
        return;
      }
      completeSnap(index);
    };

    snapFrame = requestAnimationFrame(step);
    return true;
  }

  function goTo(next) {
    if (!ready || next < 0 || next >= total || next === snapTarget) return false;
    if (useSpatialDeck) {
      if (!snapLocked && next === current) return false;
      return animateToScene(next);
    }
    const pageTop = window.scrollY || document.documentElement.scrollTop || 0;
    if (!snapLocked && next === current && Math.abs(sceneMetric(next).top - pageTop) < 1) {
      return false;
    }
    return animateToScene(next);
  }

  function nextScene() {
    return goTo(current + 1);
  }

  function prevScene() {
    return goTo(current - 1);
  }

  function isInteractiveTarget(target) {
    if (!(target instanceof Element)) return false;
    return Boolean(
      target.closest(
        'a[href], button, input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]'
      )
    );
  }

  function bindSpatialGestures() {
    if (!useSpatialDeck) return;

    let touchStartY = 0;
    let touchStartX = 0;
    let touchStartT = 0;
    let tracking = false;
    let scrubbing = false;
    let scrubDir = 0;
    let scrubIndex = -1;
    let scrubProgress = 0;
    let lastTouchY = 0;
    let lastTouchT = 0;
    let velocityY = 0;
    let scrubPaintFrame = 0;
    let pendingScrubProgress = 0;
    let wheelGateUntil = 0;

    const endScrubSession = () => {
      tracking = false;
      scrubbing = false;
      scrubDir = 0;
      scrubIndex = -1;
      scrubProgress = 0;
      pendingScrubProgress = 0;
      if (scrubPaintFrame) {
        cancelAnimationFrame(scrubPaintFrame);
        scrubPaintFrame = 0;
      }
    };

    const flushScrubPaint = () => {
      scrubPaintFrame = 0;
      if (!scrubbing) return;
      const source = scenes[current];
      const target = scenes[scrubIndex];
      if (!source || !target) return;
      scrubProgress = pendingScrubProgress;
      // 跟手：直接线性进度，与结算公式同一套 paint，松手不跳
      paintSpatialFrame(source, target, scrubDir, Math.min(1, scrubProgress));
    };

    const queueScrubPaint = (progress) => {
      pendingScrubProgress = progress;
      if (scrubPaintFrame) return;
      scrubPaintFrame = requestAnimationFrame(flushScrubPaint);
    };

    const beginScrub = (dir) => {
      const index = current + dir;
      if (index < 0 || index >= total) return false;
      const source = scenes[current];
      const target = scenes[index];
      if (!source || !target) return false;

      scrubbing = true;
      scrubDir = dir;
      scrubIndex = index;
      scrubProgress = 0;
      pendingScrubProgress = 0;
      locked = true;
      resetSpotlight();
      markSnapScenes(index);
      armSpatialPair(source, target, dir);
      // 先 ensure 目标栈并暂停解码；邻幕 warm 延后一帧，避免首帧跟手卡顿
      syncSceneMedia(index, { sliding: true });
      document.documentElement.classList.add("is-snap-animating", "is-scrolling");
      paintSpatialFrame(source, target, dir, 0);
      window.setTimeout(() => {
        if (scrubbing && scrubIndex === index) warmNeighborVideos(index);
      }, 0);
      return true;
    };

    const onTouchStart = (event) => {
      if (!ready || snapLocked || event.touches.length !== 1) return;
      if (isInteractiveTarget(event.target)) return;
      const active = scenes[current];
      if (active && !active.classList.contains("is-spatial-source")) {
        active.style.removeProperty("transform");
        active.style.removeProperty("opacity");
      }
      tracking = true;
      scrubbing = false;
      scrubDir = 0;
      scrubIndex = -1;
      scrubProgress = 0;
      pendingScrubProgress = 0;
      velocityY = 0;
      touchStartY = event.touches[0].clientY;
      touchStartX = event.touches[0].clientX;
      touchStartT = performance.now();
      lastTouchY = touchStartY;
      lastTouchT = touchStartT;
    };

    const onTouchMove = (event) => {
      if (!tracking || snapLocked) return;
      if (event.cancelable) event.preventDefault();
      const touch = event.touches[0];
      if (!touch) return;

      const now = performance.now();
      const dy = touch.clientY - touchStartY;
      const dx = touch.clientX - touchStartX;
      const frameDt = Math.max(8, now - lastTouchT);
      // 低通滤波速度，减少松手瞬间误判
      const instantVy = (touch.clientY - lastTouchY) / frameDt;
      velocityY = velocityY * 0.65 + instantVy * 0.35;
      lastTouchY = touch.clientY;
      lastTouchT = now;

      if (!scrubbing && Math.abs(dx) > Math.abs(dy) * 1.2 && Math.abs(dx) > 28) {
        tracking = false;
        return;
      }

      const intentDir = dy < 0 ? 1 : -1;
      if (!scrubbing) {
        if (Math.abs(dy) < 8) return;
        if ((intentDir > 0 && current >= total - 1) || (intentDir < 0 && current <= 0)) {
          // 边界橡皮筋也走 rAF，避免 touchmove 高频写 style
          const rubber = Math.min(1, Math.abs(dy) / (spatialScrubPx * 1.8));
          const scene = scenes[current];
          if (scene) {
            pendingScrubProgress = rubber;
            if (!scrubPaintFrame) {
              scrubPaintFrame = requestAnimationFrame(() => {
                scrubPaintFrame = 0;
                const r = pendingScrubProgress;
                const pull = (intentDir > 0 ? 1 : -1) * r * spatialVh * 0.03;
                scene.style.transform = `translate3d(0,${pull.toFixed(2)}px,0) scale(${(1 - r * 0.025).toFixed(4)})`;
                scene.style.opacity = String((1 - r * 0.06).toFixed(3));
              });
            }
          }
          return;
        }
        if (!beginScrub(intentDir)) return;
      }

      const signed = scrubDir > 0 ? -dy : dy;
      let raw = signed / spatialScrubPx;
      // 过冲阻尼，避免拉过头后猛弹
      if (raw < 0) raw = raw * 0.22;
      else if (raw > 1) raw = 1 + (raw - 1) * 0.12;
      queueScrubPaint(Math.max(0, Math.min(1.08, raw)));
    };

    const onTouchEnd = (event) => {
      if (!tracking && !scrubbing) return;

      // 先刷掉最后一帧跟手 paint，避免用过期 progress 结算
      if (scrubPaintFrame) {
        cancelAnimationFrame(scrubPaintFrame);
        scrubPaintFrame = 0;
        flushScrubPaint();
      }

      const touch = event.changedTouches[0];
      const endY = touch ? touch.clientY : lastTouchY;
      const dy = endY - touchStartY;
      const dx = (touch ? touch.clientX : touchStartX) - touchStartX;
      const dt = Math.max(16, performance.now() - touchStartT);
      const overallVy = dy / dt;

      if (!scrubbing) {
        const scene = scenes[current];
        if (scene) {
          scene.style.removeProperty("transform");
          scene.style.removeProperty("opacity");
        }
        tracking = false;

        if (snapLocked || !ready) return;
        if (Math.abs(dx) > Math.abs(dy) * 1.25 && Math.abs(dx) > 36) return;
        const distanceOk = Math.abs(dy) > 40;
        const flingOk = Math.abs(overallVy) > 0.35 || Math.abs(velocityY) > 0.45;
        if (!distanceOk && !flingOk) return;
        if (dy < 0 || overallVy < -0.35 || velocityY < -0.45) goTo(current + 1);
        else goTo(current - 1);
        return;
      }

      const progress = Math.min(1, Math.max(0, scrubProgress));
      const flingCommit =
        (scrubDir > 0 && (overallVy < -0.32 || velocityY < -0.4)) ||
        (scrubDir < 0 && (overallVy > 0.32 || velocityY > 0.4));
      // 阈值略低，跟手到一半就倾向提交，减少「拖很远还弹回」的挫败感
      const commit = progress >= 0.22 || flingCommit;
      const index = scrubIndex;
      const dir = scrubDir;
      endScrubSession();

      if (commit && index >= 0) {
        animateSpatialProgress(index, progress, true, dir);
      } else if (index >= 0) {
        animateSpatialProgress(index, progress, false, dir);
      } else {
        clearSpatialPaint();
        document.documentElement.classList.remove("is-snap-animating", "is-scrolling");
        finishSlide();
      }
    };

    const onTouchCancel = () => {
      if (scrubPaintFrame) {
        cancelAnimationFrame(scrubPaintFrame);
        scrubPaintFrame = 0;
      }
      if (scrubbing && scrubIndex >= 0) {
        const index = scrubIndex;
        const dir = scrubDir;
        const progress = scrubProgress;
        endScrubSession();
        animateSpatialProgress(index, progress, false, dir);
        return;
      }
      const scene = scenes[current];
      if (scene) {
        scene.style.removeProperty("transform");
        scene.style.removeProperty("opacity");
      }
      endScrubSession();
      document.documentElement.classList.remove("is-snap-animating", "is-scrolling");
      finishSlide();
    };

    const onWheel = (event) => {
      if (!ready) return;
      if (snapLocked || scrubbing || performance.now() < wheelGateUntil) {
        if (event.cancelable) event.preventDefault();
        return;
      }
      const dy = event.deltaY;
      if (Math.abs(dy) < 8) return;
      if (event.cancelable) event.preventDefault();
      wheelGateUntil = performance.now() + SPATIAL_DURATION + 80;
      if (dy > 0) goTo(current + 1);
      else goTo(current - 1);
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    window.addEventListener("touchcancel", onTouchCancel, { passive: true });
    window.addEventListener("wheel", onWheel, { passive: false });
  }

  function bindInteraction() {
    if (!useSpatialDeck) {
      window.addEventListener("scroll", handleStageScroll, { passive: true });
      window.addEventListener("scrollend", settleStageScroll, { passive: true });
    }
    window.addEventListener("resize", queueSceneMeasurement, { passive: true });
    // Mobile browser chrome / orientation changes often fire on visualViewport, not window.resize.
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", queueSceneMeasurement, { passive: true });
    }
    if (document.fonts?.ready) {
      document.fonts.ready.then(queueSceneMeasurement).catch(() => {});
    }

    bindSpatialGestures();

    window.addEventListener("keydown", (event) => {
      if (
        !ready ||
        event.defaultPrevented ||
        event.isComposing ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        isInteractiveTarget(event.target)
      ) {
        return;
      }

      const key = event.key;
      let direction = 0;
      if (key === "ArrowDown") {
        direction = 1;
      } else if (key === "ArrowUp") {
        direction = -1;
      } else if (["PageDown", "PageUp", " ", "Spacebar"].includes(key)) {
        direction = key === "PageUp" || ((key === " " || key === "Spacebar") && event.shiftKey) ? -1 : 1;
      } else if (key === "Home") {
        event.preventDefault();
        goTo(0);
        return;
      } else if (key === "End") {
        event.preventDefault();
        goTo(total - 1);
        return;
      }

      if (!direction) return;
      event.preventDefault();
      if (snapLocked) return;
      goTo((useSpatialDeck ? current : nearestSceneIndex()) + direction);
    });

    document.querySelectorAll("[data-goto]").forEach((el) => {
      el.addEventListener("click", (event) => {
        if (!ready) {
          event.preventDefault();
          return;
        }
        const index = Number(el.getAttribute("data-goto"));
        if (Number.isNaN(index)) return;
        if (el.tagName === "A") event.preventDefault();
        goTo(index);
      });
    });

    // Login CTAs use plain /login links; native navigation enters the workbench auth flow.

    document.addEventListener("visibilitychange", () => {
      if (!ready) return;
      if (document.hidden) pauseAllVideos();
      else if (!locked) syncSceneMedia(current, { sliding: false });
    });
  }

  function forceEnterShell() {
    document.body.classList.remove("is-booting", "is-tearing");
    document.body.classList.add("is-ready");
    ready = true;
    if (bootScreen) {
      bootScreen.classList.add("is-done");
      bootScreen.setAttribute("aria-busy", "false");
      try {
        bootScreen.remove();
      } catch {
        /* ignore */
      }
    }
  }

  async function startExperience() {
    measureSceneMetrics();
    window.scrollTo({ top: 0, behavior: "auto" });
    markNeighbors(0);
    setTheme(0);
    updateChrome(0);
    scenes[0]?.classList.add("is-settled");

    await playSplashThenReady();
    if (ready) return;
    ready = true;
    try {
      playHeroIntro();
    } catch (err) {
      console.warn("[landing] hero intro", err);
    }
    try {
      bindParallax();
    } catch (err) {
      console.warn("[landing] parallax", err);
    }
    prefetchLazyImages();

    requestAnimationFrame(() => {
      try {
        syncSceneMedia(0, { sliding: false });
      } catch (err) {
        console.warn("[landing] media", err);
      }
    });
  }

  /* ───────── Boot sequence ───────── */

  bindInteraction();
  // 尽早建双路栈（src 由 data-video-src 注入），boot 与 watchdog 共用
  initVideoStacks();

  (async () => {
    const started = performance.now();
    // 最多 4 秒必须进站
    const bootWatchdog = window.setTimeout(() => {
      console.warn("[landing] boot watchdog — force enter");
      try {
        window.scrollTo({ top: 0, behavior: "auto" });
        markNeighbors(0);
        setTheme(0);
        updateChrome(0);
        scenes[0]?.classList.add("is-settled");
        forceEnterShell();
        playHeroIntro();
        bindParallax();
        prefetchLazyImages();
        initVideoStacks();
        syncSceneMedia(0, { sliding: false });
      } catch (err) {
        console.warn("[landing] force enter hooks", err);
        forceEnterShell();
      }
    }, 4000);

    try {
      await withTimeout(preloadAllAssets(), 3500, null);
    } catch (err) {
      console.warn("[landing] preload incomplete, enter anyway", err);
    }

    if (ready) {
      // 已被 watchdog 强制进入
      window.clearTimeout(bootWatchdog);
      return;
    }

    const elapsed = performance.now() - started;
    if (!reducedMotion && elapsed < 200) {
      await wait(200 - elapsed);
    }

    setBootProgress(1, "翻开序章…");
    try {
      await startExperience();
    } catch (err) {
      console.warn("[landing] startExperience failed, force ready", err);
      forceEnterShell();
    } finally {
      window.clearTimeout(bootWatchdog);
    }
  })();
})();
