import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  Activity,
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  DatabaseZap,
  Factory,
  Gauge,
  Languages,
  ListTree,
  Moon,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import {
  Agent,
  AgentDriverProvider,
  AgentRegistryProvider,
  MinderThemeProvider,
  useMinderTheme,
  type DashboardComponent,
  type DashboardProps,
} from "minder-ui-sdk";
import { invokeTool, useTool, type ToolState } from "./api";
import { I18nProvider, useI18n, type Locale } from "./i18n";
import { useMonitorPreferences, type MonitorTheme } from "./preferences";
import { TABS } from "./dashboard.tabs";
import "./styles.css";

type AnyRecord = Record<string, any>;
type ProductMode = "overview" | "produce" | "optimize";

const ICONS: Record<string, LucideIcon> = {
  live_operations: Activity,
  event_timeline: ListTree,
  assets: Factory,
  data_health: ShieldCheck,
  data_products: Boxes,
};

function toneForStatus(value: unknown): string {
  const status = String(value || "").toLowerCase();
  if (["healthy", "good", "running", "live", "recovery"].includes(status)) return "good";
  if (["down", "bad", "critical", "failed", "disconnected"].includes(status)) return "bad";
  if (["warning", "warn", "degraded", "incomplete", "uncertain", "waiting", "waiting_for_product", "stale"].includes(status)) return "warn";
  if (["simulation", "automatic", "manual"].includes(status)) return "info";
  return "neutral";
}

function StatusPill({ label, tone }: { label: unknown; tone?: string }) {
  const { statusLabel } = useI18n();
  return (
    <span className={`status-pill status-pill--${tone || toneForStatus(label)}`}>
      <CircleDot size={12} aria-hidden="true" />
      {statusLabel(label)}
    </span>
  );
}

function FactPill({ label }: { label: unknown }) {
  const { factLabel } = useI18n();
  const raw = String(label || "Observed");
  const tone = raw === "Observed" ? "info" : raw === "Calculated" ? "violet" : raw === "Validated" ? "good" : "warn";
  return <span className={`fact-pill fact-pill--${tone}`}>{factLabel(raw)}</span>;
}

function SectionHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return (
    <header className="section-heading">
      <div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div>
      {action}
    </header>
  );
}

function DataBoundary<T>({ state, children }: { state: ToolState<T>; children: ReactNode }) {
  const { t, formatDate } = useI18n();
  if (state.status === "live") return <>{children}</>;
  const content = state.status === "initial_loading"
    ? [t("availability.loadingTitle"), t("availability.loadingBody")]
    : state.status === "stale"
      ? [t("availability.staleTitle"), t("availability.staleBody")]
      : [t("availability.offlineTitle"), t("availability.offlineBody")];
  return (
    <>
      <div className={`data-state-banner data-state-banner--${state.status}`} role={state.status === "offline" ? "alert" : "status"}>
        {state.status === "initial_loading" ? <RefreshCw className="spin" size={19} /> : <WifiOff size={19} />}
        <div><strong>{content[0]}</strong><span>{content[1]}</span><small>{state.refreshedAt ? t("availability.lastSuccess", { time: formatDate(state.refreshedAt) }) : t("availability.never")}</small></div>
        <button className="button button--secondary" onClick={() => void state.refresh()} disabled={state.loading}><RefreshCw size={16} />{t("availability.retry")}</button>
      </div>
      {state.status === "initial_loading" && <div className="skeleton-strip" aria-hidden="true"><span /><span /><span /></div>}
      <div className={state.status === "stale" ? "data-content data-content--stale" : "data-content"}>{children}</div>
    </>
  );
}

function metric(value: unknown): string | number {
  return value === null || value === undefined || value === "" ? "--" : String(value);
}

function normalizeAsset(asset: AnyRecord): AnyRecord {
  return {
    ...asset,
    id: asset.id,
    assetTag: asset.asset_tag || asset.assetTag || asset.id,
    state: asset.status || asset.state || "unknown",
    cell: asset.cell,
    type: asset.type,
    health: asset.health,
    oee: asset.oee,
    throughput: asset.throughput_per_hour ?? asset.thru,
    mode: asset.mode,
    stage: asset.stage,
    phase: asset.phase,
    batchId: asset.batch_id || asset.batchId,
    warnings: asset.warning_codes || asset.warnings || [],
  };
}

