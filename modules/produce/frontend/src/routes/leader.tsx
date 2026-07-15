import { SimpleGrid, Grid, Stack } from '@mantine/core';
import { IconUsers, IconBellRinging, IconExclamationCircle } from '@tabler/icons-react';
import { useApi } from '../api';
import StatTile from '../ui/StatTile';
import WorkPanel from '../panels/WorkPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ExceptionPanel from '../panels/ExceptionPanel';

export default function LeaderRoute({ apiBase }: { apiBase: string }) {
  const board = useApi<Array<Record<string, unknown>>>(apiBase, '/work/board/1');
  const andons = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/andon/line/1');
  const exc = useApi<Array<Record<string, unknown>>>(apiBase, '/exception/line/1/open');

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <StatTile label="Task của tổ" value={(board.data ?? []).length} icon={<IconUsers size={20} />} />
        <StatTile label="Andon đang mở" value={(andons.data ?? []).length} color="orange" icon={<IconBellRinging size={20} />} />
        <StatTile label="Ngoại lệ mở" value={(exc.data ?? []).length} color="red" icon={<IconExclamationCircle size={20} />} />
      </SimpleGrid>

      <WorkPanel apiBase={apiBase} mode="board" />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 6 }}><DowntimePanel apiBase={apiBase} mode="andon" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><ExceptionPanel apiBase={apiBase} mode="triage" /></Grid.Col>
      </Grid>
    </Stack>
  );
}
