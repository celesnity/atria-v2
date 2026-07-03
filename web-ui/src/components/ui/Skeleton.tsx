import React from 'react';
import { cn } from '../../lib/cn';

/**
 * Skeleton — the app-wide loading placeholder. Wraps the Celesnity
 * `.skeleton-shimmer` treatment so every surface reserves layout space with the
 * same quiet shimmer instead of a blank flash (fixes content-jumping globally).
 *
 * The shimmer animation is collapsed automatically under
 * `prefers-reduced-motion` via the global rule in index.css.
 */
interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Shape preset. `text` is a short line; `block` a rounded panel; `circle` an avatar. */
  variant?: 'text' | 'block' | 'circle';
}

const SHAPES: Record<NonNullable<SkeletonProps['variant']>, string> = {
  text:   'h-3.5 rounded-md',
  block:  'h-16 rounded-xl',
  circle: 'rounded-full aspect-square',
};

export function Skeleton({ variant = 'block', className, ...rest }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn('skeleton-shimmer', SHAPES[variant], className)}
      {...rest}
    />
  );
}

/**
 * SkeletonList — N stacked block skeletons. The common "loading a list" case,
 * e.g. the sessions/workspaces sidebar or a file tree.
 */
export function SkeletonList({
  count = 3,
  className,
  itemClassName,
  label = 'Loading…',
}: {
  count?: number;
  className?: string;
  itemClassName?: string;
  /** Screen-reader status while the list loads. */
  label?: string;
}) {
  return (
    <div className={cn('space-y-3', className)} role="status" aria-busy="true" aria-label={label}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} variant="block" className={itemClassName} />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}
