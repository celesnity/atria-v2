import { useEffect, useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { apiClient } from '../api/client';
import { Eyebrow } from '../components/ui/Eyebrow';
import { AnimatedHeadline } from '../components/ui/AnimatedHeadline';
import { CosmicField } from '../components/ui/CosmicField';
import { MotionRise, transitions } from '../components/ui/motion';

type AuthMode = 'keycloak' | 'none' | 'loading';

// Capability spine for the trust marquee — plain nouns, no marketing cliches.
const CAPABILITIES = [
  'Canvas', 'Console', 'Collaborator', 'Plan mode', 'MCP servers',
  'Artifacts', 'Deep research', 'Personas', 'Dispatch', 'Modules',
];

export function LoginPage() {
  const [mode, setMode] = useState<AuthMode>('loading');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const reduce = useReducedMotion();

  useEffect(() => {
    apiClient
      .authMode()
      .then((m) => setMode(m.mode))
      .catch(() => setMode('none'));
  }, []);

  function handleSso() {
    setError('');
    setLoading(true);
    window.location.href = apiClient.keycloakLoginUrl('/chat');
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await apiClient.login(email);
      navigate('/chat', { replace: true });
    } catch (err: any) {
      setError(err.message ?? 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      data-surface="dark"
      className="surface-dark relative min-h-[100dvh] w-full overflow-hidden bg-canvas text-white"
    >
      {/* Cinematic cosmic backdrop — nebula wash + parallax starfield. */}
      <CosmicField wash count={60} />

      {/* Oversized editorial watermark — bleeds off the bottom-left, barely there. */}
      <span
        aria-hidden
        className="pointer-events-none absolute -bottom-24 -left-6 select-none font-sans leading-none text-white/[0.04]"
        style={{ fontSize: 'clamp(180px, 26vw, 420px)', fontWeight: 340, letterSpacing: '-0.05em' }}
      >
        Atria
      </span>

      {/* Top brand row. */}
      <div className="relative z-10 flex items-center justify-between px-8 md:px-14 lg:px-20 pt-8">
        <div className="flex items-baseline gap-3">
          <span className="text-[18px] font-[600] tracking-[-0.02em] text-white">Atria</span>
          <span className="eyebrow-mono text-white/40 hidden sm:inline">Build mode</span>
        </div>
        <Eyebrow className="!text-white/40">v1 · 2026</Eyebrow>
      </div>

      {/* Hero grid — editorial copy left, floating form card right. Asymmetric. */}
      <div className="relative z-10 mx-auto grid min-h-[calc(100dvh-13rem)] w-full max-w-content grid-cols-1 items-center gap-16 px-8 md:px-14 lg:grid-cols-[1.15fr_0.85fr] lg:px-20">
        {/* ── Attention: the headline ── */}
        <div className="max-w-2xl">
          <MotionRise>
            <Eyebrow className="!text-white/60">One editorial workspace</Eyebrow>
          </MotionRise>

          <AnimatedHeadline
            text={'Where the work\ntakes shape.'}
            className="mt-6 max-w-[16ch] text-[48px] md:text-display-lg lg:text-display-xl font-sans font-[600] leading-[1.0] tracking-[-0.035em] text-white"
          />

          <motion.p
            initial={reduce ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.editorial, delay: 0.5 }}
            className="mt-8 max-w-md text-body-lg leading-[1.6] text-white/65"
          >
            A canvas, a console, and a collaborator. Reason across your codebase,
            dispatch work in parallel, and keep every artifact within reach.
          </motion.p>

          {/* Interest: quiet proof row — real capabilities, no fake stats. */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.editorial, delay: 0.68 }}
            className="mt-12 flex flex-wrap items-center gap-x-8 gap-y-4"
          >
            {[
              ['Plan · Normal', 'Two reasoning modes'],
              ['Parallel', 'Dispatch subagents'],
              ['MCP', 'Bring your own tools'],
            ].map(([big, small]) => (
              <div key={big} className="min-w-[7rem]">
                <div className="text-[22px] font-[600] tracking-[-0.02em] text-white">{big}</div>
                <div className="mt-1 text-body-sm text-white/45">{small}</div>
              </div>
            ))}
          </motion.div>
        </div>

        {/* ── Action: the glass auth card ── */}
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...transitions.editorial, delay: 0.3 }}
          className="relative w-full"
        >
          <div className="rounded-xl border border-white/12 bg-white/[0.04] p-8 backdrop-blur-xl shadow-cosmos md:p-10">
            <Eyebrow className="!text-white/55">Sign in</Eyebrow>

            {mode === 'loading' && (
              <div className="mt-8 space-y-3">
                <div className="skeleton-shimmer h-6 w-2/3 rounded-md opacity-30" />
                <div className="skeleton-shimmer h-4 w-full rounded-md opacity-20" />
                <div className="skeleton-shimmer mt-6 h-12 w-full rounded-pill opacity-20" />
              </div>
            )}

            {mode === 'keycloak' && (
              <>
                <h2 className="mt-4 text-headline font-[600] tracking-[-0.02em] text-white">
                  Continue with SSO
                </h2>
                <p className="mt-3 text-body-sm leading-[1.6] text-white/55">
                  Authenticate through your organization&rsquo;s identity provider,
                  then you&rsquo;ll land right back here.
                </p>

                <Eyebrow className="mt-10 block !text-white/40">
                  Identity provider · Keycloak
                </Eyebrow>

                {error && (
                  <p className="mt-3 text-body-sm font-[540] text-block-coral">{error}</p>
                )}

                <motion.button
                  type="button"
                  onClick={handleSso}
                  disabled={loading}
                  whileHover={reduce || loading ? undefined : { scale: 1.015 }}
                  whileTap={reduce || loading ? undefined : { scale: 0.98 }}
                  transition={transitions.tactile}
                  className="group mt-5 inline-flex w-full items-center justify-center gap-2 rounded-pill bg-gradient-brand px-6 py-[15px] text-btn text-white shadow-glow-nebula disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-[50%] border-2 border-white/40 border-t-white" />
                      <span>Redirecting</span>
                    </>
                  ) : (
                    <>
                      <span>Continue with Keycloak</span>
                      <ArrowRight className="h-4 w-4 transition-transform duration-base group-hover:translate-x-1" strokeWidth={2} />
                    </>
                  )}
                </motion.button>
              </>
            )}

            {mode === 'none' && (
              <>
                <h2 className="mt-4 text-headline font-[600] tracking-[-0.02em] text-white">
                  Continue with email
                </h2>
                <p className="mt-3 text-body-sm leading-[1.6] text-white/55">
                  Enter your address and we&rsquo;ll take you straight in. New
                  accounts are created automatically.
                </p>

                <form onSubmit={handleSubmit} className="mt-9">
                  <label className="block">
                    <Eyebrow className="mb-3 block !text-white/50">Email address</Eyebrow>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@studio.dev"
                      required
                      autoFocus
                      className="w-full rounded-sm border border-white/15 bg-white/[0.06] px-4 py-3 text-body-sm text-white placeholder:text-white/35 outline-none transition-shadow focus:border-accent-magenta focus:shadow-[0_0_0_3px_hsl(var(--accent-magenta)/0.35)]"
                    />
                  </label>

                  {error && (
                    <p className="mt-3 text-body-sm font-[540] text-block-coral">{error}</p>
                  )}

                  <motion.button
                    type="submit"
                    disabled={loading || !email}
                    whileHover={reduce || loading || !email ? undefined : { scale: 1.015 }}
                    whileTap={reduce || loading || !email ? undefined : { scale: 0.98 }}
                    transition={transitions.tactile}
                    className="group mt-8 inline-flex w-full items-center justify-center gap-2 rounded-pill bg-gradient-brand px-6 py-[15px] text-btn text-white shadow-glow-nebula disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {loading ? (
                      <>
                        <span className="h-4 w-4 animate-spin rounded-[50%] border-2 border-white/40 border-t-white" />
                        <span>Signing in</span>
                      </>
                    ) : (
                      <>
                        <span>Continue</span>
                        <ArrowRight className="h-4 w-4 transition-transform duration-base group-hover:translate-x-1" strokeWidth={2} />
                      </>
                    )}
                  </motion.button>
                </form>
              </>
            )}
          </div>
        </motion.div>
      </div>

      {/* Desire: continuous capability marquee — the workspace at a glance. */}
      <div className="relative z-10 mt-4 border-t border-white/10 py-6">
        <div className="flex overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
          <div className="flex shrink-0 animate-marquee items-center gap-10 pr-10">
            {[...CAPABILITIES, ...CAPABILITIES].map((c, i) => (
              <span key={i} className="whitespace-nowrap text-body-sm font-[500] tracking-[-0.01em] text-white/35">
                {c}
                <span className="ml-10 text-white/15">·</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
