import { motion } from "motion/react";
import { useMinderTheme } from "./embinder";

export default function ShowcaseBlock(props: any) {
  const { kind = 'block', topic = 'demo', results = [], pct, done, bridge } = props;
  const { tokens } = useMinderTheme();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      style={{
        background: tokens.surface,
        border: `1px solid ${tokens.border}`,
        borderRadius: 8,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ fontSize: 12, fontFamily: "monospace", color: tokens.textMuted }}>
        module_template · {kind}
      </div>
      {typeof pct === 'number' ? (
        <div>
          <div style={{ fontSize: 14, color: tokens.text, marginBottom: 4 }}>
            {done ? 'Done' : `Working… ${pct}%`}
          </div>
          <div style={{ height: 8, borderRadius: 4, background: tokens.surfaceAlt, overflow: "hidden" }}>
            <motion.div
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              style={{ height: "100%", background: tokens.secondary, borderRadius: 4, transformOrigin: "left" }}
            />
          </div>
        </div>
      ) : (
        <>
          <div style={{ fontSize: 14, color: tokens.text }}>
            Results for <b>{topic}</b>:
          </div>
          <ul style={{ fontSize: 14, color: tokens.text, listStyle: "disc", paddingLeft: 20, margin: 0 }}>
            {results.map((r: any, i: number) => (
              <li key={i}>
                {r.title}{" "}
                <span style={{ color: tokens.textMuted }}>({r.score})</span>
              </li>
            ))}
          </ul>
          <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.95 }}
              style={{
                padding: "4px 8px", borderRadius: 4, background: tokens.surfaceAlt,
                border: `1px solid ${tokens.border}`, color: tokens.text,
                fontSize: 12, cursor: "pointer",
              }}
              onClick={() => bridge?.toast?.('Hello from ShowcaseBlock', 'success')}
            >
              bridge.toast
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.95 }}
              style={{
                padding: "4px 8px", borderRadius: 4, background: tokens.surfaceAlt,
                border: `1px solid ${tokens.border}`, color: tokens.text,
                fontSize: 12, cursor: "pointer",
              }}
              onClick={() => bridge?.sendMessage?.(`Tell me more about ${topic}`)}
            >
              bridge.sendMessage
            </motion.button>
          </div>
        </>
      )}
    </motion.div>
  );
}
