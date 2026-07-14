import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useMotionValue, animate, useDragControls } from "motion/react";
import { useMinderTheme, useAgentActivity, useQuickChat } from "minder-ui-sdk";
import logoUrl from "./logo.png";

/**
 * Minder — the module_template mascot. It reacts to the agent driving the UI:
 * `useAgentActivity()` gives it the latest UI intent (navigate/fill/focus/
 * confirm/submit), and a `mt-mascot` window CustomEvent lets panels nudge its
 * mood on local actions (create/delete/restock). Pure eye-candy — it never
 * touches state.
 *
 * It roams the RIGHT portion of the screen (autonomous wandering + draggable),
 * anchored near the bottom-right corner, and never strays left over the content.
 * Pointing at the exact on-screen element an intent targets is the ghost
 * cursor's job (AgentPresence), so the two never fight over position.
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

/** The roaming pen: Minder lives in the RIGHT portion of the viewport and never
 * strays into the left where the content/chat sits. */
function rightBounds() {
  const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const maxX = Math.max(GAP, vw - BOX_W - GAP);
  const minX = Math.min(maxX, Math.max(GAP, Math.round(vw * 0.62))); // right ~38%
  const maxY = Math.max(GAP, vh - BOX_H - GAP);
  return { minX, maxX, minY: GAP, maxY };
}

/** Home corner (bottom-right), recomputed from the current viewport. */
function homePos(): Pos {
  const { maxX, maxY } = rightBounds();
  return { x: maxX - 12, y: maxY, facing: "left" };
}

/** Fire a mascot mood from anywhere in the module frontend. */
export function mascotSay(mood: Mood, text?: string | null, hold = 2600) {
  window.dispatchEvent(new CustomEvent("mt-mascot", { detail: { mood, text, hold } }));
}

/**
 * Break an agent reply into a few short speech-bubble-sized chunks so Minder can
 * "pop" them one at a time on an interval instead of dumping a wall of text.
 * Splits on sentence enders, regroups to ~120 chars, and caps the count.
 */
