import { useState } from 'react';
import { SimpleGrid, NumberInput, Group, Text } from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { useApi } from '../api';
import ChartCard from '../ui/ChartCard';

export default function ManagerCharts({ apiBase }: { apiBase: string }) {
  const [lineId, setLineId] = useState(1);
  const [shiftId, setShiftId] = useState(1);
  const why = useApi<{ top_downtime_reasons: Array<Record<string, unknown>>; scrap_by_station: Array<Record<string, unknown>> }>(
    apiBase, `/report/why-late/${lineId}?shift_id=${shiftId}`, [lineId, shiftId],
  );
  const reasons = (why.data?.top_downtime_reasons ?? []).map((r) => ({ category: String(r.category), count: Number(r.count) }));
  const scrap = (why.data?.scrap_by_station ?? []).map((r) => ({ station: `S${r.station_id}`, scrap: Number(r.scrap) }));

  return (
    <>
      <Group mb="md" gap="sm">
        <NumberInput label="Line" value={lineId} onChange={(v) => setLineId(Number(v) || 1)} w={90} size="xs" hideControls />
        <NumberInput label="Ca" value={shiftId} onChange={(v) => setShiftId(Number(v) || 1)} w={90} size="xs" hideControls />
      </Group>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <ChartCard title="Top lý do downtime">
          {reasons.length ? (
            <BarChart h={240} data={reasons} dataKey="category" series={[{ name: 'count', color: 'cobalt.6' }]} />
          ) : <Text c="dimmed" size="sm">Không có downtime.</Text>}
        </ChartCard>
        <ChartCard title="Phế phẩm theo station">
          {scrap.length ? (
            <BarChart h={240} data={scrap} dataKey="station" series={[{ name: 'scrap', color: 'red.6' }]} />
          ) : <Text c="dimmed" size="sm">Không có phế phẩm.</Text>}
        </ChartCard>
      </SimpleGrid>
    </>
  );
}
