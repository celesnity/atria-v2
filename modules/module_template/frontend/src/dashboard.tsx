import { defineDashboard } from "minder-ui-sdk";
import { ToastProvider } from "./ui/Toast";
import StatHeader from "./ui/StatHeader";
import JobsPanel from "./panels/JobsPanel";
import MediaPanel from "./panels/MediaPanel";
import DataPanel from "./panels/DataPanel";
import MetricsPanel from "./panels/MetricsPanel";
import { TABS } from "./dashboard.tabs";

// MediaPanel calls useToast(), so ALL panels must render inside ToastProvider.
// We wrap the header slot in ToastProvider so the provider covers the entire
// dashboard shell (header + panels rendered as siblings by the host).
// The host renders: <ToastProvider><Header/></ToastProvider> ... <Panel/>
// That is NOT sufficient — panels are outside the provider.
// Solution: expose each panel wrapped in ToastProvider via a thin HOC.

function withToast<P extends object>(Panel: React.ComponentType<P>): React.ComponentType<P> {
  return function WrappedPanel(props: P) {
    return (
      <ToastProvider>
        <Panel {...props} />
      </ToastProvider>
    );
  };
}

const Header = ({ apiBase }: { apiBase: string }) => (
  <ToastProvider>
    <StatHeader apiBase={apiBase} />
  </ToastProvider>
);

export default defineDashboard({
  title: "Module Template · SDK showcase",
  header: Header,
  tabs: TABS,
  panels: {
    jobs: withToast(JobsPanel),
    media: withToast(MediaPanel),
    data: withToast(DataPanel),
    metrics: withToast(MetricsPanel),
  },
});