function chunkReply(s: string): string[] {
  const clean = (s || "").replace(/\s+/g, " ").trim();
  if (!clean) return [];
  const parts = clean.match(/[^.!?…]+[.!?…]*/g) ?? [clean];
  const chunks: string[] = [];
  let cur = "";
  for (const p of parts) {
    const seg = p.trim();
    if (!seg) continue;
    if (cur && (cur + " " + seg).length > 120) {
      chunks.push(cur);
      cur = seg;
    } else {
      cur = cur ? `${cur} ${seg}` : seg;
    }
  }
  if (cur) chunks.push(cur);
  return chunks.slice(0, 6);
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

  // Live x/y the body is rendered at. Both the autonomous-wander `pos` spring AND
  // the user's drag write these same values, so they never fight. `dragging` is
  // true while a finger/pointer is moving Minder around.
  const initial = homePos();
  const mx = useMotionValue(initial.x);
  const my = useMotionValue(initial.y);
  const [dragging, setDragging] = useState(false);
  const dragControls = useDragControls();

  // Quick-chat: tap Minder → a little input opens; on send the question goes to the
  // host's real Minder agent (via the SDK bridge) and the answer pops back as
  // speech bubbles. `downAt` tells a tap (open chat) from a drag (move).
  const chat = useQuickChat();
  const [chatOpen, setChatOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [inputFocused, setInputFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const downAt = useRef<{ x: number; y: number } | null>(null);

  // Spring the live values toward the commanded position (wander target / home)
  // whenever it changes — unless the user is currently dragging.
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
      }, hold);
    }
  };

  // React to agent UI intents: emote in place. Pointing at the targeted element
  // is the ghost cursor's job (AgentPresence) — the mascot stays in its corner.
  useEffect(() => {
    if (!activity) return;
    const i = activity.intent;
    if (i.intent === "navigate") say("walk", "Đi tới Products…", 1800);
    else if (i.intent === "fill") say("type", "Đang điền form ✍️");
    else if (i.intent === "focus") say("point", `Tới lượt bạn: ${i.field} 👉`, 5000);
    else if (i.intent === "request_confirm") say("ask", i.summary || "Xác nhận nhé? 🤔", 8000);
    else if (i.intent === "submit") say("celebrate", "Xong! 🎉");
    else if (i.intent === "highlight") say("point", "Nhìn đây nè 👀", 5000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity?.tick]);

  // Keep the mascot pinned to its home corner as the viewport resizes.
  useEffect(() => {
    const reanchor = () => setPos(homePos());
    window.addEventListener("resize", reanchor);
    return () => window.removeEventListener("resize", reanchor);
  }, []);

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

  // Autofocus the quick-chat input as it opens.
  useEffect(() => {
    if (chatOpen) inputRef.current?.focus();
  }, [chatOpen]);

  // Show a live "thinking / typing" bubble while the agent works, and an error
  // bubble if the ask fails. The finished answer is handled separately below.
  useEffect(() => {
    clearTimeout(timer.current);
    if (chat.phase === "thinking") {
      setMood("ask");
      setText("Đang suy nghĩ… 💭");
    } else if (chat.phase === "streaming") {
      setMood("type");
      setText("Đang trả lời…");
    } else if (chat.phase === "error") {
      setMood("nervous");
      setText(chat.text || "Ối, có lỗi rồi 😖");
      timer.current = setTimeout(() => {
        setText(null);
        setMood("idle");
        chat.reset();
      }, 3200);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.phase]);

  // When the answer is ready, reveal it one bubble at a time on an interval —
  // Minder "chats back" instead of dumping the whole reply at once.
  useEffect(() => {
    if (chat.phase !== "done") return;
    const chunks = chunkReply(chat.text);
    if (chunks.length === 0) {
      setText(null);
      setMood("idle");
      chat.reset();
      return;
    }
    clearTimeout(timer.current);
    let i = 0;
    let t: ReturnType<typeof setTimeout>;
    const pop = () => {
      const last = i === chunks.length - 1;
      setText(chunks[i]);
      setMood(last ? "happy" : "type");
      i += 1;
      if (!last) {
        t = setTimeout(pop, 1700);
      } else {
        t = setTimeout(() => {
          setText(null);
          setMood("idle");
          chat.reset(); // back to idle → wandering resumes
        }, 3600);
      }
    };
    t = setTimeout(pop, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.phase]);

  const c1 = tokens.primary;
  const c2 = tokens.info;
  const eyeLook = mood === "point" ? 3 : mood === "ask" ? -2 : 0;

  return (
    <motion.div
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
      {/* Quick-chat input — reuses the composer feel (surface + border + focus
          ring) in a compact bubble anchored above Minder. */}
      <AnimatePresence>
        {chatOpen && (
          <motion.form
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.95 }}
            onSubmit={(e) => {
              e.preventDefault();
              const q = draft.trim();
              if (!q) return;
              chat.ask(q);
              setDraft("");
              setChatOpen(false);
            }}
            // Don't let a pointerdown inside the input start a mascot drag.
            onPointerDown={(e) => e.stopPropagation()}
            style={{
              pointerEvents: "auto",
              marginBottom: 8,
              display: "flex",
              alignItems: "center",
              gap: 6,
              width: 232,
              background: tokens.surface,
              // Soft brand-tinted focus ring instead of the harsh global
              // :focus-visible outline that leaks in from the host shell.
              border: `1px solid ${inputFocused ? tokens.primary : tokens.border}`,
              boxShadow: inputFocused
                ? `${tokens.cardShadow}, 0 0 0 3px ${tokens.primary}29`
                : tokens.cardShadow,
              borderRadius: 14,
              padding: "6px 6px 6px 12px",
              transition:
                "border-color 160ms ease, box-shadow 160ms ease",
            }}
          >
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setChatOpen(false);
              }}
              onFocus={() => setInputFocused(true)}
              onBlur={() => setInputFocused(false)}
              placeholder="Hỏi Minder bất cứ điều gì…"
              style={{
                flex: 1,
                minWidth: 0,
                border: "none",
                outline: "none",
                // Inline wins over the host's global :focus-visible rule, so
                // the container owns the focus treatment — not a stray outline.
                boxShadow: "none",
                background: "transparent",
                color: tokens.text,
                fontSize: 12.5,
              }}
            />
            <button
              type="submit"
              aria-label="Gửi"
              disabled={!draft.trim()}
              style={{
                flex: "0 0 auto",
                width: 26,
                height: 26,
                display: "grid",
                placeItems: "center",
                borderRadius: 999,
                border: "none",
                cursor: draft.trim() ? "pointer" : "default",
                opacity: draft.trim() ? 1 : 0.5,
                background: `linear-gradient(135deg, ${tokens.primary}, ${tokens.info})`,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </motion.form>
        )}
      </AnimatePresence>

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
        onClick={() => setChatOpen((v) => !v)}
        title="Bấm để chat với Minder"
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 1.12 }}
        style={{
          width: 90,
          height: 96,
          position: "relative",
          pointerEvents: "auto",
          cursor: "pointer",
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

          <img
            src={logoUrl}
            alt="mascot"
            draggable={false}
            style={{
              width: 84,
              height: 84,
              margin: "6px 3px",
              borderRadius: "50%",
              objectFit: "cover",
              boxShadow: `0 6px 18px rgba(0,0,0,0.28)`,
              border: `2px solid ${tokens.surface}`,
              userSelect: "none",
              display: "block",
            }}
          />
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
