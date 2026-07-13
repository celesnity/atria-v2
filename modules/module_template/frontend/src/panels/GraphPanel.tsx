import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Share2, Package, Tag, RefreshCw, Crosshair, X } from "lucide-react";
import { useMinderTheme, Agent } from "minder-ui-sdk";

/**
 * Operational Graph demo (BE-SDK-10). Reads the module's `/connector/graph`
 * endpoint — the whole graph on load, and a node's linked neighbourhood when you
 * focus one. This is the same surface the agent queries to pull *connected*
 * context (a product and its category) instead of one isolated read.
 */

interface GNode {
  id: string;
  kind: "product" | "category";
  label: string;
  sku?: string;
  price?: number;
  stock?: number;
}
interface GEdge {
  from: string;
  to: string;
  rel: string;
}
interface GraphData {
  nodes: GNode[];
  edges: GEdge[];
  focus?: string | null;
  available?: boolean;
}

export default function GraphPanel({ apiBase }: { apiBase: string }) {
  const { tokens } = useMinderTheme();
  const base = apiBase.replace(/\/$/, "");
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [focus, setFocus] = useState<GraphData | null>(null);

  const load = useCallback(
    (node?: string) => {
      const qs = node ? `?node=${encodeURIComponent(node)}&depth=1` : "";
      return fetch(`${base}/connector/graph${qs}`)
        .then((r) => r.json())
        .then((d: GraphData) => (node ? setFocus(d) : setGraph(d)))
        .catch(() => {});
    },
    [base],
  );

  useEffect(() => {
    load();
  }, [load]);

  const nodeIcon = (kind: string) =>
    kind === "category" ? <Tag size={14} /> : <Package size={14} />;

  const nodeColor = (kind: string) => (kind === "category" ? tokens.warning : tokens.primary);

  if (!graph) return <div style={{ padding: 20, color: tokens.textMuted, textAlign: "center" }}>Loading graph…</div>;

  const labelOf = (id: string) => graph.nodes.find((n) => n.id === id)?.label ?? id;

  return (
    <Agent.Page name="graph" description="Operational Graph — products linked to categories">
    <Agent.Data name="nodes" description="Product/category graph nodes and edges" value={graph}>
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: tokens.text, fontSize: 16, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          <Share2 size={17} /> Operational Graph
        </h3>
        <Agent.Button name="reload" description="Reload the whole graph" onAct={() => { setFocus(null); load(); }}>
        <motion.button
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
          onClick={() => { setFocus(null); load(); }}
          style={{ background: "none", border: `1px solid ${tokens.border}`, borderRadius: 8, padding: "6px 12px", color: tokens.textMuted, cursor: "pointer" }}
        >
          <RefreshCw size={15} />
        </motion.button>
        </Agent.Button>
      </div>

      <p style={{ color: tokens.textMuted, fontSize: 13, margin: "0 0 16px" }}>
        {graph.nodes.length} nodes · {graph.edges.length} edges. Focus a node to
        pull its linked context — the same query the agent runs.
      </p>

      {/* Focused neighbourhood (a node's linked context) */}
      <AnimatePresence>
        {focus && focus.focus && (
          <motion.div
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            style={{ background: `${tokens.primary}12`, border: `1px solid ${tokens.primary}44`, borderRadius: 10, padding: 14, marginBottom: 18, overflow: "hidden" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <Crosshair size={14} style={{ color: tokens.primary }} />
              <strong style={{ color: tokens.text, fontSize: 13 }}>Linked context · {labelOf(focus.focus)}</strong>
              <button onClick={() => setFocus(null)} style={{ marginLeft: "auto", background: "none", border: "none", color: tokens.textMuted, cursor: "pointer" }}>
                <X size={15} />
              </button>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
              {focus.nodes.map((n) => (
                <span key={n.id} style={{ display: "inline-flex", alignItems: "center", gap: 5, border: `1px solid ${nodeColor(n.kind)}`, color: nodeColor(n.kind), borderRadius: 999, padding: "3px 10px", fontSize: 12 }}>
                  {nodeIcon(n.kind)} {n.label}
                </span>
              ))}
            </div>
            <div style={{ color: tokens.textMuted, fontSize: 12 }}>
              {focus.edges.map((e, i) => (
                <div key={i}>{labelOf(e.from)} —<em>{e.rel}</em>→ {labelOf(e.to)}</div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* All nodes — click to focus */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {graph.nodes.map((n) => (
          <motion.button
            key={n.id}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            onClick={() => load(n.id)}
            style={{
              textAlign: "left", display: "flex", alignItems: "center", gap: 10,
              background: tokens.surface, border: `1px solid ${focus?.focus === n.id ? nodeColor(n.kind) : tokens.border}`,
              borderRadius: 10, padding: "11px 14px", color: tokens.text, cursor: "pointer",
            }}
          >
            <span style={{ color: nodeColor(n.kind), display: "inline-flex" }}>{nodeIcon(n.kind)}</span>
            <span style={{ fontSize: 14, fontWeight: 500 }}>{n.label}</span>
            {n.kind === "product" && (
              <span style={{ color: tokens.textMuted, fontSize: 12 }}>
                {n.sku} · ${n.price?.toFixed(2)} · {n.stock} in stock
              </span>
            )}
            <span style={{ marginLeft: "auto", color: tokens.textMuted, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>{n.kind}</span>
          </motion.button>
        ))}
      </div>
    </div>
    </Agent.Data>
    </Agent.Page>
  );
}
