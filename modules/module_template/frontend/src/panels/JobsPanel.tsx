import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Play, Loader2, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { useMinderTheme, Agent } from "minder-ui-sdk";
import { statusColor, variants } from "../theme";

interface Job {
  id: string;
  kind: string;
  status: string;
  pct: number;
  created_at: string;
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  running: <Loader2 size={14} className="spin" />,
  done: <CheckCircle2 size={14} />,
  error: <XCircle size={14} />,
  queued: <AlertCircle size={14} />,
};

export default function JobsPanel({ apiBase }: { apiBase: string }) {
  const { tokens } = useMinderTheme();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [starting, setStarting] = useState(false);

  const fetchJobs = () => {
    fetch(`${apiBase}/connector/jobs`)
      .then((r) => r.json())
      .then((d) => setJobs(d.jobs || []))
      .catch(() => {});
  };

  const startJob = () => {
    setStarting(true);
    fetch(`${apiBase}/connector/jobs/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps: 5 }),
    })
      .then((r) => r.json())
      .then(() => fetchJobs())
      .catch(() => {})
      .finally(() => setStarting(false));
  };

  // One-shot fetch on mount; the live polling below only runs while a job is
  // actually in flight.
  useEffect(() => {
    fetchJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase]);

  // ponytail: poll every 2s ONLY while a job is running/queued — an idle panel
  // makes zero requests (kills the steady 2s /connector/jobs spam). A job
  // started by the agent elsewhere appears on the next mount/interaction.
  const active = jobs.some((j) => j.status === "running" || j.status === "queued");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(fetchJobs, 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, active]);

  return (
    <Agent.Page name="jobs" description="Background jobs and their status">
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h3 style={{ margin: 0, color: tokens.text, fontSize: 16, fontWeight: 600 }}>Jobs</h3>
        <Agent.Button name="start" description="Start a demo background job" onAct={startJob}>
        <motion.button
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          onClick={startJob}
          disabled={starting}
          style={{
            display: "flex", alignItems: "center", gap: 6, background: tokens.primary,
            border: "none", borderRadius: 8, padding: "7px 14px", color: "#fff",
            fontSize: 13, cursor: starting ? "wait" : "pointer", fontWeight: 500,
            opacity: starting ? 0.7 : 1,
          }}
          title="Start a demo background job (5 steps) via the worker"
        >
          {starting ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
          {starting ? "Starting…" : "Start job"}
        </motion.button>
        </Agent.Button>
      </div>

      <style>{`.spin{animation:spin 1s linear infinite}@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>

      <Agent.Data name="list" description="Jobs queued and running" value={jobs}>
      {jobs.length === 0 ? (
        <div style={{ color: tokens.textMuted, textAlign: "center", padding: "40px 0", fontSize: 14 }}>
          No jobs yet — click "Start job", or ask the agent in chat
        </div>
      ) : (
        <motion.div
          variants={variants.listContainer}
          initial="hidden"
          animate="visible"
          style={{ display: "flex", flexDirection: "column", gap: 10 }}
        >
          <AnimatePresence>
            {jobs.map((job) => {
              const color = statusColor(tokens, job.status);
              return (
                <motion.div
                  key={job.id}
                  layout
                  variants={variants.listItem}
                  exit="exit"
                  style={{
                    background: tokens.surface,
                    border: `1px solid ${tokens.border}`,
                    borderRadius: 10,
                    padding: "12px 14px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                    <span style={{ color: tokens.text, fontSize: 13, fontWeight: 500 }}>{job.kind || job.id}</span>
                    <span style={{
                      display: "flex", alignItems: "center", gap: 5,
                      color, fontSize: 12, fontWeight: 600,
                      background: `${color}18`, borderRadius: 20, padding: "2px 10px",
                    }}>
                      {STATUS_ICONS[job.status]}
                      {job.status}
                    </span>
                  </div>
                  <div style={{ background: tokens.surfaceAlt, borderRadius: 4, height: 6, overflow: "hidden" }}>
                    <motion.div
                      animate={{ width: `${job.pct ?? 0}%` }}
                      transition={{ duration: 0.5, ease: "easeOut" }}
                      style={{ height: "100%", background: color, borderRadius: 4 }}
                    />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, color: tokens.textMuted, fontSize: 11 }}>
                    <span>{job.id}</span>
                    <span>{job.pct ?? 0}%</span>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </motion.div>
      )}
      </Agent.Data>
    </div>
    </Agent.Page>
  );
}
