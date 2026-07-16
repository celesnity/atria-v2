import { useState } from 'react';
import { SimpleGrid, Group, Text } from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { useApi } from '../api';
import ChartCard from '../ui/ChartCard';
import { LineSelect, ShiftSelect } from '../ui/selects';

export default function ManagerCharts({ apiBase }: { apiBase: string }) {
  const [lineId, setLineId] = useState(2);
  const [shiftId, setShiftId] = useState(1);
  const why = useApi<{ top_downtime_reasons: Array<Record<string, unknown>>; scrap_by_station: Array<Record<string, unknown>> }>(
    apiBase, `/report/why-late/${lineId}?shift_id=${shiftId}`, [lineId, shiftId],
  );
  const reasons = (why.data?.top_downtime_reasons ?? []).map((r) => ({ category: String(r.category), count: Number(r.count) }));
  const scrap = (why.data?.scrap_by_station ?? []).map((r) => ({ station: `S${r.station_id}`, scrap: Number(r.scrap) }));

  return (
    <>
      <Group mb="md" gap="sm" align="flex-end">
        <LineSelect apiBase={apiBase} value={lineId} onChange={setLineId} w={200} />
        <ShiftSelect apiBase={apiBase} value={shiftId} onChange={setShiftId} lineId={lineId} />
      </Group>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <ChartCard title="Top lý do downtime">
          {reasons.length ? (
            <BarChart h={260} data={reasons} dataKey="category" series={[{ name: 'count', label: 'Số lần', color: 'cobalt.6' }]} tickLine="y" gridAxis="y" withBarValueLabel barProps={{ radius: 6 }} />
          ) : <Text c="dimmed" size="sm">Không có downtime.</Text>}
        </ChartCard>
        <ChartCard title="Phế phẩm theo station">
          {scrap.length ? (
            <BarChart h={260} data={scrap} dataKey="station" series={[{ name: 'scrap', label: 'Phế phẩm', color: 'red.6' }]} tickLine="y" gridAxis="y" withBarValueLabel barProps={{ radius: 6 }} />
          ) : <Text c="dimmed" size="sm">Không có phế phẩm.</Text>}
        </ChartCard>
      </SimpleGrid>
    </>
  );
}
