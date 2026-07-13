import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useMotionValue, animate, useDragControls } from "motion/react";
import { useMinderTheme, useAgentActivity, type UiIntent } from "minder-ui-sdk";

/**
 * Pilo — the module_template mascot. It reacts to the agent driving the UI:
 * `useAgentActivity()` gives it the latest UI intent (navigate/fill/focus/
 * confirm/submit), and a `mt-mascot` window CustomEvent lets panels nudge its
 * mood on local actions (create/delete/restock). Pure eye-candy — it never
 * touches state.
 *
 * Beyond changing mood, Pilo physically WALKS to the on-screen element an intent
 * targets: `focus` → the `[data-agent-field]`, `fill`/`request_confirm` → the
 * `[data-agent-form]`, `submit` → the `[data-agent-control="submit"]`,
 * `highlight` → the `[data-agent-control]`. It springs beside the element,
 * points at it, then strolls back to its home corner when idle.
 */

type Mood = "idle" | "walk" | "type" | "point" | "ask" | "celebrate" | "nervous" | "happy";

/** Mascot bounding box (px) — body sits at the bottom, speech bubble above it. */
const BOX_W = 130;
const BOX_H = 210;
const GAP = 8;

interface Pos {
  x: number;
  y: number;
  /** Which way the body faces so it points TOWARD the target. */
  facing: "left" | "right";
}

/** Home corner (bottom-left), recomputed from the current viewport. */
function homePos(): Pos {
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  return { x: 20, y: vh - BOX_H - 20, facing: "right" };
}

/** The DOM element an intent points at, via the `data-agent-*` marker convention. */
function targetFor(intent: UiIntent): Element | null {
  const q = (sel: string) => document.querySelector(sel);
  switch (intent.intent) {
    case "focus":
      return q(`[data-agent-field="${CSS.escape(intent.field)}"]`);
    case "fill":
      return q(`[data-agent-form="${CSS.escape(intent.form)}"]`);
    case "request_confirm":
      return (
        q(`[data-agent-form="${CSS.escape(intent.target)}"]`) ??
        q(`[data-agent-control="${CSS.escape(intent.target)}"]`)
      );
    case "highlight":
      return q(`[data-agent-control="${CSS.escape(intent.control)}"]`);
    case "submit":
      return q(`[data-agent-control="submit"]`) ?? q(`[data-agent-form="${CSS.escape(intent.form)}"]`);
    default: // navigate → no specific element
      return null;
  }
}

/** Place the mascot beside an element: prefer its left, fall back to its right. */
function poseBeside(el: Element): Pos {
  const r = el.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let facing: "left" | "right" = "right";
  let x = r.left - BOX_W - GAP; // stand to the LEFT, point right at it
  if (x < GAP) {
    x = r.right + GAP; // no room → stand to the RIGHT, point left
    facing = "left";
  }
  x = Math.max(GAP, Math.min(x, vw - BOX_W - GAP));

  // Anchor the body (bottom of the box) roughly at the element's vertical center.
  let y = r.top + r.height / 2 - BOX_H + 44;
  y = Math.max(GAP, Math.min(y, vh - BOX_H - GAP));

  return { x, y, facing };
}

/** Fire a mascot mood from anywhere in the module frontend. */
export function mascotSay(mood: Mood, text?: string | null, hold = 2600) {
  window.dispatchEvent(new CustomEvent("mt-mascot", { detail: { mood, text, hold } }));
}

const BODY: Record<Mood, object> = {
  idle: { y: [0, -6, 0], rotate: 0, transition: { duration: 2.6, repeat: Infinity, ease: "easeInOut" } },
  walk: { x: [0, 7, -7, 0], rotate: [0, 5, -5, 0], transition: { duration: 0.6, repeat: Infinity } },
  type: { y: [0, -3, 0], transition: { duration: 0.24, repeat: Infinity } },
  point: { rotate: 9, x: 5, transition: { duration: 0.3 } },
  ask: { rotate: [0, -6, 6, 0], transition: { duration: 1.3, repeat: Infinity } },
  celebrate: { y: [0, -24, 0], rotate: [0, -14, 14, 0], transition: { duration: 0.6, repeat: 2 } },
  nervous: { x: [0, -4, 4, -4, 4, 0], transition: { duration: 0.4, repeat: Infinity } },
  happy: { y: [0, -12, 0], transition: { duration: 0.42, repeat: 1 } },
};

