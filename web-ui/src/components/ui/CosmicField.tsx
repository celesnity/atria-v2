/**
 * CosmicField — the signature Celesnity ambient backdrop.
 *
 * A pointer-parallax starfield layered over two soft nebula blooms. Deterministic
 * star placement (no Math.random at render) so hydration is stable and the field
 * never reshuffles between paints. Respects prefers-reduced-motion: blooms hold
 * still, stars stop twinkling. Pure decoration — always aria-hidden, never
 * interactive. Reads only brand tokens (bg-gradient-brand, hairline), no raw hex.
 */

import { motion, useReducedMotion, useMotionValue, useSpring, useTransform } from 'motion/react';
import { useEffect, useMemo } from 'react';

interface CosmicFieldProps {
  /** Star density. Default 46 — enough to read as a sky, sparse enough to stay calm. */
  count?: number;
  /** Extra classes on the absolute wrapper. */
  className?: string;
  /** When true, adds the deep radial hero wash beneath the stars. */
  wash?: boolean;
}

// Deterministic pseudo-random — a tiny LCG seeded per-star so the sky is fixed.
function seeded(i: number, salt: number): number {
  const x = Math.sin(i * 928.371 + salt * 13.17) * 43758.5453;
  return x - Math.floor(x);
}

export function CosmicField({ count = 46, className = '', wash = false }: CosmicFieldProps) {
  const reduce = useReducedMotion();

  // Pointer parallax — the star layer drifts a few px against cursor movement.
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 40, damping: 20 });
  const sy = useSpring(py, { stiffness: 40, damping: 20 });
  const driftX = useTransform(sx, (v) => v * 14);
  const driftY = useTransform(sy, (v) => v * 14);

  useEffect(() => {
    if (reduce) return;
    const onMove = (e: PointerEvent) => {
      px.set(e.clientX / window.innerWidth - 0.5);
      py.set(e.clientY / window.innerHeight - 0.5);
    };
    window.addEventListener('pointermove', onMove);
    return () => window.removeEventListener('pointermove', onMove);
  }, [px, py, reduce]);

  const stars = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => ({
        left: `${(seeded(i, 1) * 100).toFixed(2)}%`,
        top: `${(seeded(i, 2) * 100).toFixed(2)}%`,
        size: 0.8 + seeded(i, 3) * 2.2,
        delay: seeded(i, 4) * 4,
        dur: 2.6 + seeded(i, 5) * 3.4,
        base: 0.15 + seeded(i, 6) * 0.5,
      })),
    [count],
  );

  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      {wash && <div className="absolute inset-0 bg-hero-wash" />}

      {/* Two nebula blooms — the brand gradient, blurred off-canvas. */}
      <div className="absolute -top-32 -left-24 w-[34rem] h-[34rem] rounded-full bg-gradient-brand opacity-30 blur-[120px]" />
      <div className="absolute -bottom-40 -right-24 w-[30rem] h-[30rem] rounded-full bg-gradient-brand opacity-20 blur-[120px]" />

      {/* Parallax star layer. */}
      <motion.div className="absolute inset-0" style={reduce ? undefined : { x: driftX, y: driftY }}>
        {stars.map((s, i) => (
          <motion.span
            key={i}
            className="absolute rounded-full bg-ink"
            style={{ left: s.left, top: s.top, width: s.size, height: s.size }}
            initial={{ opacity: s.base }}
            animate={reduce ? { opacity: s.base } : { opacity: [s.base, Math.min(1, s.base + 0.45), s.base] }}
            transition={reduce ? undefined : { duration: s.dur, delay: s.delay, repeat: Infinity, ease: 'easeInOut' }}
          />
        ))}
      </motion.div>
    </div>
  );
}
