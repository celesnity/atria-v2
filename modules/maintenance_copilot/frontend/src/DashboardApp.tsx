import { useEffect, useMemo, useRef, useState } from 'react';

interface DashboardProps {
  /** Connector public base, e.g. http://localhost:9200 — passed by the host. */
  apiBase: string;
}

type Health = 'checking' | 'online' | 'offline';

interface Citation {
  doc?: string;
  revision?: string;
  ata?: string;
  citation?: string;
  source_name?: string;
  page_number?: number | null;
  confidence_score?: number;
}

interface Passage {
  chunk_id?: string;
  text?: string;
  doc?: string;
  title?: string;
  ata?: string;
  revision?: string;
  source_name?: string;
  citation?: string;
  score?: number;
}

interface PipelineDoc { doc_type?: string; title?: string; revision?: string; ata?: string; chunks?: number; }
interface PipelineStats {
  collection?: string;
  total_chunks?: number;
  documents?: PipelineDoc[];
  embed_model?: string;
  embed_dim?: number;
  edges?: { ref?: number; hier?: number; semantic?: number; total?: number; ref_density?: number };
  graph?: { available?: boolean; nodes?: number; edges?: number };
  error?: string;
}

interface AnswerCard {
  answer?: string;
  answer_type?: string;
  exact_quote?: string;
  confidence_band?: 'high' | 'medium' | 'low';
  review_required?: boolean;
  advisory_note?: string;
  related_suggestions?: string[];
  citations?: Citation[];
  passages?: Passage[];
  validation_warnings?: string[];
}

const FONT = "'Outfit', ui-sans-serif, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
const INK = '#0f1222';
const MUTE = '#5b6178';
const FAINT = '#8a90a6';
const LINE = 'rgba(15,18,34,0.10)';
const ACCENT = '#4f46e5';
const LINK = '#1a56db';
const SURFACE = '#ffffff';
const PANEL = '#f6f7fb';

const BAND: Record<string, { label: string; fg: string; bg: string; dot: string }> = {
  high: { label: 'High confidence', fg: '#0f7a4f', bg: 'rgba(16,185,129,0.12)', dot: '#10b981' },
  medium: { label: 'Medium confidence', fg: '#9a6a00', bg: 'rgba(245,158,11,0.14)', dot: '#f59e0b' },
  low: { label: 'Low confidence', fg: '#b42318', bg: 'rgba(239,68,68,0.12)', dot: '#ef4444' },
};

const snippet = (t = '', n = 260) => (t.length > n ? t.slice(0, n).trimEnd() + '…' : t);
const sourceLabel = (p: Passage | Citation) =>
  (p as Passage).title || (p as any).source_name || (p as any).doc || 'Source';