function LiveOperations({ apiBase, locale }: { apiBase: string; locale: Locale }) {
  const { t, formatNumber, statusLabel } = useI18n();
  const state = useTool<AnyRecord>(apiBase, "monitor_live_operations");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const data = state.data;
  const operating = data?.state || {};
  const context = data?.work_context || {};
  const intake = data?.intake || {};
  const grounded = state.status === "live" && data?.source_health?.status !== "disconnected";

  async function askMonitor() {
    if (!question.trim() || !grounded) return;
    setAsking(true);
    try {
      const result = await invokeTool<AnyRecord>(apiBase, "monitor_ask", { question: question.trim(), lang: locale });
      setAnswer(result.answer || t("ask.noAnswer"));
    } catch (reason) {
      setAnswer(reason instanceof Error ? reason.message : t("ask.failed"));
    } finally {
      setAsking(false);
    }
  }

  return (
    <Agent.Page name="live_operations" description="Current operational state, context, and observed facts">
      <SectionHeading eyebrow={t("live.eyebrow")} title={t("live.title")} description={t("live.description")} />
      <DataBoundary state={state}>
        <Agent.Data name="operational_snapshot" description="Canonical live operations snapshot" value={data}>
          <div className="metric-grid">
            <article className="metric-card metric-card--accent"><span>{t("live.operatingState")}</span><strong>{operating.operating_state ? statusLabel(operating.operating_state) : "--"}</strong><StatusPill label={operating.operating_mode || "unknown"} /></article>
            <article className="metric-card"><span>{t("live.assetCondition")}</span><strong>{operating.asset_condition ? statusLabel(operating.asset_condition) : "--"}</strong><StatusPill label={t("live.separate")} tone="neutral" /></article>
            <article className="metric-card"><span>{t("live.dataHealth")}</span><strong>{operating.data_health ? statusLabel(operating.data_health) : "--"}</strong><StatusPill label={data?.source_health?.quality || "unknown"} /></article>
            <article className="metric-card"><span>{t("live.simulationMinute")}</span><strong className="tabular">{metric(data?.simulation_minute)}</strong><StatusPill label={data?.scenario || t("live.source")} tone="neutral" /></article>
          </div>
          <div className="content-grid content-grid--wide">
            <article className="surface-card">
              <div className="card-title"><div><p className="eyebrow">{t("live.contextEyebrow")}</p><h3>{t("live.contextTitle")}</h3></div><Factory size={20} /></div>
              <dl className="definition-grid">
                <div><dt>{t("live.running")}</dt><dd>{formatNumber(operating.running_count)}</dd></div>
                <div><dt>{t("live.waiting")}</dt><dd>{formatNumber(operating.waiting_for_product_count)}</dd></div>
                <div><dt>{t("live.queue")}</dt><dd>{formatNumber(intake.queue_len ?? context.intake_queue_len)}</dd></div>
                <div><dt>{t("live.inProgress")}</dt><dd>{formatNumber(intake.in_progress ?? context.in_progress_batches)}</dd></div>
                <div><dt>{t("live.completed")}</dt><dd>{formatNumber(intake.completed ?? context.completed_batches)}</dd></div>
                <div><dt>{t("live.activeBatches")}</dt><dd>{(context.active_batch_ids || []).join(", ") || t("common.notBound")}</dd></div>
              </dl>
            </article>
            <article className="surface-card">
              <div className="card-title"><div><p className="eyebrow">{t("ask.eyebrow")}</p><h3>{t("ask.title")}</h3></div><Sparkles size={20} /></div>
              <label className="field-label" htmlFor="monitor-question">{t("ask.label")}</label>
              <div className="ask-row"><input id="monitor-question" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void askMonitor(); }} placeholder={t("ask.placeholder")} disabled={!grounded} /><button className="button button--primary" disabled={asking || !question.trim() || !grounded} onClick={() => void askMonitor()}>{asking ? <RefreshCw className="spin" size={16} /> : <Search size={16} />}{t("ask.button")}</button></div>
              <p className="helper-text">{grounded ? t("ask.helper") : t("ask.offline")}</p>
              {answer && <div className="answer-box" aria-live="polite">{answer}</div>}
            </article>
          </div>
        </Agent.Data>
      </DataBoundary>
    </Agent.Page>
  );
}

