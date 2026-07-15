import type { ReactNode } from 'react';
import { Card, Group, Divider, Title, Box } from '@mantine/core';

export default function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" mb="md">
      <Group justify="space-between" align="flex-end" wrap="nowrap" mb="sm">
        <Group gap={8} align="center" wrap="nowrap">
          <Box w={3} h={16} style={{ borderRadius: 2, background: 'var(--mantine-color-cobalt-6)' }} />
          <Title order={5}>{title}</Title>
        </Group>
        <Group gap={8} align="flex-end" wrap="wrap">{actions}</Group>
      </Group>
      <Divider mb="md" />
      {children}
    </Card>
  );
}
