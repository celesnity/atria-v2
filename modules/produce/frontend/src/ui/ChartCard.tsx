import type { ReactNode } from 'react';
import { Card, Group, Title, Box } from '@mantine/core';

export default function ChartCard({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" h="100%">
      <Group justify="space-between" mb="md" align="flex-end">
        <Group gap={8} align="center" wrap="nowrap">
          <Box w={3} h={16} style={{ borderRadius: 2, background: 'var(--mantine-color-cobalt-6)' }} />
          <Title order={5}>{title}</Title>
        </Group>
        {actions}
      </Group>
      {children}
    </Card>
  );
}
