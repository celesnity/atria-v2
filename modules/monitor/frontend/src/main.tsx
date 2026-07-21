import React from "react";
import ReactDOM from "react-dom/client";
import Dashboard from "./dashboard";

const apiBase = (import.meta.env.VITE_MONITOR_API_BASE || window.location.origin).replace(/\/$/, "");
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><Dashboard apiBase={apiBase} /></React.StrictMode>,
);
