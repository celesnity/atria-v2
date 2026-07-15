import { SimpleGrid, Grid, Stack } from '@mantine/core';
import { IconListCheck, IconClipboardCheck, IconAlertTriangle } from '@tabler/icons-react';
import { useApi } from '../api';
import StatTile from '../ui/StatTile';
import WorkPanel from '../panels/WorkPanel';
import SopPanel from '../panels/SopPanel';
import WipPanel from '../panels/WipPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ScrapPanel from '../panels/ScrapPanel';

export default function OperatorRoute({ apiBase }: { apiBase: string }) {
  const queue = useApi<Array<Record<string, unknown>>>(apiBase, '/work/queue/op1');
  const openDt = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/events/open');
  const q = queue.data ?? [];
  const running = q.filter((t) => t.status === 'in_progress').length;

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <StatTile label="Hàng đợi của tôi" value={q.length} icon={<IconListCheck size={20} />} hint="task chưa xong" />
        <StatTile label="Đang làm" value={running} color="green" icon={<IconClipboardCheck size={20} />} />
        <StatTile label="Downtime mở" value={(openDt.data ?? []).length} color="orange" icon={<IconAlertTriangle size={20} />} />
      </SimpleGrid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <WorkPanel apiBase={apiBase} mode="queue" />
          <SopPanel apiBase={apiBase} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <WipPanel apiBase={apiBase} />
          <DowntimePanel apiBase={apiBase} mode="log" />
          <ScrapPanel apiBase={apiBase} mode="record" />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
