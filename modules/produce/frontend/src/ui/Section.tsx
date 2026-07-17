import type { ReactNode } from 'react';
import { Card, Group, Title, Box } from '@mantine/core';

export default function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" mb="md" className="pr-section">
      <Group justify="space-between" align="flex-start" wrap="wrap" mb="xs" gap="sm">
        <Group gap={12} align="center" wrap="nowrap" style={{ flex: '1 1 220px', minWidth: 0 }}>
          <Box
            w={5}
            h={22}
            style={{
              borderRadius: 5,
              flexShrink: 0,
              background: 'linear-gradient(180deg, var(--mantine-color-cobalt-4), var(--mantine-color-cobalt-7))',
              boxShadow: '0 4px 10px -4px var(--mantine-color-cobalt-5)',
            }}
          />
          <Title order={4} style={{ letterSpacing: '-0.015em', lineHeight: 1.2 }}>
            {title}
          </Title>
        </Group>
        <Group gap={8} align="flex-end" wrap="wrap" style={{ flexShrink: 0, justifyContent: 'flex-end' }}>{actions}</Group>
      </Group>
      {/* Gradient hairline: crisp near the accent, fading into the surface. */}
      <Box
        mb="md"
        style={{
          height: 1,
          background:
            'linear-gradient(90deg, color-mix(in srgb, var(--pr-accent) 45%, transparent), var(--pr-border) 40%, transparent)',
        }}
      />
      {children}
    </Card>
  );
}
