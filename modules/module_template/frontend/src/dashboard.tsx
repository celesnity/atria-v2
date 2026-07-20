import type { ReactNode } from "react";
import {
  Agent,
  AgentRegistryProvider,
  MinderThemeProvider,
  useMinderTheme,
  type DashboardComponent,
  type DashboardProps,
} from "./embinder";
import Mascot from "./ui/Mascot";
import { ToastProvider } from "./ui/Toast";

function Surface({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <main
      data-minder-dashboard=""
      style={{
        minHeight: "100%",
        padding: 24,
        background: tokens.bg,
        color: tokens.text,
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {children}
    </main>
  );
}

/** A UI-only federation surface; Minder owns all chat and agent execution. */
function Dashboard({ theme }: DashboardProps) {
  return (
    <MinderThemeProvider theme={theme}>
      <AgentRegistryProvider>
        <ToastProvider>
          <Surface>
            <Agent.Page name="module_template" description="Embind UI-only module template">
              <section style={{ maxWidth: 680 }}>
                <p style={{ color: "#9ca8c8", fontSize: 13, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Embinder module template
                </p>
                <h1 style={{ margin: "8px 0", fontSize: 32 }}>Dashboard surface is ready</h1>
                <Agent.Data
                  name="runtime"
                  description="The module runs as a static federation remote; chat and agent actions are owned by Minder."
                  value={{ runtime: "ui-only", chat: "minder", cursor: "embinder" }}
                >
                  <p style={{ color: "#9ca8c8", lineHeight: 1.6 }}>
                    Ask Minder through the mascot. Tool activity from the host drives the Embinder ghost cursor
                    without a connector, MCP server, Python worker, or module API.
                  </p>
                </Agent.Data>
              </section>
            </Agent.Page>
          </Surface>
          <Mascot />
        </ToastProvider>
      </AgentRegistryProvider>
    </MinderThemeProvider>
  );
}

const withMeta = Dashboard as DashboardComponent;
withMeta.meta = { title: "Module Template · Embinder", tabs: [] };

export default withMeta;
