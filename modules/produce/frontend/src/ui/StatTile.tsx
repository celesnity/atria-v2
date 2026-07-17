import type { ReactNode } from 'react';
import { Card, Group, Text, ThemeIcon } from '@mantine/core';

export default function StatTile({
  label,
  value,
  icon,
  color = 'cobalt',
  hint,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  color?: string;
  hint?: string;
}) {
  return (
    <Card
      withBorder
      radius="lg"
      padding="lg"
      shadow="sm"
      className="pr-stat"
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      {/* Faint accent glow anchored to the icon corner for depth. */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          top: -40,
          right: -40,
          width: 140,
          height: 140,
          borderRadius: '50%',
          background: `radial-gradient(circle, var(--mantine-color-${color}-1), transparent 70%)`,
          opacity: 0.7,
          pointerEvents: 'none',
        }}
      />
      <Group justify="space-between" align="flex-start" wrap="nowrap" style={{ position: 'relative' }}>
        <div style={{ minWidth: 0 }}>
          <Text
            size="xs"
            c="dimmed"
            tt="uppercase"
            fw={700}
            style={{ letterSpacing: '0.06em', fontSize: 11 }}
          >
            {label}
          </Text>
          <Text
            fw={800}
            fz={38}
            lh={1}
            mt={8}
            style={{ fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}
          >
            {value}
          </Text>
          {hint ? (
            <Text size="xs" c="dimmed" mt={6}>
              {hint}
            </Text>
          ) : null}
        </div>
        {icon ? (
          <ThemeIcon
            variant="gradient"
            gradient={{ from: `${color}.5`, to: `${color}.7`, deg: 135 }}
            size={46}
            radius="md"
            style={{ boxShadow: `0 6px 16px -6px var(--mantine-color-${color}-5)` }}
          >
            {icon}
          </ThemeIcon>
        ) : null}
      </Group>
    </Card>
  );
}
