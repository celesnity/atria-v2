import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import AnimatedNumber from "../ui/AnimatedNumber";
import { STATUS_COLORS, CHART_COLORS } from "../theme";

interface Metrics {
  jobs_by_status: Record<string, number>;
  media_total_bytes: number;
}

export default function MetricsPanel({ apiBase }: { apiBase: string }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    fetch(`${apiBase}/connector/metrics`)
      .then((r) => r.json())
      .then(setMetrics)
      .catch(() => {});
  }, [apiBase]);

  if (!metrics) return <div style={{ padding: 20, color: "#64748b", textAlign: "center" }}>Loading metrics…</div>;

  const barData = Object.entries(metrics.jobs_by_status || {}).map(([status, count]) => ({ status, count }));
  const pieData = barData;

  return (
    <div style={{ padding: 20 }}>
      <h3 style={{ margin: "0 0 20px", color: "#e2e8f0", fontSize: 16, fontWeight: 600 }}>Metrics</h3>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        style={{ marginBottom: 28 }}
      >
        <h4 style={{ color: "#94a3b8", fontSize: 12, fontWeight: 500, margin: "0 0 10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Jobs by Status</h4>
        {barData.length === 0 ? (
          <div style={{ color: "#64748b", fontSize: 13 }}>No job data</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={barData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
              <XAxis dataKey="status" tick={{ fill: "#94a3b8", fontSize: 12 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} />
              <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid #2d2d44", borderRadius: 8, color: "#e2e8f0" }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {barData.map((entry) => (
                  <Cell key={entry.status} fill={STATUS_COLORS[entry.status] || CHART_COLORS[0]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
        style={{ marginBottom: 28 }}
      >
        <h4 style={{ color: "#94a3b8", fontSize: 12, fontWeight: 500, margin: "0 0 10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Distribution</h4>
        {pieData.length === 0 ? (
          <div style={{ color: "#64748b", fontSize: 13 }}>No data</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={pieData} dataKey="count" nameKey="status" cx="50%" cy="50%" outerRadius={80}>
                {pieData.map((entry, i) => (
                  <Cell key={entry.status} fill={STATUS_COLORS[entry.status] || CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid #2d2d44", borderRadius: 8, color: "#e2e8f0" }} />
              <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
        style={{ background: "#1a1a2e", border: "1px solid #2d2d44", borderRadius: 10, padding: "14px 16px" }}
      >
        <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 4 }}>Media Storage</div>
        <div style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 700 }}>
          <AnimatedNumber value={Math.round((metrics.media_total_bytes || 0) / 1024)} />{" "}
          <span style={{ fontSize: 14, color: "#94a3b8" }}>KB</span>
        </div>
      </motion.div>
    </div>
  );
}
