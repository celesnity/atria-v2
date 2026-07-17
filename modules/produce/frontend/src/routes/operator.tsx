import { useState } from 'react';
import { SimpleGrid, Grid, Stack } from '@mantine/core';
import {
  IconListCheck,
  IconClipboardCheck,
  IconAlertTriangle,
  IconLayoutDashboard,
  IconClipboardList,
  IconBuildingFactory2,
  IconGauge,
} from '@tabler/icons-react';
import { useApi } from '../api';
import StatTile from '../ui/StatTile';
import SubNav, { type SubTab } from '../ui/SubNav';
import HeroStrip from '../ui/HeroStrip';
import WorkPanel from '../panels/WorkPanel';
import SopPanel from '../panels/SopPanel';
import WipPanel from '../panels/WipPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ScrapPanel from '../panels/ScrapPanel';
import CommandCenter from '../panels/CommandCenter';

export default function OperatorRoute({ apiBase }: { apiBase: string }) {
  const [view, setView] = useState('overview');
  const queue = useApi<Array<Record<string, unknown>>>(apiBase, '/work/queue/op1');
  const openDt = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/events/open');
  const q = queue.data ?? [];
  const running = q.filter((t) => t.status === 'in_progress').length;
  const queued = q.filter((t) => t.status === 'queued').length;
  const openDowntime = (openDt.data ?? []).length;

  const tabs: SubTab[] = [
    { id: 'overview', label: 'Tổng quan', icon: <IconLayoutDashboard size={16} /> },
    { id: 'work', label: 'Công việc', icon: <IconClipboardList size={16} />, badge: q.length || undefined },
    { id: 'station', label: 'Trạm & WIP', icon: <IconBuildingFactory2 size={16} /> },
    { id: 'quality', label: 'Chất lượng & Downtime', icon: <IconAlertTriangle size={16} />, badge: openDowntime || undefined },
  ];

  return (
    <Stack gap="lg">
      <SubNav tabs={tabs} value={view} onChange={setView} />

      {view === 'overview' && (
        <Stack gap="md">
          <HeroStrip
            eyebrow="Ca sản xuất · Operator"
            title="Chào op1 — sẵn sàng vào ca"
            subtitle="Theo dõi hàng đợi, trạm và chất lượng trong một màn hình."
            status={running > 0 ? 'online' : 'idle'}
            metrics={[
              { label: 'Đang làm', value: running },
              { label: 'Hàng đợi', value: q.length },
              { label: 'Downtime mở', value: openDowntime },
            ]}
          />

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
            <StatTile label="Hàng đợi của tôi" value={q.length} icon={<IconListCheck size={22} />} hint="task chưa xong" />
            <StatTile label="Đang làm" value={running} color="green" icon={<IconClipboardCheck size={22} />} hint="đang thực hiện" />
            <StatTile label="Chờ nhận" value={queued} color="cobalt" icon={<IconGauge size={22} />} hint="chưa claim" />
            <StatTile label="Downtime mở" value={openDowntime} color="orange" icon={<IconAlertTriangle size={22} />} hint="cần xử lý" />
          </SimpleGrid>

          <CommandCenter apiBase={apiBase} />
        </Stack>
      )}

      {view === 'work' && (
        <Grid gutter="md" align="flex-start">
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <WorkPanel apiBase={apiBase} mode="queue" />
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <SopPanel apiBase={apiBase} />
          </Grid.Col>
        </Grid>
      )}

      {view === 'station' && <WipPanel apiBase={apiBase} />}

      {view === 'quality' && (
        <Grid gutter="md" align="flex-start">
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <DowntimePanel apiBase={apiBase} mode="log" />
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <ScrapPanel apiBase={apiBase} mode="record" />
          </Grid.Col>
        </Grid>
      )}
    </Stack>
  );
}