function EventTimeline({ apiBase }: { apiBase: string; locale: Locale }) {
  const { t, formatDate, eventLabel } = useI18n();
  const state = useTool<AnyRecord>(apiBase, "monitor_event_timeline", { since_seq: 0, limit: 100 });
  const [selected, setSelected] = useState<AnyRecord | null>(null);
  const [evidence, setEvidence] = useState<AnyRecord | null>(null);
  const [evidenceError, setEvidenceError] = useState("");
  const events = state.data?.events || [];
  const confidenceScore = selected?.confidence?.score ?? selected?.confidence;

  async function selectEvent(event: AnyRecord) {
    setSelected(event); setEvidence(null); setEvidenceError("");
    try { setEvidence(await invokeTool(apiBase, "monitor_event_evidence", { event_id: event.event_id })); }
    catch (reason) { setEvidenceError(reason instanceof Error ? reason.message : t("timeline.evidenceUnavailable")); }
  }

  return (
    <Agent.Page name="event_timeline" description="Ordered operational facts with evidence and provenance">
      <SectionHeading eyebrow={t("timeline.eyebrow")} title={t("timeline.title")} description={t("timeline.description")} action={<span className="count-chip">{t("common.facts", { count: events.length })}</span>} />
      <DataBoundary state={state}>
        <Agent.Data name="event_timeline" description="Contextual events with fact labels and evidence references" value={state.data}>
          <div className="timeline-layout">
            <ol className="timeline-list" aria-label={t("timeline.listLabel")}>
              {events.length === 0 && <li className="empty-state empty-state--bounded"><ListTree size={26} /><strong>{t("timeline.empty")}</strong></li>}
              {events.map((event: AnyRecord) => <li key={event.event_id}><button className={`event-row ${selected?.event_id === event.event_id ? "event-row--selected" : ""}`} onClick={() => void selectEvent(event)}><span className="sequence tabular">#{event.sequence}</span><span className="event-copy"><strong>{eventLabel(event.event_type)}</strong><small>{formatDate(event.occurred_at)} · {event.scope?.asset_tag || event.scope?.machine_id || t("timeline.unknownAsset")}</small></span><FactPill label={event.fact_label} /><ChevronRight size={18} aria-hidden="true" /></button></li>)}
            </ol>
            <aside className="evidence-panel" aria-live="polite">
              {!selected && <div className="empty-state"><DatabaseZap size={28} /><strong>{t("timeline.select")}</strong><span>{t("timeline.selectHelp")}</span></div>}
              {selected && <><div className="card-title"><div><p className="eyebrow">{t("timeline.evidence")}</p><h3>{selected.event_id}</h3></div><FactPill label={selected.fact_label} /></div>{typeof confidenceScore === "number" && <div className="confidence"><span>{t("timeline.confidence")}</span><strong>{Math.round(confidenceScore * 100)}%</strong></div>}{evidenceError && <p className="inline-error">{evidenceError}</p>}{!evidence && !evidenceError && <div className="mini-loader">{t("timeline.loadingEvidence")}</div>}{evidence && <><h4>{t("timeline.observations")}</h4><ul className="evidence-list">{(evidence.observations || []).map((observation: AnyRecord) => <li key={observation.observation_id}><span>{observation.signal_id}</span><strong className="tabular">{String(observation.value)} {observation.unit || ""}</strong></li>)}</ul><h4>{t("timeline.provenance")}</h4><pre className="mono-wrap">{JSON.stringify(selected.provenance || {}, null, 2)}</pre><div className={`conflict-box ${(evidence.conflicts || []).length ? "conflict-box--warn" : ""}`}><ShieldCheck size={17} /><span>{(evidence.conflicts || []).length ? t("timeline.conflicts", { count: evidence.conflicts.length }) : t("timeline.noConflicts")}</span></div></>}</>}
            </aside>
          </div>
        </Agent.Data>
      </DataBoundary>
    </Agent.Page>
  );
}

function AssetCard({ asset }: { asset: AnyRecord }) {
  const { t, statusLabel, formatNumber } = useI18n();
  const machine = normalizeAsset(asset);
  return <article className="asset-card"><div className="asset-card__top"><div className="asset-icon"><Factory size={20} /></div><div><h3>{machine.assetTag}</h3><p>{machine.id} · {machine.cell || machine.type || t("common.unknown")}</p></div><StatusPill label={machine.state} /></div><div className="asset-metrics"><div><span>{t("assets.oee")}</span><strong className="tabular">{machine.oee != null ? formatNumber(machine.oee, { style: "percent", maximumFractionDigits: 0 }) : "--"}</strong></div><div><span>{t("assets.health")}</span><strong className="tabular">{machine.health != null ? formatNumber(machine.health, { style: "percent", maximumFractionDigits: 0 }) : "--"}</strong></div><div><span>{t("assets.throughput")}</span><strong className="tabular">{formatNumber(machine.throughput)}</strong></div></div><dl className="asset-context"><div><dt>{t("assets.program")}</dt><dd>{machine.mode || "--"}</dd></div><div><dt>{t("assets.stage")}</dt><dd>{machine.stage ? statusLabel(machine.stage) : "--"}</dd></div><div><dt>{t("assets.batch")}</dt><dd>{machine.batchId || "--"}</dd></div></dl>{machine.warnings.length > 0 && <div className="asset-warning"><AlertTriangle size={16} />{machine.warnings.join(", ")}</div>}</article>;
}

function Assets({ apiBase }: { apiBase: string; locale: Locale }) {
  const { t } = useI18n();
  const state = useTool<AnyRecord>(apiBase, "monitor_fleet");
  const machines = state.data?.machines || [];
  return <Agent.Page name="assets" description="Fleet assets and separate runtime and condition states"><SectionHeading eyebrow={t("assets.eyebrow")} title={t("assets.title")} description={t("assets.description")} action={<span className="count-chip">{t("common.assets", { count: machines.length })}</span>} /><DataBoundary state={state}><Agent.Data name="fleet_assets" description="Current machine fleet state" value={machines}><div className={`asset-grid ${machines.length ? "" : "asset-grid--empty"}`}>{machines.length ? machines.map((machine: AnyRecord) => <AssetCard asset={machine} key={machine.id} />) : <div className="empty-state empty-state--bounded"><Factory size={28} /><strong>{t("assets.empty")}</strong><span>{t("assets.emptyHelp")}</span></div>}</div></Agent.Data></DataBoundary></Agent.Page>;
}

function DataHealth({ apiBase }: { apiBase: string; locale: Locale }) {
  const { t, statusLabel, formatNumber } = useI18n();
  const state = useTool<AnyRecord>(apiBase, "monitor_source_health");
  const sources = state.data?.sources?.length ? state.data.sources : [{}];
  return <Agent.Page name="data_health" description="Source freshness, quality, clock accuracy, and calibration"><SectionHeading eyebrow={t("health.eyebrow")} title={t("health.title")} description={t("health.description")} /><DataBoundary state={state}><Agent.Data name="source_health" description="Telemetry source trust metadata" value={state.data}><div className="health-summary"><div className={`health-orb health-orb--${state.data?.overall_status === "healthy" ? "good" : "warn"}`}><ShieldCheck size={28} /></div><div><p className="eyebrow">{t("health.overall")}</p><h3>{statusLabel(state.data?.overall_status)}</h3><p>{t("health.dataHealth", { status: statusLabel(state.data?.data_health) })}</p></div></div><div className="source-table-wrap"><table className="source-table"><caption>{t("health.caption")}</caption><thead><tr><th scope="col">{t("health.source")}</th><th scope="col">{t("health.connection")}</th><th scope="col">{t("health.quality")}</th><th scope="col">{t("health.freshness")}</th><th scope="col">{t("health.clock")}</th><th scope="col">{t("health.calibration")}</th></tr></thead><tbody>{sources.map((source: AnyRecord, index: number) => <tr key={source.source_id || index}><th scope="row">{source.source_id || t("common.unavailable")}<small>{source.domain || t("health.telemetry")}</small></th><td><StatusPill label={source.status || "disconnected"} /></td><td>{statusLabel(source.quality)}</td><td className="tabular">{source.latency_seconds != null ? `${formatNumber(source.latency_seconds)}s` : "--"}</td><td>{source.clock_accuracy_ms != null ? `±${formatNumber(source.clock_accuracy_ms)}ms` : "--"}</td><td>{statusLabel(source.calibration_status)}</td></tr>)}</tbody></table></div></Agent.Data></DataBoundary></Agent.Page>;
}

function ProductColumn({ consumer, title, icon, product }: { consumer: "Produce" | "Optimize"; title: string; icon: ReactNode; product: AnyRecord | null }) {
  const { t } = useI18n();
  const isProduce = consumer === "Produce";
  const lists = isProduce ? [{ label: t("products.downtime"), value: product?.downtime_candidates }, { label: t("products.cycles"), value: product?.cycle_events }, { label: t("products.contextFacts"), value: product?.facts }] : [{ label: t("products.losses"), value: product?.production_loss_events }, { label: t("products.constraints"), value: product?.constraints }, { label: t("products.outcomes"), value: product?.intervention_outcomes }];
  return <article className="product-card"><div className="product-card__header"><div className="product-icon">{icon}</div><div><p className="eyebrow">{isProduce ? t("products.produceArrow") : t("products.optimizeArrow")}</p><h3>{title}</h3></div><StatusPill label={t("common.readOnly")} tone="info" /></div><p className="contract-name">{product?.contract_version || t("products.contractLoading")}</p><div className="product-stats">{lists.map((item) => <div key={item.label}><strong className="tabular">{item.value?.length || 0}</strong><span>{item.label}</span></div>)}</div><div className="product-details"><div><span>{t("products.batchContext")}</span><strong>{product?.work_context?.active_batch_ids?.length || product?.work_context?.batch_id || 0}</strong></div><div><span>{t("products.machineCount")}</span><strong>{product?.assets?.length || 0}</strong></div><div><span>{t("products.readiness")}</span><strong>{product?.data_quality?.status || product?.data_readiness?.status || t("common.unknown")}</strong></div></div><p className="boundary-note"><ShieldCheck size={16} />{t("products.boundary", { consumer })}</p></article>;
}

function MiniFactList({ title, events }: { title: string; events: AnyRecord[] }) {
  const { t, eventLabel } = useI18n();
  return <article className="surface-card fact-list-card"><h3>{title}</h3>{events.length ? <ul className="mini-fact-list">{events.slice(-8).reverse().map((event) => <li key={event.event_id}><FactPill label={event.fact_label} /><span>{eventLabel(event.event_type)}</span><strong>{event.scope?.asset_tag || event.scope?.machine_id || "—"}</strong></li>)}</ul> : <div className="empty-state empty-state--compact">{t("optimize.empty")}</div>}</article>;
}

function ProduceMode({ product }: { product: AnyRecord | null }) {
  const { t } = useI18n();
  const assets = (product?.assets || []).map(normalizeAsset);
  const running = assets.filter((asset: AnyRecord) => asset.state === "running").length;
  const faulted = assets.filter((asset: AnyRecord) => asset.state === "down").length;
  const waiting = assets.filter((asset: AnyRecord) => asset.state === "idle").length;
  const candidates = product?.downtime_candidates || [];
  return <div className="consumer-mode"><SectionHeading eyebrow={t("products.produceArrow")} title={t("produce.title")} description={t("produce.description")} /><div className="consumer-metrics"><article><span>{t("produce.running")}</span><strong>{running}</strong></article><article><span>{t("produce.waiting")}</span><strong>{waiting}</strong></article><article><span>{t("produce.faulted")}</span><strong>{faulted}</strong></article><article><span>{t("produce.queue")}</span><strong>{product?.intake?.queue_len ?? "--"}</strong></article></div><article className="surface-card"><h3>{t("produce.executionBoard")}</h3><div className="execution-board">{assets.length ? assets.map((asset: AnyRecord) => <div className="execution-row" key={asset.id}><div><strong>{asset.assetTag}</strong><span>{asset.type} · {asset.mode || "--"}</span></div><StatusPill label={asset.state} /><span>{asset.stage || "--"}</span><strong>{asset.batchId || "--"}</strong></div>) : <div className="empty-state empty-state--compact">{t("assets.empty")}</div>}</div></article><MiniFactList title={t("produce.candidates")} events={candidates} /></div>;
}

function OptimizeMode({ product }: { product: AnyRecord | null }) {
  const { t, formatNumber, statusLabel } = useI18n();
  const snapshot = product?.operational_state_snapshot || {};
  const readiness = product?.data_readiness || {};
  return <div className="consumer-mode"><SectionHeading eyebrow={t("products.optimizeArrow")} title={t("optimize.title")} description={t("optimize.description")} /><div className="consumer-metrics"><article><span>{t("optimize.oee")}</span><strong>{snapshot.average_oee != null ? formatNumber(snapshot.average_oee, { style: "percent", maximumFractionDigits: 1 }) : "--"}</strong></article><article><span>{t("optimize.throughput")}</span><strong>{formatNumber(snapshot.total_throughput_per_hour)}</strong></article><article><span>{t("optimize.target")}</span><strong>{formatNumber(snapshot.total_target_per_hour)}</strong></article><article><span>{t("optimize.completed")}</span><strong>{formatNumber(snapshot.completed_batches)}</strong></article></div><article className="readiness-card"><div><p className="eyebrow">{t("optimize.readiness")}</p><h3>{statusLabel(readiness.status)}</h3></div><div><span>{t("optimize.identity")}</span><strong>{readiness.identity_complete ? "✓" : "—"}</strong></div><StatusPill label={readiness.source_quality || "unknown"} /></article><div className="fact-list-grid"><MiniFactList title={t("optimize.losses")} events={product?.production_loss_events || []} /><MiniFactList title={t("optimize.constraints")} events={product?.constraints || []} /><MiniFactList title={t("optimize.invalidations")} events={product?.recommendation_invalidating_events || []} /><MiniFactList title={t("optimize.outcomes")} events={product?.intervention_outcomes || []} /></div></div>;
}

function DataProducts({ apiBase }: { apiBase: string; locale: Locale }) {
  const { t } = useI18n();
  const [mode, setMode] = useState<ProductMode>("overview");
  const produce = useTool<AnyRecord>(apiBase, "monitor_produce_data_product");
  const optimize = useTool<AnyRecord>(apiBase, "monitor_optimize_data_product");
  const combined: ToolState<AnyRecord> = { data: { produce: produce.data, optimize: optimize.data }, error: produce.error || optimize.error, loading: produce.loading || optimize.loading, status: produce.status === "offline" || optimize.status === "offline" ? "offline" : produce.status === "stale" || optimize.status === "stale" ? "stale" : produce.status === "initial_loading" || optimize.status === "initial_loading" ? "initial_loading" : "live", refreshedAt: produce.refreshedAt || optimize.refreshedAt, refresh: async () => { await Promise.all([produce.refresh(), optimize.refresh()]); } };
  return <Agent.Page name="data_products" description="Purpose-built read contracts for Produce and Optimize"><SectionHeading eyebrow={t("products.eyebrow")} title={t("products.title")} description={t("products.description")} action={<div className="segmented segmented--modes" role="group" aria-label={t("products.modeLabel")}>{(["overview", "produce", "optimize"] as ProductMode[]).map((item) => <button key={item} aria-pressed={mode === item} onClick={() => setMode(item)}>{t(`products.${item}` as any)}</button>)}</div>} /><DataBoundary state={combined}><Agent.Data name="produce_data_product" description="Produce-ready state, cycles, and downtime evidence" value={produce.data}><Agent.Data name="optimize_data_product" description="Optimize-ready losses, constraints, readiness, and outcomes" value={optimize.data}>{mode === "overview" && <div className="product-grid"><ProductColumn consumer="Produce" title={t("products.executionFacts")} icon={<Factory size={22} />} product={produce.data} /><ProductColumn consumer="Optimize" title={t("products.decisionContext")} icon={<Gauge size={22} />} product={optimize.data} /></div>}{mode === "produce" && <ProduceMode product={produce.data} />}{mode === "optimize" && <OptimizeMode product={optimize.data} />}</Agent.Data></Agent.Data></DataBoundary></Agent.Page>;
}

const PANELS: Record<string, ComponentType<{ apiBase: string; locale: Locale }>> = { live_operations: LiveOperations, event_timeline: EventTimeline, assets: Assets, data_health: DataHealth, data_products: DataProducts };

function PreferenceControls({ theme, locale, setTheme, setLocale }: { theme: MonitorTheme; locale: Locale; setTheme: (theme: MonitorTheme) => void; setLocale: (locale: Locale) => void }) {
  const { t } = useI18n();
  return <div className="preference-controls"><div className="segmented segmented--theme" role="group" aria-label={t("settings.appearance")}><button aria-label={t("settings.changeLight")} title={t("settings.changeLight")} aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Sun size={16} /><span>{t("settings.light")}</span></button><button aria-label={t("settings.changeDark")} title={t("settings.changeDark")} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Moon size={16} /><span>{t("settings.dark")}</span></button></div><div className="segmented segmented--locale" role="group" aria-label={t("settings.language")}><Languages size={16} aria-hidden="true" /><button aria-label={t("settings.changeEnglish")} aria-pressed={locale === "en"} onClick={() => setLocale("en")}>EN</button><button aria-label={t("settings.changeVietnamese")} aria-pressed={locale === "vi"} onClick={() => setLocale("vi")}>VI</button></div></div>;
}

function DashboardSurface({ apiBase, activeTab, theme, locale, setTheme, setLocale }: { apiBase: string; activeTab?: string | null; theme: MonitorTheme; locale: Locale; setTheme: (theme: MonitorTheme) => void; setLocale: (locale: Locale) => void }) {
  const { tokens } = useMinderTheme();
  const { t } = useI18n();
  const [tab, setTab] = useState(activeTab || TABS[0].id);
  const mainRef = useRef<HTMLElement>(null);
  const source = useTool<AnyRecord>(apiBase, "monitor_source_health");
  useEffect(() => { if (activeTab) setTab(activeTab); }, [activeTab]);
  const Panel = PANELS[tab] || LiveOperations;
  const selected = useMemo(() => TABS.find((item) => item.id === tab) || TABS[0], [tab]);
  const sourceLabel = source.status === "live" ? t("status.live") : source.status === "stale" ? t("status.stale") : source.status === "offline" ? t("status.offline") : t("status.loading");

  function navigate(next: string) {
    setTab(next);
    window.requestAnimationFrame(() => mainRef.current?.focus());
  }

  return <div className="monitor-shell" data-theme={theme} lang={locale} style={{ "--monitor-bg": tokens.bg, "--surface-sdk": tokens.surface, "--surface-alt-sdk": tokens.surfaceAlt, "--border-sdk": tokens.border, "--text-sdk": tokens.text, "--muted-sdk": tokens.textMuted, "--primary-sdk": tokens.primary, "--success-sdk": tokens.success, "--warning-sdk": tokens.warning, "--danger-sdk": tokens.error, "--shadow-sdk": tokens.cardShadow } as CSSProperties}><a className="skip-link" href="#monitor-main">{t("nav.skip")}</a><header className="monitor-header"><div className="brand-mark"><Activity size={22} aria-hidden="true" /></div><div className="brand-copy"><span>Monitor</span><small>{t("brand.subtitle")}</small></div><div className="scope-path" aria-label={t("scope.plant")}><span>{t("scope.plant")}</span><ChevronRight size={14} /><span>{t("scope.washers")}</span><ChevronRight size={14} /><strong>{t("scope.dryers")}</strong></div><PreferenceControls theme={theme} locale={locale} setTheme={setTheme} setLocale={setLocale} /><div className={`live-indicator live-indicator--${source.status}`}><span /><div><strong>{sourceLabel}</strong><small>{t("status.refresh")}</small></div></div></header><nav className="monitor-nav" aria-label={t("nav.label")}>{TABS.map((item) => { const Icon = ICONS[item.id]; return <button key={item.id} className={tab === item.id ? "active" : ""} aria-current={tab === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><Icon size={18} /><span>{t(`tab.${item.id}` as any)}</span></button>; })}</nav><main id="monitor-main" ref={mainRef} tabIndex={-1}><div className="mobile-view-title"><span>{t(`tab.${selected.id}` as any)}</span></div><Panel apiBase={apiBase} locale={locale} /></main><footer className="monitor-footer"><span><CheckCircle2 size={14} />{t("footer.readOnly")}</span><span><Clock3 size={14} />{t("footer.timestamps")}</span></footer></div>;
}

function Dashboard({ apiBase, activeTab, theme: hostTheme }: DashboardProps) {
  const preferences = useMonitorPreferences(hostTheme);
  return <MinderThemeProvider theme={preferences.theme}><I18nProvider locale={preferences.locale}><AgentDriverProvider apiBase={apiBase} onNavigate={(_route: string) => undefined}><AgentRegistryProvider apiBase={apiBase} sessionId="monitor"><DashboardSurface apiBase={apiBase} activeTab={activeTab} theme={preferences.theme} locale={preferences.locale} setTheme={preferences.setTheme} setLocale={preferences.setLocale} /></AgentRegistryProvider></AgentDriverProvider></I18nProvider></MinderThemeProvider>;
}

const withMeta = Dashboard as DashboardComponent;
withMeta.meta = { title: "Monitor · Operational truth", tabs: TABS.map((tab) => ({ ...tab })) };
export default withMeta;
