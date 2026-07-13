import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useMinderTheme, useAgentActivity } from "minder-ui-sdk";

/**
 * Pilo — the module_template mascot. It reacts to the agent driving the UI:
 * `useAgentActivity()` gives it the latest UI intent (navigate/fill/focus/
 * confirm/submit), and a `mt-mascot` window CustomEvent lets panels nudge its
 * mood on local actions (create/delete/restock). Pure eye-candy — it never
 * touches state.
 */

type Mood = "idle" | "walk" | "type" | "point" | "ask" | "celebrate" | "nervous" | "happy";

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
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const say = (m: Mood, t: string | null, hold = 3000) => {
    setMood(m);
    setText(t);
    clearTimeout(timer.current);
    if (m !== "idle") {
      timer.current = setTimeout(() => {
        setMood("idle");
        setText(null);
      }, hold);
    }
  };

  // React to agent UI intents.
  useEffect(() => {
    if (!activity) return;
    const i = activity.intent;
    if (i.intent === "navigate") say("walk", "Đi tới Products…", 1800);
    else if (i.intent === "fill") say("type", "Đang điền form ✍️");
    else if (i.intent === "focus") say("point", `Tới lượt bạn: ${i.field} 👉`, 5000);
    else if (i.intent === "request_confirm") say("ask", i.summary || "Xác nhận nhé? 🤔", 8000);
    else if (i.intent === "submit") say("celebrate", "Xong! 🎉");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity?.tick]);

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
    <div style={{ position: "fixed", left: 20, bottom: 20, zIndex: 9998, pointerEvents: "none", width: 120 }}>
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

      <motion.div animate={mood} variants={{}} style={{ width: 90, height: 96, position: "relative" }}>
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
    </div>
  );
}
