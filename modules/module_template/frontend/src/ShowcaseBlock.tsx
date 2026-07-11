import { motion } from "motion/react";

export default function ShowcaseBlock(props: any) {
  const { kind = 'block', topic = 'demo', results = [], pct, done, bridge } = props;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="bg-bg-000 border border-border-300/15 rounded-lg p-4 space-y-2"
    >
      <div className="text-xs font-mono text-text-300">module_template · {kind}</div>
      {typeof pct === 'number' ? (
        <div>
          <div className="text-sm text-text-100 mb-1">{done ? 'Done' : `Working… ${pct}%`}</div>
          <div className="h-2 rounded bg-bg-200 overflow-hidden">
            <motion.div
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              className="h-full bg-accent-secondary-100"
              style={{ originX: 0 }}
            />
          </div>
        </div>
      ) : (
        <>
          <div className="text-sm text-text-100">Results for <b>{topic}</b>:</div>
          <ul className="text-sm text-text-200 list-disc pl-5">
            {results.map((r: any, i: number) => (
              <li key={i}>{r.title} <span className="text-text-400">({r.score})</span></li>
            ))}
          </ul>
          <div className="flex gap-2 pt-1">
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.95 }}
              className="px-2 py-1 rounded bg-bg-200 text-xs"
              onClick={() => bridge?.toast?.('Hello from ShowcaseBlock', 'success')}
            >
              bridge.toast
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.95 }}
              className="px-2 py-1 rounded bg-bg-200 text-xs"
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
