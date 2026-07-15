import type { ReactNode } from 'react';
import { Card, Group, Text, ThemeIcon } from '@mantine/core';

export default function StatTile({ label, value, icon, color = 'cobalt', hint }: { label: string; value: ReactNode; icon?: ReactNode; color?: string; hint?: string }) {
  return (
    <Card withBorder radius="lg" padding="md" shadow="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.04em' }}>{label}</Text>
          <Text fw={700} fz={26} lh={1.1} mt={4} style={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Text>
          {hint ? <Text size="xs" c="dimmed" mt={2}>{hint}</Text> : null}
        </div>
        {icon ? <ThemeIcon variant="light" color={color} size={38} radius="md">{icon}</ThemeIcon> : null}
      </Group>
    </Card>
  );
}
