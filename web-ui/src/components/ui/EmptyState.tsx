import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { MotionRise } from './motion';
import { cn } from '../../lib/cn';

/**
 * EmptyState — the app-wide "nothing here yet" panel. A centered icon medallion,
 * a title, a supporting line, and an optional action. Replaces ad-hoc empty
 * markup so every blank surface (sessions, files, chat, results) reads the same.
 */
interface EmptyStateProps {
  Icon: LucideIcon;
  title: string;
  description?: string;
  /** Optional call-to-action, e.g. a <Button>. */
  action?: React.ReactNode;
  /** Compact drops the medallion size + vertical padding for narrow rails. */
  size?: 'sm' | 'md';
  className?: string;
}

export function EmptyState({
  Icon,
  title,
  description,
  action,
  size = 'md',
  className,
}: EmptyStateProps) {
  const compact = size === 'sm';
  return (
    <MotionRise
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'py-10 px-4' : 'py-16 px-6',
        className,
      )}
    >
      <div
        className={cn(
          'rounded-[50%] bg-surface-soft flex items-center justify-center mb-4 text-text-muted',
          compact ? 'w-14 h-14' : 'w-16 h-16',
        )}
        aria-hidden="true"
      >
        <Icon className={compact ? 'w-7 h-7' : 'w-8 h-8'} strokeWidth={1.5} />
      </div>
      <h3 className="text-sm font-medium text-ink mb-1">{title}</h3>
      {description && (
        <p className="text-xs text-text-muted max-w-[240px] leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </MotionRise>
  );
}