export default function DashboardApp({ apiBase }: DashboardProps) {
  const [health, setHealth] = useState<Health>('checking');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);            // phase 1: retrieving passages
  const [loadingAnswer, setLoadingAnswer] = useState(false); // phase 2: AI overview
  const [passagesData, setPassagesData] = useState<AnswerCard | null>(null);
  const [card, setCard] = useState<AnswerCard | null>(null);
  const [focused, setFocused] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<'search' | 'corpus'>('search');
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [docTitle, setDocTitle] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!document.getElementById('mc-fonts')) {
      const link = document.createElement('link');
      link.id = 'mc-fonts';
      link.rel = 'stylesheet';
      link.href = 'https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap';
      document.head.appendChild(link);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    setHealth('checking');
    fetch(`${apiBase}/connector/health`)
      .then((r) => r.json())
      .then((h) => alive && setHealth(h?.ok ? 'online' : 'offline'))
      .catch(() => alive && setHealth('offline'));
    return () => { alive = false; };
  }, [apiBase]);

  const view = card || passagesData;
  const unavailable = useMemo(
    () => (view?.validation_warnings || []).some((w) => w.startsWith('service_unavailable')),
    [view],
  );

  async function run(apiAction: string, text: string) {
    const r = await fetch(`${apiBase}/connector/run`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: apiAction, args: { query: text } }),
    });
    return { ok: r.ok, data: await r.json() };
  }

  async function retrieve(query = q) {
    const text = query.trim();
    if (!text || loading) return;
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    setLoading(true);
    setLoadingAnswer(false);
    setCard(null);
    setPassagesData(null);
    setExpanded(false);
    try {
      // Phase 1 — passages first (fast, no LLM): show results immediately.
      const p = await run('passages', text);
      setPassagesData(p.ok ? p.data : { passages: [] });
      setLoading(false);
      // Phase 2 — AI overview (LLM synthesis): loads and appears after.
      setLoadingAnswer(true);
      const f = await run('retrieve', text);
      setCard(f.ok ? f.data : { answer: f.data?.detail || 'Request failed.', confidence_band: 'low' });
    } catch {
      setCard({ answer: 'Could not reach the copilot service.', confidence_band: 'low' });
    } finally {
      setLoading(false);
      setLoadingAnswer(false);
    }
  }

  async function loadStats() {
    setStatsLoading(true);
    try {
      const r = await fetch(`${apiBase}/connector/run`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action: 'pipeline_stats', args: {} }),
      });
      setStats(await r.json());
    } catch {
      setStats({ error: 'Could not load pipeline stats.' });
    } finally {
      setStatsLoading(false);
    }
  }

  function openTab(t: 'search' | 'corpus') {
    setTab(t);
    if (t === 'corpus' && !stats && !statsLoading) loadStats();
  }

  const dot = health === 'online' ? '#10b981' : health === 'offline' ? '#ef4444' : '#f59e0b';
  const statusLabel = health === 'online' ? 'Online' : health === 'offline' ? 'Offline' : 'Checking';
  const passages = view?.passages || [];
  const topSources = passages.slice(0, 3);
  const answerLong = (card?.answer || '').length > 520;
  const hasResults = !!card || !!passagesData;

  return (
    <div style={{ font: `400 15px/1.55 ${FONT}`, color: INK, background: PANEL, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <style>{`
        @keyframes mc-spin { to { transform: rotate(360deg); } }
        @keyframes mc-rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        @keyframes mc-shim { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .mc-btn { transition: transform .18s ease, box-shadow .18s ease, background .18s ease; }
        .mc-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 22px rgba(79,70,229,.30); }
        .mc-btn:active:not(:disabled) { transform: translateY(0); }
        .mc-chip { transition: background .15s ease, border-color .15s ease, color .15s ease; }
        .mc-sugg:hover { background: rgba(79,70,229,.06); border-color: rgba(79,70,229,.35); color: ${ACCENT}; }
        .mc-src { transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease; }
        .mc-src:hover { border-color: rgba(79,70,229,.35); box-shadow: 0 8px 22px rgba(15,18,34,.07); transform: translateY(-2px); }
        .mc-res { transition: background .15s ease; }
        .mc-res:hover { background: rgba(79,70,229,.035); }
        .mc-res:hover .mc-res-h { text-decoration: underline; }
        .mc-scroll::-webkit-scrollbar { width: 10px; }
        .mc-scroll::-webkit-scrollbar-thumb { background: rgba(15,18,34,.16); border-radius: 999px; border: 3px solid ${PANEL}; }
        @media (max-width: 760px){ .mc-top { grid-template-columns: 1fr !important; } .mc-hidesm { display: none !important; } }
      `}</style>

      {/* Command bar — fixed header of the flex column (does not scroll) */}
      <div style={{
        flexShrink: 0, zIndex: 30, background: PANEL,
        borderBottom: `1px solid ${LINE}`,
        padding: '20px clamp(16px, 4vw, 40px) 12px',
      }}>
        <div style={{ maxWidth: 1040, margin: '0 auto' }}>
          {/* Header title row */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
            <div>
              <h1 style={{ margin: 0, fontSize: 'clamp(1.2rem, 1.5vw, 1.5rem)', fontWeight: 700, letterSpacing: '-0.02em' }}>Maintenance Copilot</h1>
              <p style={{ margin: '5px 0 0', color: MUTE, fontSize: 13.5 }}>Grounded AMM / MEL / CDL / TSM retrieval — advisory only.</p>
            </div>
            <StatusPill dot={dot} label={statusLabel} />
          </div>

          {/* Search bar (always visible) */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'stretch', background: SURFACE, border: `1px solid ${focused ? ACCENT : LINE}`, borderRadius: 999, padding: '6px 6px 6px 16px', boxShadow: focused ? `0 0 0 4px ${ACCENT}1e` : '0 1px 3px rgba(15,18,34,.06)', transition: 'border-color .15s ease, box-shadow .15s ease' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" style={{ alignSelf: 'center', flexShrink: 0 }} stroke={FAINT} strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => { if (e.key === 'Enter') retrieve(); if (e.key === 'Escape') { setQ(''); } }}
              placeholder="Search the manuals — APU inoperative dispatch, ATA 32 procedure…"
              style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', font: `400 15px/1.4 ${FONT}`, color: INK, padding: '9px 4px' }}
            />
            <button className="mc-btn" onClick={() => retrieve()} disabled={!q.trim() || loading} style={{ border: 'none', borderRadius: 999, padding: '0 24px', font: `600 14px ${FONT}`, color: '#fff', background: !q.trim() || loading ? '#a5a9c4' : ACCENT, cursor: !q.trim() || loading ? 'default' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}>
              {loading && <span style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,.55)', borderTopColor: '#fff', borderRadius: 999, animation: 'mc-spin .7s linear infinite' }} />}
              {loading ? 'Searching' : 'Search'}
            </button>
          </div>

          {/* Tabs */}
          <div style={{ display: 'flex', gap: 4, marginTop: 12 }}>
            {(['search', 'corpus'] as const).map((t) => (
              <button key={t} onClick={() => openTab(t)} style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: '7px 4px', marginRight: 12, font: `600 13px ${FONT}`, color: tab === t ? INK : FAINT, borderBottom: `2px solid ${tab === t ? ACCENT : 'transparent'}`, transition: 'color .15s ease, border-color .15s ease' }}>
                {t === 'search' ? 'Search' : 'Corpus & Pipeline'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Scrollable body — the flex-1 scroll region (guaranteed to scroll) */}
      <div ref={scrollRef} className="mc-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <div style={{ maxWidth: 1040, margin: '0 auto', padding: '22px clamp(16px, 4vw, 40px) 56px' }}>
        {tab === 'corpus' && <CorpusView stats={stats} loading={statsLoading} onReload={loadStats} onOpen={setDocTitle} />}
        {tab === 'search' && !hasResults && !loading && (
          <div style={{ padding: '56px 24px', textAlign: 'center', color: FAINT, background: SURFACE, border: `1px dashed ${LINE}`, borderRadius: 18 }}>
            <div style={{ fontSize: 15.5, color: MUTE, fontWeight: 600 }}>Ask a maintenance question</div>
            <div style={{ fontSize: 13, marginTop: 6 }}>You get an AI overview, the source document, and the matching passages — all cited.</div>
          </div>
        )}

        {tab === 'search' && loading && (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: MUTE, background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 18 }}>
            <span style={{ display: 'inline-block', width: 22, height: 22, border: `2.5px solid ${LINE}`, borderTopColor: ACCENT, borderRadius: 999, animation: 'mc-spin .7s linear infinite' }} />
            <div style={{ marginTop: 12, fontSize: 13.5 }}>Retrieving from the manuals…</div>
          </div>
        )}

        {tab === 'search' && unavailable && (
          <div style={{ background: SURFACE, border: `1px solid ${LINE}`, borderLeft: '3px solid #ef4444', borderRadius: 16, padding: '16px 20px', animation: 'mc-rise .3s ease both' }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 8 }}>Retrieval service offline</div>
            <p style={{ margin: 0, color: '#7a2620', fontSize: 14 }}>{card.answer}</p>
            <p style={{ margin: '10px 0 0', color: '#9a6a00', fontSize: 12.5 }}>Do not fall back to reading the manuals directly.</p>
          </div>
        )}

        {tab === 'search' && hasResults && !unavailable && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 22, animation: 'mc-rise .3s ease both' }}>
            <div className="mc-top" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.7fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
              {/* AI Overview — real once synthesized; skeleton while it generates (phase 2) */}
              {card ? (
              <section style={{ background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 20, overflow: 'hidden', boxShadow: '0 8px 30px rgba(15,18,34,.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '16px 22px 10px' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}><Sparkle /><span style={{ fontSize: 14.5, fontWeight: 600 }}>AI Overview</span></span>
                  {card.confidence_band && (
                    <span className="mc-chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 11px', borderRadius: 999, fontSize: 12, fontWeight: 600, color: BAND[card.confidence_band].fg, background: BAND[card.confidence_band].bg }}>
                      <span style={{ width: 6, height: 6, borderRadius: 999, background: BAND[card.confidence_band].dot }} />{BAND[card.confidence_band].label}
                    </span>
                  )}
                </div>

                {card.review_required && (
                  <div style={{ margin: '0 22px 10px', padding: '10px 13px', borderRadius: 11, background: 'rgba(239,68,68,.07)', color: '#b42318', fontSize: 12.5, fontWeight: 500 }}>
                    Mandatory manual review — verify against the approved manuals before any dispatch decision.
                  </div>
                )}

                <div style={{ padding: '0 22px 8px' }}>
                  <p style={{ margin: 0, fontSize: 16, lineHeight: 1.72, color: INK, whiteSpace: 'pre-wrap', maxHeight: answerLong && !expanded ? 150 : undefined, overflow: 'hidden', maskImage: answerLong && !expanded ? 'linear-gradient(#000 68%, transparent)' : undefined, WebkitMaskImage: answerLong && !expanded ? 'linear-gradient(#000 68%, transparent)' : undefined }}>
                    {card.answer}
                  </p>
                </div>

                {answerLong && (
                  <button onClick={() => setExpanded((v) => !v)} style={{ margin: '4px 22px 10px', padding: '8px 18px', border: `1px solid ${LINE}`, borderRadius: 999, background: 'transparent', color: ACCENT, font: `600 13px ${FONT}`, cursor: 'pointer' }}>
                    {expanded ? 'Show less' : 'Show more'}
                  </button>
                )}

                {!!card.related_suggestions?.length && (
                  <div style={{ padding: '12px 22px 8px', borderTop: `1px solid ${LINE}`, marginTop: 8 }}>
                    <div style={{ fontSize: 12, color: FAINT, marginBottom: 10 }}>People also ask</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {card.related_suggestions.map((s, i) => (
                        <button key={i} className="mc-sugg mc-chip" onClick={() => { setQ(s); retrieve(s); }} style={{ padding: '8px 14px', border: `1px solid ${LINE}`, borderRadius: 999, background: PANEL, color: MUTE, font: `500 12.5px ${FONT}`, cursor: 'pointer', textAlign: 'left' }}>{s}</button>
                      ))}
                    </div>
                  </div>
                )}

                <div style={{ padding: '12px 22px', borderTop: `1px solid ${LINE}`, background: PANEL, fontSize: 12, fontStyle: 'italic', color: FAINT }}>
                  {card.advisory_note || 'Advisory only — a licensed engineer makes and signs every dispatch decision.'}
                </div>
              </section>
              ) : (
              <section style={{ background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 20, padding: '20px 22px', boxShadow: '0 8px 30px rgba(15,18,34,.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}><Sparkle /><span style={{ fontSize: 14.5, fontWeight: 600 }}>AI Overview</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: MUTE, marginBottom: 14 }}>
                  <span style={{ width: 16, height: 16, border: `2px solid ${LINE}`, borderTopColor: ACCENT, borderRadius: 999, animation: 'mc-spin .7s linear infinite' }} />
                  <span style={{ fontSize: 14 }}>Generating overview from the sources…</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {[95, 88, 92, 70].map((w, i) => (
                    <div key={i} style={{ height: 11, width: `${w}%`, borderRadius: 6, background: 'linear-gradient(90deg, rgba(15,18,34,.05), rgba(15,18,34,.11), rgba(15,18,34,.05))', backgroundSize: '200% 100%', animation: 'mc-shim 1.3s ease-in-out infinite' }} />
                  ))}
                </div>
              </section>
              )}

              {/* Source document */}
              <aside style={{ position: 'sticky', top: 92, background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 20, padding: '14px 16px', boxShadow: '0 8px 30px rgba(15,18,34,.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}><DocIcon /><span style={{ fontSize: 13, fontWeight: 600 }}>{topSources.length} source{topSources.length === 1 ? '' : 's'}</span></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {topSources.map((p, i) => (
                    <div key={i} className="mc-src" onClick={() => p.title && setDocTitle(p.title)} style={{ padding: '12px 13px', border: `1px solid ${LINE}`, borderRadius: 13, cursor: p.title ? 'pointer' : 'default' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                        <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', color: ACCENT, background: 'rgba(79,70,229,.10)', padding: '2px 7px', borderRadius: 6 }}>{p.doc || 'DOC'}</span>
                        {p.ata && <span style={{ fontSize: 11.5, color: FAINT }}>ATA {p.ata}</span>}
                        {p.revision && <span style={{ fontSize: 11.5, color: FAINT }}>· rev {p.revision}</span>}
                      </div>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: INK, lineHeight: 1.35 }}>{sourceLabel(p)}</div>
                      <p style={{ margin: '5px 0 0', fontSize: 12.5, lineHeight: 1.5, color: MUTE }}>{snippet(p.text, 150)}</p>
                    </div>
                  ))}
                  {!topSources.length && <div style={{ fontSize: 13, color: FAINT }}>No source documents matched.</div>}
                </div>
              </aside>
            </div>

            {/* Retrieved passages */}
            {!!passages.length && (
              <section>
                <div style={{ fontSize: 12.5, fontWeight: 600, letterSpacing: '.04em', textTransform: 'uppercase', color: FAINT, margin: '2px 2px 12px' }}>Retrieved passages · {passages.length}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {passages.map((p, i) => (
                    <div key={i} className="mc-res" onClick={() => p.title && setDocTitle(p.title)} style={{ padding: '15px 16px', borderRadius: 13, background: SURFACE, border: '1px solid transparent', cursor: p.title ? 'pointer' : 'default' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: MUTE, marginBottom: 3 }}>
                        <DocDot />
                        <span style={{ fontWeight: 600, color: '#3a3f57' }}>{p.doc || 'DOC'}</span>
                        {p.ata && <span>· ATA {p.ata}</span>}
                        {p.revision && <span>· rev {p.revision}</span>}
                        {typeof p.score === 'number' && <span style={{ marginLeft: 'auto', fontSize: 11.5, fontVariantNumeric: 'tabular-nums', color: FAINT, fontWeight: 600 }}>match {Math.round(p.score * 100)}%</span>}
                      </div>
                      <div className="mc-res-h" style={{ fontSize: 16, color: LINK, fontWeight: 500, lineHeight: 1.3 }}>{p.citation || sourceLabel(p)}</div>
                      <p style={{ margin: '5px 0 0', fontSize: 13.5, lineHeight: 1.6, color: '#3a3f57' }}>{snippet(p.text, 300)}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
        </div>
      </div>
      {docTitle && <DocumentModal apiBase={apiBase} title={docTitle} onClose={() => setDocTitle(null)} />}
    </div>
  );
}

function StatusPill({ dot, label, compact }: { dot: string; label: string; compact?: boolean }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: compact ? '5px 10px' : '6px 12px', borderRadius: 999, background: compact ? 'transparent' : SURFACE, border: compact ? 'none' : `1px solid ${LINE}`, fontSize: 12.5, fontWeight: 500, color: MUTE, whiteSpace: 'nowrap' }}>
      <span style={{ width: 8, height: 8, borderRadius: 999, background: dot, boxShadow: `0 0 0 3px ${dot}22` }} />{label}
    </span>
  );
}

interface DocData { title?: string; doc_type?: string; ata?: string; revision?: string; chunk_count?: number; chunks?: { chunk_id?: string; text?: string; citation?: string }[]; error?: string; }

function DocumentModal({ apiBase, title, onClose }: { apiBase: string; title: string; onClose: () => void }) {
  const [doc, setDoc] = useState<DocData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(`${apiBase}/connector/run`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'document', args: { title } }),
    })
      .then((r) => r.json())
      .then((d) => alive && setDoc(d))
      .catch(() => alive && setDoc({ error: 'Could not load document.' }))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [apiBase, title]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(15,18,34,.42)', backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'clamp(12px, 4vw, 48px)', animation: 'mc-rise .2s ease both' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: 'min(820px, 100%)', maxHeight: '86vh', display: 'flex', flexDirection: 'column', background: SURFACE, borderRadius: 20, overflow: 'hidden', boxShadow: '0 30px 80px rgba(15,18,34,.35)' }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, padding: '18px 22px', borderBottom: `1px solid ${LINE}` }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', color: ACCENT, background: 'rgba(79,70,229,.10)', padding: '3px 8px', borderRadius: 6 }}>{doc?.doc_type || 'DOC'}</span>
              {doc?.ata && <span style={{ fontSize: 12, color: FAINT }}>ATA {doc.ata}</span>}
              {doc?.revision && <span style={{ fontSize: 12, color: FAINT }}>· {doc.revision}</span>}
              {typeof doc?.chunk_count === 'number' && <span style={{ fontSize: 12, color: FAINT }}>· {doc.chunk_count} chunks</span>}
            </div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: '-0.01em', color: INK }}>{title}</h2>
          </div>
          <button onClick={onClose} aria-label="Close" style={{ flexShrink: 0, width: 34, height: 34, borderRadius: 10, border: `1px solid ${LINE}`, background: PANEL, color: MUTE, cursor: 'pointer', font: '18px/1 sans-serif' }}>×</button>
        </div>

        <div className="mc-scroll" style={{ overflowY: 'auto', padding: '20px 22px 26px' }}>
          {loading && (
            <div style={{ padding: '48px', textAlign: 'center', color: MUTE }}>
              <span style={{ display: 'inline-block', width: 22, height: 22, border: `2.5px solid ${LINE}`, borderTopColor: ACCENT, borderRadius: 999, animation: 'mc-spin .7s linear infinite' }} />
              <div style={{ marginTop: 12, fontSize: 13.5 }}>Loading source document…</div>
            </div>
          )}
          {!loading && doc?.error && <div style={{ color: '#b42318', fontSize: 14 }}>{doc.error}</div>}
          {!loading && !doc?.error && (doc?.chunks || []).map((c, i) => (
            <div key={i} style={{ padding: '2px 0 16px', borderBottom: i < (doc?.chunks?.length || 0) - 1 ? `1px solid ${LINE}` : 'none', marginBottom: 16 }}>
              {c.citation && <div style={{ fontSize: 11.5, fontFamily: 'ui-monospace, Menlo, monospace', color: FAINT, marginBottom: 6 }}>{c.citation}</div>}
              <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.72, color: '#25293c', whiteSpace: 'pre-wrap' }}>{c.text}</p>
            </div>
          ))}
          {!loading && !doc?.error && !(doc?.chunks || []).length && <div style={{ color: FAINT, fontSize: 14 }}>No content found for this document.</div>}
        </div>
      </div>
    </div>
  );
}

