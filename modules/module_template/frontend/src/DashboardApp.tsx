import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Briefcase, Image, Database, BarChart3, Activity } from "lucide-react";
import { ToastProvider } from "./ui/Toast";
import StatCard from "./ui/StatCard";
import JobsPanel from "./panels/JobsPanel";
import MediaPanel from "./panels/MediaPanel";
import DataPanel from "./panels/DataPanel";
import MetricsPanel from "./panels/MetricsPanel";
import { variants, COLORS } from "./theme";

const TABS = [
  { id: "jobs", label: "Jobs", icon: <Briefcase size={15} /> },
  { id: "media", label: "Media", icon: <Image size={15} /> },
  { id: "data", label: "Data", icon: <Database size={15} /> },
  { id: "metrics", label: "Metrics", icon: <BarChart3 size={15} /> },
] as const;

type TabId = typeof TABS[number]["id"];

interface Props {
  apiBase: string;
}

export default function DashboardApp({ apiBase }: Props) {
  const [tab, setTab] = useState<TabId>("jobs");
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [overview, setOverview] = useState<{ mt_jobs: number; mt_media: number; minder_artifacts_count: number } | null>(null);

  useEffect(() => {
    const check = () => {
      fetch(`${apiBase}/connector/health`)
        .then((r) => r.json())
        .then((d) => setHealthy(!!d.ok))
        .catch(() => setHealthy(false));
    };
    check();
    const t = setInterval(check, 5000);
    return () => clearInterval(t);
  }, [apiBase]);

  useEffect(() => {
    fetch(`${apiBase}/connector/overview`)
      .then((r) => r.json())
      .then(setOverview)
      .catch(() => {});
  }, [apiBase]);

  return (
    <ToastProvider>
      <div style={{ minHeight: "100vh", background: "#0f0f1a", color: "#e2e8f0", fontFamily: "system-ui, -apple-system, sans-serif" }}>
        {/* Header */}
        <div style={{ borderBottom: "1px solid #2d2d44", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Activity size={20} style={{ color: COLORS.primary }} />
            <span style={{ fontWeight: 700, fontSize: 18, color: "#e2e8f0" }}>Module Dashboard</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <motion.span
              animate={healthy ? { scale: [1, 1.3, 1], opacity: [1, 0.6, 1] } : {}}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
              style={{
                width: 9, height: 9, borderRadius: "50%", display: "inline-block",
                background: healthy === null ? "#f59e0b" : healthy ? "#22c55e" : "#ef4444",
              }}
            />
            <span style={{ color: "#94a3b8" }}>{healthy === null ? "connecting…" : healthy ? "connector online" : "offline"}</span>
          </div>
        </div>

        {/* Stat cards */}
        <div style={{ padding: "20px 24px 0" }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <StatCard icon={<Briefcase size={20} />} label="Total Jobs" value={overview?.mt_jobs ?? 0} />
            <StatCard icon={<Image size={20} />} label="Media Files" value={overview?.mt_media ?? 0} />
            <StatCard icon={<Database size={20} />} label="Artifacts" value={overview?.minder_artifacts_count ?? 0} />
          </div>
        </div>

        {/* Tab bar */}
        <div style={{ padding: "20px 24px 0", display: "flex", gap: 4, borderBottom: "1px solid #2d2d44", position: "relative" }}>
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "8px 16px", background: "none", border: "none",
                color: tab === t.id ? "#e2e8f0" : "#64748b",
                fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
                cursor: "pointer", position: "relative", transition: "color 0.2s",
              }}
            >
              {t.icon}
              {t.label}
              {tab === t.id && (
                <motion.div
                  layoutId="tabUnderline"
                  style={{
                    position: "absolute", bottom: -1, left: 0, right: 0, height: 2,
                    background: COLORS.primary, borderRadius: "2px 2px 0 0",
                  }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Panel */}
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            variants={variants.panelVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            {tab === "jobs" && <JobsPanel apiBase={apiBase} />}
            {tab === "media" && <MediaPanel apiBase={apiBase} />}
            {tab === "data" && <DataPanel apiBase={apiBase} />}
            {tab === "metrics" && <MetricsPanel apiBase={apiBase} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </ToastProvider>
  );
}
