import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Package, Plus, RefreshCw, Trash2, PackagePlus, Sparkles, Check, X, Search, Copy, ArrowUpDown } from "lucide-react";
import { useMinderTheme, useAgentForm } from "minder-ui-sdk";
import { useToast } from "../ui/Toast";
import { mascotSay } from "../ui/Mascot";
import { variants } from "../theme";

interface Product {
  id: number;
  sku: string;
  name: string;
  price: number;
  category: string;
  stock: number;
}

type FormState = { sku: string; name: string; price: string; category: string };
const EMPTY: FormState = { sku: "", name: "", price: "", category: "" };

export default function ProductsPanel({ apiBase }: { apiBase: string }) {
  const { tokens } = useMinderTheme();
  const { push } = useToast();
  const [products, setProducts] = useState<Product[]>([]);
  const [value, setValue] = useState<FormState>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [cat, setCat] = useState<string>("all");
  const [sortDesc, setSortDesc] = useState(false);

  const base = apiBase.replace(/\/$/, "");

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = products.filter(
      (p) =>
        (cat === "all" || p.category === cat) &&
        (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)),
    );
    list = [...list].sort((a, b) => (sortDesc ? b.price - a.price : a.price - b.price));
    return list;
  }, [products, search, cat, sortDesc]);

  const fetchProducts = () =>
    fetch(`${base}/connector/products`)
      .then((r) => r.json())
      .then((d) => setProducts(d.products || []))
      .catch(() => {});

  useEffect(() => {
    fetchProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase]);

  const submit = () => {
    if (!value.sku || !value.name || !value.price) {
      push("Fill SKU, name and price first", "error");
      return;
    }
    setBusy(true);
    fetch(`${base}/connector/tools/create_product`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        arguments: {
          sku: value.sku,
          name: value.name,
          price: Number(value.price),
          category: value.category,
        },
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.requires_approval) {
          push("Needs approval — see the decision packet", "info");
          mascotSay("ask", "Cái này cần duyệt 🔒", 3200);
        } else {
          push(`Created ${value.name}`, "success");
          mascotSay("celebrate", `Đã tạo ${value.name}! 🎉`);
        }
        setValue(EMPTY);
        return fetchProducts();
      })
      .catch(() => push("Create failed", "error"))
      .finally(() => setBusy(false));
  };

  // Agent co-pilot: `fill`/`focus`/`request_confirm` intents drive THIS form.
  const { agentFilled, pendingConfirm, focusField, confirm, reject } = useAgentForm<FormState>(
    "add_product",
    { value, setValue, onSubmit: submit },
  );

  const restock = (id: number) =>
    fetch(`${base}/connector/tools/restock_product`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arguments: { product_id: id, qty: 10 } }),
    })
      .then((r) => r.json())
      .then(() => {
        push("Restocked +10", "success");
        mascotSay("happy", "Nhập thêm 10 📦", 1800);
        return fetchProducts();
      })
      .catch(() => push("Restock failed", "error"));

  const duplicate = (id: number) =>
    fetch(`${base}/connector/tools/duplicate_product`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arguments: { product_id: id } }),
    })
      .then((r) => r.json())
      .then(() => {
        push("Duplicated", "success");
        mascotSay("happy", "Nhân bản xong 🧬", 1800);
        return fetchProducts();
      })
      .catch(() => push("Duplicate failed", "error"));

  // Delete is HIGH risk → gated. Clicking is a human approval, so we post a
  // decision (approve) which re-runs the action past the gate.
  const del = (id: number, name: string) =>
    fetch(`${base}/connector/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict: "approve", action: "delete_product", arguments: { product_id: id } }),
    })
      .then((r) => r.json())
      .then(() => {
        push(`Deleted ${name}`, "success");
        mascotSay("nervous", `Đã xoá ${name} 😬`, 2000);
        return fetchProducts();
      })
      .catch(() => push("Delete failed", "error"));

  const field = (key: keyof FormState, label: string, placeholder: string, type = "text") => {
    const filled = agentFilled.includes(key);
    const focused = focusField === key;
    return (
      <div data-agent-field={key} style={{ flex: 1, minWidth: 130 }}>
        <label style={{ fontSize: 11, color: tokens.textMuted, display: "flex", gap: 6, marginBottom: 4 }}>
          {label}
          {filled && (
            <span style={{ color: tokens.info, display: "inline-flex", alignItems: "center", gap: 3 }}>
              <Sparkles size={11} /> agent
            </span>
          )}
        </label>
        <input
          type={type}
          value={String(value[key] ?? "")}
          placeholder={placeholder}
          onChange={(e) => setValue({ ...value, [key]: e.target.value })}
          style={{
            width: "100%",
            boxSizing: "border-box",
            background: tokens.surfaceAlt,
            border: `1px solid ${focused ? tokens.primary : filled ? tokens.info : tokens.border}`,
            boxShadow: focused ? `0 0 0 3px ${tokens.primary}33` : "none",
            borderRadius: 8,
            padding: "8px 10px",
            color: tokens.text,
            fontSize: 13,
            outline: "none",
          }}
        />
      </div>
    );
  };

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: tokens.text, fontSize: 16, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          <Package size={17} /> Products
        </h3>
        <motion.button
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
          onClick={fetchProducts}
          style={{ background: "none", border: `1px solid ${tokens.border}`, borderRadius: 8, padding: "6px 12px", color: tokens.textMuted, cursor: "pointer" }}
        >
          <RefreshCw size={15} />
        </motion.button>
      </div>

      {/* Add Product form — agent-drivable */}
      <div data-agent-form="add_product" style={{ background: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          {field("sku", "SKU", "SKU-003")}
          {field("name", "Name", "Cirrus Mug")}
          {field("price", "Price", "19.90", "number")}
          {field("category", "Category", "A / B / C")}
          <motion.button
            data-agent-control="submit"
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            onClick={submit}
            disabled={busy}
            style={{
              display: "flex", alignItems: "center", gap: 6, background: tokens.primary,
              border: "none", borderRadius: 8, padding: "9px 14px", color: "#fff",
              fontSize: 13, fontWeight: 500, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1,
            }}
          >
            <Plus size={14} /> Add
          </motion.button>
        </div>

        <AnimatePresence>
          {pendingConfirm && (
            <motion.div
              initial={{ opacity: 0, height: 0, marginTop: 0 }}
              animate={{ opacity: 1, height: "auto", marginTop: 14 }}
              exit={{ opacity: 0, height: 0, marginTop: 0 }}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                background: `${tokens.info}14`, border: `1px solid ${tokens.info}55`,
                borderRadius: 10, padding: "10px 14px", overflow: "hidden",
              }}
            >
              <Sparkles size={15} style={{ color: tokens.info, flexShrink: 0 }} />
              <span style={{ flex: 1, color: tokens.text, fontSize: 13 }}>
                {pendingConfirm.summary || "The agent prefilled this — confirm to submit."}
              </span>
              <button onClick={confirm} data-minder-approve="" style={confirmBtn(tokens.success)}>
                <Check size={13} /> Confirm
              </button>
              <button onClick={reject} style={confirmBtn(tokens.textMuted)}>
                <X size={13} /> Reject
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Toolbar: search + category chips + sort */}
      {products.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: 1, minWidth: 160 }}>
            <Search size={14} style={{ position: "absolute", left: 10, top: 9, color: tokens.textMuted }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name or SKU…"
              style={{ width: "100%", boxSizing: "border-box", background: tokens.surfaceAlt, border: `1px solid ${tokens.border}`, borderRadius: 8, padding: "7px 10px 7px 30px", color: tokens.text, fontSize: 13, outline: "none" }}
            />
          </div>
          {["all", "A", "B", "C"].map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              style={{
                border: `1px solid ${cat === c ? tokens.primary : tokens.border}`,
                background: cat === c ? `${tokens.primary}1e` : "transparent",
                color: cat === c ? tokens.primary : tokens.textMuted,
                borderRadius: 999, padding: "5px 12px", fontSize: 12, cursor: "pointer", fontWeight: 500,
              }}
            >
              {c === "all" ? "All" : c}
            </button>
          ))}
          <button
            onClick={() => setSortDesc((s) => !s)}
            title="Sort by price"
            style={{ display: "flex", alignItems: "center", gap: 5, border: `1px solid ${tokens.border}`, background: "transparent", color: tokens.textMuted, borderRadius: 8, padding: "6px 10px", fontSize: 12, cursor: "pointer" }}
          >
            <ArrowUpDown size={13} /> {sortDesc ? "Price ↓" : "Price ↑"}
          </button>
        </div>
      )}

      {/* Catalog list */}
      {shown.length === 0 ? (
        <div style={{ color: tokens.textMuted, textAlign: "center", padding: "40px 0", fontSize: 14 }}>
          {products.length === 0
            ? 'No products yet — add one above, or ask the agent to "add product …"'
            : "No products match your filter."}
        </div>
      ) : (
        <motion.div variants={variants.listContainer} initial="hidden" animate="visible" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <AnimatePresence>
            {shown.map((p) => (
              <motion.div
                key={p.id}
                layout
                variants={variants.listItem}
                exit="exit"
                style={{
                  background: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 10,
                  padding: "12px 14px", display: "flex", alignItems: "center", gap: 12,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: tokens.text, fontSize: 14, fontWeight: 500 }}>
                    {p.name} <span style={{ color: tokens.textMuted, fontSize: 12 }}>· {p.sku}</span>
                  </div>
                  <div style={{ color: tokens.textMuted, fontSize: 12, marginTop: 2 }}>
                    ${p.price.toFixed(2)} · {p.category || "—"} · {p.stock} in stock
                  </div>
                </div>
                <button onClick={() => restock(p.id)} title="Restock +10" style={iconBtn(tokens.border, tokens.textMuted)}>
                  <PackagePlus size={15} />
                </button>
                <button onClick={() => duplicate(p.id)} title="Duplicate" style={iconBtn(tokens.border, tokens.textMuted)}>
                  <Copy size={15} />
                </button>
                <button onClick={() => del(p.id, p.name)} title="Delete (high risk — approval)" style={iconBtn(`${tokens.error}55`, tokens.error)}>
                  <Trash2 size={15} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  );
}

function confirmBtn(color: string): React.CSSProperties {
  return {
    display: "flex", alignItems: "center", gap: 4, background: "transparent",
    border: `1px solid ${color}`, color, borderRadius: 7, padding: "5px 10px",
    fontSize: 12, fontWeight: 600, cursor: "pointer",
  };
}

function iconBtn(border: string, color: string): React.CSSProperties {
  return {
    background: "none", border: `1px solid ${border}`, borderRadius: 8,
    padding: "7px 9px", color, cursor: "pointer", display: "flex", alignItems: "center",
  };
}
