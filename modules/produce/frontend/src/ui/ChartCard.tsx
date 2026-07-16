import type { ReactNode } from 'react';
import { Card, Group, Title, Box } from '@mantine/core';

export default function ChartCard({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" h="100%">
      <Group justify="space-between" mb="md" align="center">
        <Group gap={12} align="center" wrap="nowrap">
          <Box
            w={5}
            h={22}
            style={{
              borderRadius: 5,
              background: 'linear-gradient(180deg, var(--mantine-color-cobalt-4), var(--mantine-color-cobalt-7))',
              boxShadow: '0 4px 10px -4px var(--mantine-color-cobalt-5)',
            }}
          />
          <Title order={4} style={{ letterSpacing: '-0.015em' }}>{title}</Title>
        </Group>
        {actions}
      </Group>
      {children}
    </Card>
  );
}