function CorpusView({ stats, loading, onReload, onOpen }: { stats: PipelineStats | null; loading: boolean; onReload: () => void; onOpen: (title: string) => void }) {
  if (loading && !stats) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center', color: MUTE, background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 18 }}>
        <span style={{ display: 'inline-block', width: 22, height: 22, border: `2.5px solid ${LINE}`, borderTopColor: ACCENT, borderRadius: 999, animation: 'mc-spin .7s linear infinite' }} />
        <div style={{ marginTop: 12, fontSize: 13.5 }}>Loading pipeline stats…</div>
      </div>
    );
  }
  const s = stats || {};
  const e = s.edges || {};
  const g = s.graph || {};
  const docs = s.documents || [];
  const stages = [
    { name: 'Parse', value: docs.length, unit: 'docs' },
    { name: 'Chunk', value: s.total_chunks ?? 0, unit: 'chunks' },
    { name: 'Embed', value: s.embed_dim ?? 0, unit: 'dim' },
    { name: 'Index', value: s.total_chunks ?? 0, unit: 'vectors' },
    { name: 'Graph', value: e.total ?? 0, unit: 'edges' },
  ];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, animation: 'mc-rise .3s ease both' }}>
      {s.error && <div style={{ padding: '12px 16px', borderRadius: 12, background: 'rgba(239,68,68,.08)', color: '#b42318', fontSize: 13 }}>{s.error}</div>}

      {/* Pipeline stages */}
      <section style={{ background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 18, padding: '18px 20px', boxShadow: '0 6px 24px rgba(15,18,34,.05)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Ingestion pipeline</span>
          <button onClick={onReload} style={{ border: `1px solid ${LINE}`, borderRadius: 999, background: 'transparent', color: ACCENT, font: `600 12px ${FONT}`, padding: '6px 14px', cursor: 'pointer' }}>Refresh</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
          {stages.map((st, i) => (
            <div key={st.name} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{ minWidth: 92, textAlign: 'center', padding: '12px 14px', borderRadius: 14, background: PANEL, border: `1px solid ${LINE}` }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: INK, fontVariantNumeric: 'tabular-nums' }}>{st.value}</div>
                <div style={{ fontSize: 11, color: FAINT, marginTop: 2 }}>{st.unit}</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: ACCENT, marginTop: 4 }}>{st.name}</div>
              </div>
              {i < stages.length - 1 && <span style={{ color: FAINT, fontSize: 16 }}>→</span>}
            </div>
          ))}
        </div>
      </section>

      {/* Index + edges + graph stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <StatCard title="Vector index" rows={[['Collection', s.collection || '—'], ['Chunks', String(s.total_chunks ?? 0)], ['Embed model', s.embed_model || '—'], ['Dimension', String(s.embed_dim ?? '—')]]} />
        <StatCard title="Deterministic edges (G1)" rows={[['ref (cross-ref)', String(e.ref ?? 0)], ['hier (parent/child)', String(e.hier ?? 0)], ['semantic (kNN)', String(e.semantic ?? 0)], ['ref density', String(e.ref_density ?? '—')]]} />
        <StatCard title="Knowledge graph" rows={g.available ? [['Nodes', String(g.nodes ?? 0)], ['Edges', String(g.edges ?? 0)], ['Status', 'connected']] : [['Status', 'not connected']]} />
      </div>

      {/* Documents */}
      <section>
        <div style={{ fontSize: 12.5, fontWeight: 600, letterSpacing: '.04em', textTransform: 'uppercase', color: FAINT, margin: '2px 2px 12px' }}>Ingested documents · {docs.length}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {docs.map((d, i) => (
            <div key={i} className="mc-src" onClick={() => d.title && onOpen(d.title)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 16px', background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 12, cursor: d.title ? 'pointer' : 'default' }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', color: ACCENT, background: 'rgba(79,70,229,.10)', padding: '3px 8px', borderRadius: 6, flexShrink: 0 }}>{d.doc_type || 'DOC'}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.title || 'Untitled'}</div>
                <div style={{ fontSize: 12, color: FAINT, marginTop: 2 }}>{d.ata ? `ATA ${d.ata}` : ''}{d.revision ? `  ·  ${d.revision}` : ''}</div>
              </div>
              <span style={{ fontSize: 13, fontWeight: 600, color: MUTE, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{d.chunks ?? 0} chunks</span>
            </div>
          ))}
          {!docs.length && <div style={{ padding: '40px 24px', textAlign: 'center', color: FAINT, background: SURFACE, border: `1px dashed ${LINE}`, borderRadius: 16, fontSize: 13.5 }}>No documents indexed yet. Drop files in the ingest folder and restart the module.</div>}
        </div>
      </section>
    </div>
  );
}

function StatCard({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div style={{ background: SURFACE, border: `1px solid ${LINE}`, borderRadius: 16, padding: '14px 16px' }}>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: INK, marginBottom: 10 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {rows.map(([label, val], i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
            <span style={{ fontSize: 12.5, color: MUTE }}>{label}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: INK, fontVariantNumeric: 'tabular-nums', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60%' }}>{val}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Sparkle() {
  return (
    <span style={{ width: 22, height: 22, borderRadius: 7, background: 'linear-gradient(135deg, #6366f1, #a855f7)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 3px 10px rgba(124,58,237,.35)' }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="#fff"><path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2z" /></svg>
    </span>
  );
}

function DocIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={ACCENT} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></svg>;
}

function DocDot() {
  return <span style={{ width: 16, height: 16, borderRadius: 5, background: 'rgba(79,70,229,.12)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke={ACCENT} strokeWidth="2.4"><path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z" /></svg></span>;
}
