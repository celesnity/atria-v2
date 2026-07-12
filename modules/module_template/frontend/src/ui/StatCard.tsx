import React from "react";
import { motion } from "motion/react";
import { useMinderTheme } from "minder-ui-sdk";
import AnimatedNumber from "./AnimatedNumber";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  suffix?: string;
}

export default function StatCard({ icon, label, value, suffix }: StatCardProps) {
  const { tokens } = useMinderTheme();

  return (
    <motion.div
      whileHover={{ y: -2, boxShadow: tokens.cardHoverShadow }}
      transition={{ duration: 0.2 }}
      style={{
        background: tokens.surface,
        border: `1px solid ${tokens.border}`,
        borderRadius: 12,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 14,
        flex: 1,
        minWidth: 0,
        boxShadow: tokens.cardShadow,
      }}
    >
      <div style={{ color: tokens.primary, opacity: 0.9 }}>{icon}</div>
      <div>
        <div style={{ color: tokens.textMuted, fontSize: 12, marginBottom: 2 }}>{label}</div>
        <div style={{ color: tokens.text, fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
          <AnimatedNumber value={value} />
          {suffix && <span style={{ fontSize: 14, marginLeft: 2, color: tokens.textMuted }}>{suffix}</span>}
        </div>
      </div>
    </motion.div>
  );
}