const ARM: Record<Mood, object> = {
  point: { rotate: -55, x: 2 },
  type: { rotate: [-10, -30, -10], transition: { duration: 0.24, repeat: Infinity } },
  celebrate: { rotate: [-20, -120, -20], transition: { duration: 0.5, repeat: 2 } },
  idle: { rotate: -8 },
  walk: { rotate: [-8, -20, -8], transition: { duration: 0.6, repeat: Infinity } },
  ask: { rotate: -8 },
  nervous: { rotate: -8 },
  happy: { rotate: [-8, -70, -8], transition: { duration: 0.42, repeat: 1 } },
};

export default function Mascot() {
  const { tokens } = useMinderTheme();
  const activity = useAgentActivity();
  const [mood, setMood] = useState<Mood>("idle");
  const [text, setText] = useState<string | null>(null);
  const [blink, setBlink] = useState(false);
  const [pos, setPos] = useState<Pos>(homePos);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  /** Element the mascot is currently escorting (for scroll/resize re-anchoring). */
  const tracked = useRef<Element | null>(null);

  // Live x/y the body is actually rendered at. Both the agent-driven `pos` spring
  // AND the user's drag write these same values, so hand-dragging and autonomous
  // movement never fight. `true` while a finger/pointer is dragging Pilo around.
  const initial = homePos();
  const mx = useMotionValue(initial.x);
  const my = useMotionValue(initial.y);
  const [dragging, setDragging] = useState(false);
  // Drag is started manually from the robot body (not the whole 130×210 box) so
  // the transparent speech-bubble area above it never intercepts clicks.
  const dragControls = useDragControls();

  // Whenever the commanded position changes (intent walk / home / wander), spring
  // the live values toward it — unless the user is currently dragging.
  useEffect(() => {
    if (dragging) return;
    const a = animate(mx, pos.x, { type: "spring", stiffness: 130, damping: 18, mass: 0.7 });
    const b = animate(my, pos.y, { type: "spring", stiffness: 130, damping: 18, mass: 0.7 });
    return () => {
      a.stop();
      b.stop();
    };
  }, [pos.x, pos.y, dragging, mx, my]);

  const say = (m: Mood, t: string | null, hold = 3000) => {
    setMood(m);
    setText(t);
    clearTimeout(timer.current);
    if (m !== "idle") {
      timer.current = setTimeout(() => {
        setMood("idle");
        setText(null);
        tracked.current = null; // stop escorting → stroll home
        setPos(homePos());
      }, hold);
    }
  };

  /** Walk to whatever element an intent points at (retrying once for late DOM). */
  const walkTo = useCallback((intent: UiIntent) => {
    const settle = (attempt: number) => {
      const el = targetFor(intent);
      if (el) {
        tracked.current = el;
        setPos(poseBeside(el));
      } else if (attempt < 1) {
        // Tab may have just switched (navigate→fill); let it mount, then retry.
        setTimeout(() => settle(attempt + 1), 140);
      } else {
        tracked.current = null;
        setPos(homePos());
      }
    };
    settle(0);
  }, []);

  // React to agent UI intents: change mood AND travel to the targeted element.
  useEffect(() => {
    if (!activity) return;
    const i = activity.intent;
    if (i.intent === "navigate") say("walk", "Đi tới Products…", 1800);
    else if (i.intent === "fill") say("type", "Đang điền form ✍️");
    else if (i.intent === "focus") say("point", `Tới lượt bạn: ${i.field} 👉`, 5000);
    else if (i.intent === "request_confirm") say("ask", i.summary || "Xác nhận nhé? 🤔", 8000);
    else if (i.intent === "submit") say("celebrate", "Xong! 🎉");
    else if (i.intent === "highlight") say("point", "Nhìn đây nè 👀", 5000);
    walkTo(i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity?.tick]);

  // Keep the mascot pinned beside its target as the page scrolls / resizes.
  // When it's NOT escorting an element we leave it wherever it wandered/was
  // dropped — only clamp it back inside the viewport on resize.
  useEffect(() => {
    const reanchor = () => {
      const el = tracked.current;
      if (el && el.isConnected) {
        setPos(poseBeside(el));
      } else {
        const maxX = Math.max(GAP, window.innerWidth - BOX_W - GAP);
        const maxY = Math.max(GAP, window.innerHeight - BOX_H - GAP);
        if (mx.get() > maxX) animate(mx, maxX);
        if (my.get() > maxY) animate(my, maxY);
      }
    };
    window.addEventListener("scroll", reanchor, true);
    window.addEventListener("resize", reanchor);
    return () => {
      window.removeEventListener("scroll", reanchor, true);
      window.removeEventListener("resize", reanchor);
    };
  }, [mx, my]);

  // Autonomous wandering: when Pilo is idle (no agent intent to escort) and not
  // being dragged, it strolls to a random spot every few seconds. Pauses the
  // moment an intent arrives (mood leaves "idle") or the user grabs it.
  useEffect(() => {
    if (mood !== "idle" || dragging) return;
    let alive = true;
    let hop: ReturnType<typeof setTimeout>;
    const roam = () => {
      if (!alive) return;
      const maxX = Math.max(GAP, window.innerWidth - BOX_W - GAP);
      const maxY = Math.max(GAP, window.innerHeight - BOX_H - GAP);
      const nx = GAP + Math.random() * (maxX - GAP);
      const ny = GAP + Math.random() * (maxY - GAP);
      setPos((prev) => ({ x: nx, y: ny, facing: nx >= prev.x ? "right" : "left" }));
      hop = setTimeout(roam, 3500 + Math.random() * 3500);
    };
    // Settle first so it doesn't dart off the instant you drop it or it goes idle.
    hop = setTimeout(roam, 2500);
    return () => {
      alive = false;
      clearTimeout(hop);
    };
  }, [mood, dragging]);

  // React to panel-level nudges.
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent).detail || {};
      say(d.mood || "happy", d.text ?? null, d.hold ?? 2600);
    };
    window.addEventListener("mt-mascot", h);
    return () => window.removeEventListener("mt-mascot", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Idle blink.
  useEffect(() => {
    const t = setInterval(() => {
      setBlink(true);
      setTimeout(() => setBlink(false), 140);
    }, 3600);
    return () => clearInterval(t);
  }, []);

  const c1 = tokens.primary;
  const c2 = tokens.info;
  const eyeLook = mood === "point" ? 3 : mood === "ask" ? -2 : 0;

  return (
    <motion.div
      drag
      dragListener={false}
      dragControls={dragControls}
      dragMomentum={false}
      dragElastic={0.12}
      dragConstraints={{
        left: GAP,
        top: GAP,
        right: Math.max(GAP, (typeof window === "undefined" ? 1280 : window.innerWidth) - BOX_W - GAP),
        bottom: Math.max(GAP, (typeof window === "undefined" ? 800 : window.innerHeight) - BOX_H - GAP),
      }}
      onDragStart={() => {
        tracked.current = null; // stop escorting any element while hand-held
        setDragging(true);
      }}
      onDragEnd={() => {
        // Commit the dropped spot as the new commanded position so the follow
        // spring doesn't yank Pilo back to where an old intent left it.
        setPos((prev) => ({ ...prev, x: mx.get(), y: my.get() }));
        setDragging(false);
      }}
      style={{
        x: mx,
        y: my,
        position: "fixed",
        left: 0,
        top: 0,
        zIndex: 9998,
        pointerEvents: "none",
        width: BOX_W,
        height: BOX_H,
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        alignItems: "flex-start",
      }}
    >
      <AnimatePresence>
        {text && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.9 }}
            style={{
              marginBottom: 8,
              background: tokens.surface,
              border: `1px solid ${tokens.border}`,
              boxShadow: tokens.cardShadow,
              borderRadius: 12,
              padding: "8px 12px",
              color: tokens.text,
              fontSize: 12.5,
              maxWidth: 180,
              lineHeight: 1.35,
            }}
          >
            {text}
            <div style={{ position: "absolute", left: 34, width: 12, height: 12, background: tokens.surface, borderRight: `1px solid ${tokens.border}`, borderBottom: `1px solid ${tokens.border}`, transform: "rotate(45deg)", marginTop: 2 }} />
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        animate={mood}
        variants={{}}
        onPointerDown={(e) => dragControls.start(e)}
        title="Kéo tôi đi chơi! 🖐️"
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 1.12 }}
        style={{
          width: 90,
          height: 96,
          position: "relative",
          pointerEvents: "auto",
          cursor: dragging ? "grabbing" : "grab",
          touchAction: "none",
          scaleX: pos.facing === "left" ? -1 : 1,
        }}
      >
        <motion.div animate={BODY[mood]} style={{ width: "100%", height: "100%" }}>
          {/* confetti on celebrate */}
          <AnimatePresence>
            {mood === "celebrate" &&
              [0, 1, 2, 3, 4].map((n) => (
                <motion.div
                  key={n}
                  initial={{ opacity: 1, x: 45, y: 30, scale: 0.6 }}
                  animate={{ opacity: 0, x: 45 + (n - 2) * 26, y: -10 - n * 6, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.7 }}
                  style={{ position: "absolute", width: 7, height: 7, borderRadius: 2, background: tokens.chart[n % tokens.chart.length] }}
                />
              ))}
          </AnimatePresence>

          <svg viewBox="0 0 90 96" width="90" height="96">
            <defs>
              <linearGradient id="pilo-body" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor={c1} />
                <stop offset="1" stopColor={c2} />
              </linearGradient>
            </defs>
            {/* antenna */}
            <line x1="45" y1="16" x2="45" y2="4" stroke={c2} strokeWidth="3" strokeLinecap="round" />
            <circle cx="45" cy="4" r="4" fill={c2} />
            {/* shadow */}
            <ellipse cx="45" cy="90" rx="24" ry="5" fill="#000" opacity="0.18" />
            {/* left arm */}
            <motion.rect animate={ARM[mood]} x="12" y="46" width="9" height="24" rx="4.5" fill={c1} style={{ transformBox: "fill-box", transformOrigin: "center top" }} />
            {/* right arm (the pointer) */}
            <motion.rect animate={ARM[mood]} x="69" y="46" width="9" height="24" rx="4.5" fill={c1} style={{ transformBox: "fill-box", transformOrigin: "center top" }} />
            {/* body */}
            <rect x="18" y="18" width="54" height="60" rx="20" fill="url(#pilo-body)" />
            {/* face plate */}
            <rect x="26" y="30" width="38" height="26" rx="13" fill={tokens.surfaceAlt} />
            {/* eyes */}
            <g>
              <ellipse cx={38 + eyeLook} cy="43" rx="4.2" ry={blink ? 0.8 : 4.6} fill={tokens.text} />
              <ellipse cx={52 + eyeLook} cy="43" rx="4.2" ry={blink ? 0.8 : 4.6} fill={tokens.text} />
            </g>
            {/* mouth */}
            {mood === "celebrate" || mood === "happy" ? (
              <path d="M40 62 Q45 68 50 62" stroke={tokens.text} strokeWidth="2.4" fill="none" strokeLinecap="round" />
            ) : mood === "nervous" ? (
              <path d="M40 65 Q45 60 50 65" stroke={tokens.text} strokeWidth="2.4" fill="none" strokeLinecap="round" />
            ) : (
              <line x1="41" y1="63" x2="49" y2="63" stroke={tokens.text} strokeWidth="2.4" strokeLinecap="round" />
            )}
            {/* feet */}
            <rect x="30" y="78" width="12" height="8" rx="4" fill={c1} />
            <rect x="48" y="78" width="12" height="8" rx="4" fill={c1} />
          </svg>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
