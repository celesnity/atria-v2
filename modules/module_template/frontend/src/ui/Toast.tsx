import React, { createContext, useContext, useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, XCircle, Info } from "lucide-react";

type Kind = "success" | "error" | "info";

interface Toast {
  id: number;
  msg: string;
  kind: Kind;
}

interface ToastCtx {
  push: (msg: string, kind?: Kind) => void;
}

const Ctx = createContext<ToastCtx>({ push: () => {} });

export function useToast() {
  return useContext(Ctx);
}

const ICONS: Record<Kind, React.ReactNode> = {
  success: <CheckCircle2 size={16} />,
  error: <XCircle size={16} />,
  info: <Info size={16} />,
};

const KIND_COLORS: Record<Kind, string> = {
  success: "#22c55e",
  error: "#ef4444",
  info: "#5AA6FF",
};

let _id = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((msg: string, kind: Kind = "info") => {
    const id = ++_id;
    setToasts((prev) => [...prev, { id, msg, kind }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 60, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.15 } }}
              style={{
                background: "#111A2E",
                border: `1px solid ${KIND_COLORS[t.kind]}44`,
                borderLeft: `3px solid ${KIND_COLORS[t.kind]}`,
                borderRadius: 8,
                padding: "10px 14px",
                display: "flex",
                alignItems: "center",
                gap: 8,
                color: "#e2e8f0",
                fontSize: 14,
                minWidth: 240,
                boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
              }}
            >
              <span style={{ color: KIND_COLORS[t.kind] }}>{ICONS[t.kind]}</span>
              {t.msg}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
