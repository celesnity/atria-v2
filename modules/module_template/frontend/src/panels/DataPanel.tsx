import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Database, RefreshCw, MessageSquare } from "lucide-react";
import { useMinderTheme, Agent } from "../embinder";
import StatCard from "../ui/StatCard";
import { variants } from "../theme";

interface Overview {
  mt_jobs: number;
  mt_media: number;
  minder_conversations: { id: string; title: string; status: string }[];
  minder_artifacts_count: number;
  minder_recent_artifacts: string[];
}

export default function DataPanel({ apiBase }: { apiBase: string }) {
  const { tokens } = useMinderTheme();
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = () => {
    setLoading(true);
    fetch(`${apiBase}/connector/overview`)
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [apiBase]);

  return (
    <Agent.Page name="data" description="Raw data tables and records">
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h3 style={{ margin: 0, color: tokens.text, fontSize: 16, fontWeight: 600 }}>Data Overview</h3>
        <Agent.Button name="refresh" description="Reload data" onAct={fetchData}>
        <motion.button
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
          onClick={fetchData}
          style={{ background: "none", border: `1px solid ${tokens.border}`, borderRadius: 8, padding: "6px 12px", color: tokens.textMuted, cursor: "pointer" }}
        >
          <motion.div animate={{ rotate: loading ? 360 : 0 }} transition={{ duration: 0.6, repeat: loading ? Infinity : 0, ease: "linear" }}>
            <RefreshCw size={15} />
          </motion.div>
        </motion.button>
        </Agent.Button>
      </div>

      <Agent.Data name="overview" description="Module DB counts and recent conversations" value={data}>
      {data && (
        <>
          <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
            <StatCard icon={<Database size={20} />} label="Module Jobs" value={data.mt_jobs} />
            <StatCard icon={<Database size={20} />} label="Media Files" value={data.mt_media} />
            <StatCard icon={<Database size={20} />} label="Artifacts" value={data.minder_artifacts_count} />
          </div>

          <h4 style={{ color: tokens.textMuted, fontSize: 13, fontWeight: 500, margin: "0 0 12px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Minder Conversations
          </h4>

          {(data.minder_conversations?.length ?? 0) === 0 ? (
            <div style={{ color: tokens.textMuted, fontSize: 13, padding: "16px 0" }}>No conversations found</div>
          ) : (
            <motion.div
              variants={variants.listContainer}
              initial="hidden"
              animate="visible"
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
            >
              <AnimatePresence>
                {data.minder_conversations.map((c) => (
                  <motion.div
                    key={c.id}
                    layout
                    variants={variants.listItem}
                    style={{
                      background: tokens.surface,
                      border: `1px solid ${tokens.border}`,
                      borderRadius: 10,
                      padding: "10px 14px",
                      display: "flex", alignItems: "center", gap: 10,
                    }}
                  >
                    <MessageSquare size={15} style={{ color: tokens.primary, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: tokens.text, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title || c.id}</div>
                      <div style={{ color: tokens.textMuted, fontSize: 11, marginTop: 2 }}>{c.status}</div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </>
      )}
      </Agent.Data>
    </div>
    </Agent.Page>
  );
}
