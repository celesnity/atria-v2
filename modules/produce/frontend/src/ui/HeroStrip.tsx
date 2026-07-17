import { Group, Text, Badge } from '@mantine/core';

export interface HeroMetric {
  label: string;
  value: string | number;
}

/**
 * Gradient welcome banner for a persona overview page. Carries shift context
 * (operator, date, live status) and a row of inline mini-metrics so the top of
 * the page reads as a briefing rather than an empty header. Styling lives in
 * `.pr-hero` (dashboard GlobalStyle).
 */
export default function HeroStrip({
  eyebrow,
  title,
  subtitle,
  status = 'online',
  metrics = [],
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  status?: 'online' | 'idle';
  metrics?: HeroMetric[];
}) {
  return (
    <div className="pr-hero">
      <div className="pr-hero-glow" aria-hidden />
      <div className="pr-hero-body">
        <div style={{ minWidth: 0 }}>
          <Group gap={8} align="center" mb={6}>
            <Text className="pr-hero-eyebrow">{eyebrow}</Text>
            <Badge
              size="sm"
              radius="sm"
              variant="light"
              color={status === 'online' ? 'teal' : 'gray'}
              className="pr-hero-status"
            >
              <span className="pr-hero-dot" data-status={status} /> {status === 'online' ? 'Đang trực tuyến' : 'Nghỉ'}
            </Badge>
          </Group>
          <Text className="pr-hero-title">{title}</Text>
          {subtitle ? <Text className="pr-hero-sub">{subtitle}</Text> : null}
        </div>
        {metrics.length ? (
          <div className="pr-hero-metrics">
            {metrics.map((m) => (
              <div key={m.label} className="pr-hero-metric">
                <Text className="pr-hero-metric-value">{m.value}</Text>
                <Text className="pr-hero-metric-label">{m.label}</Text>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
