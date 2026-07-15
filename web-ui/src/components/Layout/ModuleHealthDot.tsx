import { useTranslation } from 'react-i18next';
import type { HealthStatus } from '../../hooks/useModuleHealth';

const DOT_STYLES: Record<HealthStatus, { cls: string; labelKey: string }> = {
  ok:      { cls: 'bg-green-500',     labelKey: 'moduleHealthDot.online' },
  down:    { cls: 'bg-red-500',       labelKey: 'moduleHealthDot.unreachable' },
  loading: { cls: 'bg-text-muted/50', labelKey: 'moduleHealthDot.checking' },
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
  const { t } = useTranslation('layout');
  if (!status) return null;
  const { cls, labelKey } = DOT_STYLES[status];
  const label = t(labelKey);
  return (
    <span
      className={`inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full ${cls} ${className}`}
      title={label}
      aria-label={label}
    />
  );
}
