import React from "react";
import { motion } from "motion/react";
import AnimatedNumber from "./AnimatedNumber";
import { COLORS } from "../theme";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  suffix?: string;
}

export default function StatCard({ icon, label, value, suffix }: StatCardProps) {
  return (
    <motion.div
      whileHover={{ y: -2, boxShadow: "0 8px 32px rgba(99,102,241,0.2)" }}
      transition={{ duration: 0.2 }}
      style={{
        background: "#1a1a2e",
        border: "1px solid #2d2d44",
        borderRadius: 12,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 14,
        flex: 1,
        minWidth: 0,
      }}
    >
      <div style={{ color: COLORS.primary, opacity: 0.9 }}>{icon}</div>
      <div>
        <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 2 }}>{label}</div>
        <div style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
          <AnimatedNumber value={value} />{suffix && <span style={{ fontSize: 14, marginLeft: 2, color: "#94a3b8" }}>{suffix}</span>}
        </div>
      </div>
    </motion.div>
  );
}
