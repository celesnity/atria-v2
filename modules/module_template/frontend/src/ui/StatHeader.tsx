import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Briefcase, Image, Database, Activity } from "lucide-react";
import { useMinderTheme } from "minder-ui-sdk";
import StatCard from "./StatCard";

interface Props {
  apiBase: string;
}

/** Persistent module chrome (brand header + stat cards + health) shown above
 *  whichever tab panel the host has selected. */
export default function StatHeader({ apiBase }: Props) {
  const { tokens } = useMinderTheme();
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

  const healthDotColor =
    healthy === null ? tokens.warning : healthy ? tokens.success : tokens.error;

  return (
    <div>
      {/* Header */}
      <div style={{ borderBottom: `1px solid ${tokens.border}`, padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <span style={{
            display: "grid", placeItems: "center", width: 32, height: 32, borderRadius: 9,
            background: tokens.brandGradient,
            boxShadow: "0 6px 20px rgba(46,107,246,0.40)",
          }}>
            <Activity size={17} style={{ color: "#fff" }} />
          </span>
          <span style={{
            fontWeight: 700, fontSize: 18, letterSpacing: "-0.01em",
            background: tokens.titleGradient,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}>
            Module Template
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <motion.span
            animate={healthy ? { scale: [1, 1.3, 1], opacity: [1, 0.6, 1] } : {}}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
            style={{
              width: 9, height: 9, borderRadius: "50%", display: "inline-block",
              background: healthDotColor,
            }}
          />
          <span style={{ color: tokens.textMuted }}>
            {healthy === null ? "connecting…" : healthy ? "connector online" : "offline"}
          </span>
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
    </div>
  );
}
