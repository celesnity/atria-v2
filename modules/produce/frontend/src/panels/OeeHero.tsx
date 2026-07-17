import { useState } from 'react';
import { Card, Group, RingProgress, Text, Stack, NumberInput, SimpleGrid } from '@mantine/core';
import { DonutChart } from '@mantine/charts';
import { useApi } from '../api';

export default function OeeHero({ apiBase }: { apiBase: string }) {
  const [shiftId, setShiftId] = useState(1);
  const [total, setTotal] = useState(400);
  const oee = useApi<Record<string, number> & { error?: string }>(apiBase, `/oee/shifts/${shiftId}?total_count=${total}`, [shiftId, total]);
  const d = oee.data ?? {};
  const pct = (v?: number) => Math.round((v ?? 0) * 100);
  const donut = [
    { name: 'Availability', value: pct(d.availability), color: 'cobalt.6' },
    { name: 'Performance', value: pct(d.performance), color: 'teal.6' },
    { name: 'Quality', value: pct(d.quality), color: 'grape.6' },
  ];
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" mb="md">
      <Group justify="space-between" mb="md" align="flex-end">
        <Text fw={700} fz={16}>OEE ca {shiftId}</Text>
        <Group gap="sm">
          <NumberInput label="Ca" value={shiftId} onChange={(v) => setShiftId(Number(v) || 1)} w={90} size="xs" hideControls />
          <NumberInput label="Sản lượng" value={total} onChange={(v) => setTotal(Number(v) || 0)} w={120} size="xs" hideControls />
        </Group>
      </Group>
      {d.error ? (
        <Text c="orange" size="sm">{d.error}</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xl">
          <Group justify="center">
            <RingProgress
              size={180}
              thickness={16}
              roundCaps
              sections={[{ value: pct(d.oee), color: 'cobalt.6' }]}
              label={<Text ta="center" fw={700} fz={30}>{pct(d.oee)}%</Text>}
            />
          </Group>
          <Stack justify="center" gap="xs">
            <DonutChart data={donut} withTooltip chartLabel="A×P×Q" size={150} thickness={22} />
          </Stack>
        </SimpleGrid>
      )}
    </Card>
  );
}
