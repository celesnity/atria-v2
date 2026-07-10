import type { HealthStatus } from '../../hooks/useModuleHealth';

const DOT_STYLES: Record<HealthStatus, { cls: string; label: string }> = {
  ok:      { cls: 'bg-green-500',   label: 'Service online' },
  down:    { cls: 'bg-red-500',     label: 'Service unreachable' },
  loading: { cls: 'bg-text-muted/50', label: 'Checking service…' },
};

/**
 * Small connector-health dot for a service-module tile. Renders nothing for a
 * non-service module (status undefined) so non-service tiles are untouched.
 */
export function ModuleHealthDot({
  status,
  className = '',
}: {
  status: HealthStatus | undefined;
  className?: string;
}) {
  if (!status) return null;
  const { cls, label } = DOT_STYLES[status];
  return (
    <span
      className={`inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full ${cls} ${className}`}
      title={label}
      aria-label={label}
    />
  );
}
