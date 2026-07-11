import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Database, RefreshCw, MessageSquare } from "lucide-react";
import StatCard from "../ui/StatCard";
import { variants } from "../theme";

interface Overview {
  mt_jobs: number;
  mt_media: number;
  atria_conversations: { id: string; title: string; status: string }[];
  atria_artifacts_count: number;
  atria_recent_artifacts: string[];
}

export default function DataPanel({ apiBase }: { apiBase: string }) {
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
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h3 style={{ margin: 0, color: "#e2e8f0", fontSize: 16, fontWeight: 600 }}>Data Overview</h3>
        <motion.button
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
          onClick={fetchData}
          style={{ background: "none", border: "1px solid #2d2d44", borderRadius: 8, padding: "6px 12px", color: "#94a3b8", cursor: "pointer" }}
        >
          <motion.div animate={{ rotate: loading ? 360 : 0 }} transition={{ duration: 0.6, repeat: loading ? Infinity : 0, ease: "linear" }}>
            <RefreshCw size={15} />
          </motion.div>
        </motion.button>
      </div>

      {data && (
        <>
          <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
            <StatCard icon={<Database size={20} />} label="Module Jobs" value={data.mt_jobs} />
            <StatCard icon={<Database size={20} />} label="Media Files" value={data.mt_media} />
            <StatCard icon={<Database size={20} />} label="Artifacts" value={data.atria_artifacts_count} />
          </div>

          <h4 style={{ color: "#94a3b8", fontSize: 13, fontWeight: 500, margin: "0 0 12px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Atria Conversations
          </h4>

          {(data.atria_conversations?.length ?? 0) === 0 ? (
            <div style={{ color: "#64748b", fontSize: 13, padding: "16px 0" }}>No conversations found</div>
          ) : (
            <motion.div
              variants={variants.listContainer}
              initial="hidden"
              animate="visible"
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
            >
              <AnimatePresence>
                {data.atria_conversations.map((c) => (
                  <motion.div
                    key={c.id}
                    layout
                    variants={variants.listItem}
                    style={{
                      background: "#1a1a2e", border: "1px solid #2d2d44",
                      borderRadius: 10, padding: "10px 14px",
                      display: "flex", alignItems: "center", gap: 10,
                    }}
                  >
                    <MessageSquare size={15} style={{ color: "#6366f1", flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: "#e2e8f0", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title || c.id}</div>
                      <div style={{ color: "#64748b", fontSize: 11, marginTop: 2 }}>{c.status}</div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </>
      )}
    </div>
  );
}
