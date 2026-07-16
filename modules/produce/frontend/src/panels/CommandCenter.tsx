import { useState } from 'react';
import {
  Card, Group, Stack, Text, Title, RingProgress, Progress, Badge, ThemeIcon,
  SimpleGrid, Grid, Box, Center, Timeline, ScrollArea, Divider,
} from '@mantine/core';
import { BarChart, DonutChart } from '@mantine/charts';
import {
  IconActivity, IconAlertTriangle, IconRecycle, IconStack2, IconGauge,
  IconClock, IconTool, IconChecklist,
} from '@tabler/icons-react';
import { useApi } from '../api';
import { LineSelect, ShiftSelect } from '../ui/selects';

type Row = Record<string, unknown>;

const STATUS_META: Record<string, { label: string; color: string }> = {
  queued: { label: 'Chờ nhận', color: 'gray' },
  assigned: { label: 'Đã gán', color: 'cobalt' },
  in_progress: { label: 'Đang làm', color: 'indigo' },
  done: { label: 'Hoàn thành', color: 'teal' },
  blocked: { label: 'Bị chặn', color: 'red' },
};

const CAT_COLORS = ['cobalt.6', 'teal.6', 'grape.6', 'orange.6', 'red.6', 'cyan.6', 'lime.6'];

function pct(v?: number) {
  return Math.round((v ?? 0) * 100);
}

/** A titled bento cell with the shared gradient accent bar. */
function Cell({
  title, icon, right, children, className,
}: {
  title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" h="100%" className={className}>
      <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
        <Group gap={10} align="center" wrap="nowrap" style={{ flex: '1 1 auto', minWidth: 0 }}>
          {icon ? (
            <ThemeIcon variant="light" color="cobalt" size={30} radius="md">{icon}</ThemeIcon>
          ) : (
            <Box w={5} h={20} style={{ borderRadius: 5, background: 'linear-gradient(180deg, var(--mantine-color-cobalt-4), var(--mantine-color-cobalt-7))' }} />
          )}
          <Title order={5} style={{ letterSpacing: '-0.01em', lineHeight: 1.2 }}>{title}</Title>
        </Group>
        {right}
      </Group>
      {children}
    </Card>
  );
}

export default function CommandCenter({ apiBase }: { apiBase: string }) {
  const [line, setLine] = useState(2);
  const [shift, setShift] = useState(1);
  const count = 420;

  const oee = useApi<Record<string, number> & { error?: string }>(apiBase, `/oee/shifts/${shift}?total_count=${count}`, [shift]);
  const losses = useApi<Record<string, number>>(apiBase, `/oee/shifts/${shift}/losses?total_count=${count}`, [shift]);
  const live = useApi<{ line_id: number; tasks: Row[] }>(apiBase, `/report/live/${line}`, [line]);
  const alerts = useApi<Row[]>(apiBase, '/downtime/alerts?threshold_minutes=0');
  const scrap = useApi<Row[]>(apiBase, '/scrap/by-station');
  const wip = useApi<Row[]>(apiBase, '/wip/wip');

  const d = oee.data ?? {};
  const l = losses.data ?? {};

  // Task-status distribution (donut + legend).
  const tasks = live.data?.tasks ?? [];
  const statusCounts = tasks.reduce<Record<string, number>>((acc, t) => {
    const s = String(t.status ?? 'queued');
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});
  const statusDonut = Object.entries(statusCounts).map(([k, v]) => ({
    name: STATUS_META[k]?.label ?? k,
    value: v,
    color: `${STATUS_META[k]?.color ?? 'gray'}.6`,
  }));

  // Downtime grouped by category.
  const dtByCat = (alerts.data ?? []).reduce<Record<string, number>>((acc, r) => {
    const c = String(r.category ?? 'Khác');
    acc[c] = (acc[c] ?? 0) + 1;
    return acc;
  }, {});
  const dtDonut = Object.entries(dtByCat).map(([k, v], i) => ({ name: k, value: v, color: CAT_COLORS[i % CAT_COLORS.length] }));
  const openDowntime = (alerts.data ?? []).length;

  // Top stations by scrap / wip.
  const scrapBars = (scrap.data ?? []).slice(0, 8).map((r) => ({ station: `T${r.station_id}`, scrap: Number(r.scrap ?? 0) }));
  const wipBars = (wip.data ?? []).slice(0, 8).map((r) => ({ station: `T${r.station_id}`, wip: Number(r.wip ?? 0) }));

  // Recent activity timeline (open downtime, newest first).
  const recent = [...(alerts.data ?? [])].sort((a, b) => Number(b.elapsed_minutes ?? 0) - Number(a.elapsed_minutes ?? 0)).slice(0, 5);

  const oeeVal = pct(d.oee);
  const oeeColor = oeeVal >= 75 ? 'teal' : oeeVal >= 60 ? 'cobalt' : 'orange';
  const totalScrap = (scrap.data ?? []).reduce((s, r) => s + Number(r.scrap ?? 0), 0);
  const totalWip = (wip.data ?? []).reduce((s, r) => s + Number(r.wip ?? 0), 0);

  return (
    <Stack gap="md">
      {/* Controls */}
      <Group justify="flex-end" gap="sm" align="flex-end">
        <LineSelect apiBase={apiBase} value={line} onChange={setLine} w={200} />
        <ShiftSelect apiBase={apiBase} value={shift} onChange={setShift} lineId={line} />
      </Group>

      {/* Bento row 1: OEE hero cell (wide) + status donut + downtime donut */}
      <Grid gutter="md" align="stretch">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Cell title="Hiệu suất thiết bị (OEE)" icon={<IconGauge size={18} />} right={<Badge color={oeeColor} variant="light" size="lg" radius="sm">{oeeVal}%</Badge>}>
            <Group align="center" gap="xl" wrap="nowrap">
              <RingProgress
                size={168}
                thickness={16}
                roundCaps
                sections={[{ value: oeeVal, color: oeeColor }]}
                label={<Center><Stack gap={0} align="center"><Text fw={800} fz={34} lh={1}>{oeeVal}%</Text><Text size="xs" c="dimmed">OEE</Text></Stack></Center>}
              />
              <Stack gap="xs" style={{ flex: 1, minWidth: 0 }}>
                {[
                  { k: 'Sẵn sàng (A)', v: pct(d.availability), c: 'cobalt' },
                  { k: 'Hiệu năng (P)', v: pct(d.performance), c: 'grape' },
                  { k: 'Chất lượng (Q)', v: pct(d.quality), c: 'teal' },
                ].map((row) => (
                  <div key={row.k}>
                    <Group justify="space-between" mb={3}><Text size="xs" c="dimmed" fw={600}>{row.k}</Text><Text size="xs" fw={700}>{row.v}%</Text></Group>
                    <Progress value={row.v} color={row.c} size="sm" radius="xl" />
                  </div>
                ))}
              </Stack>
            </Group>
            <Divider my="sm" />
            <Group gap="lg" wrap="wrap">
              <Group gap={6}><IconClock size={15} color="var(--mantine-color-orange-5)" /><Text size="xs" c="dimmed">Mất sẵn sàng</Text><Text size="xs" fw={700}>{(l.availability_loss_min ?? 0).toFixed(0)}′</Text></Group>
              <Group gap={6}><IconActivity size={15} color="var(--mantine-color-grape-5)" /><Text size="xs" c="dimmed">Mất hiệu năng</Text><Text size="xs" fw={700}>{(l.performance_loss_min ?? 0).toFixed(0)}′</Text></Group>
              <Group gap={6}><IconRecycle size={15} color="var(--mantine-color-red-5)" /><Text size="xs" c="dimmed">Mất chất lượng</Text><Text size="xs" fw={700}>{(l.quality_loss_min ?? 0).toFixed(0)}′</Text></Group>
            </Group>
          </Cell>
        </Grid.Col>

        <Grid.Col span={{ base: 12, sm: 6, lg: 4 }}>
          <Cell title="Trạng thái công việc" icon={<IconChecklist size={18} />} right={<Badge variant="light" color="gray" radius="sm">{tasks.length} task</Badge>}>
            {statusDonut.length ? (
              <Group align="center" gap="lg" wrap="nowrap">
                <DonutChart data={statusDonut} size={130} thickness={20} withTooltip chartLabel={`${tasks.length}`} />
                <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
                  {statusDonut.map((s) => (
                    <Group key={s.name} justify="space-between" wrap="nowrap" gap="xs">
                      <Group gap={6} wrap="nowrap"><Box w={9} h={9} style={{ borderRadius: 3, background: `var(--mantine-color-${s.color.replace('.', '-')})` }} /><Text size="xs" c="dimmed" truncate>{s.name}</Text></Group>
                      <Text size="xs" fw={700}>{s.value}</Text>
                    </Group>
                  ))}
                </Stack>
              </Group>
            ) : <Center h={130}><Text c="dimmed" size="sm">Chưa có công việc</Text></Center>}
          </Cell>
        </Grid.Col>

        <Grid.Col span={{ base: 12, sm: 6, lg: 3 }}>
          <Cell title="Downtime đang mở" icon={<IconAlertTriangle size={18} />} right={<Badge color={openDowntime ? 'red' : 'teal'} variant="light" radius="sm">{openDowntime}</Badge>}>
            {dtDonut.length ? (
              <Center><DonutChart data={dtDonut} size={140} thickness={22} withTooltip chartLabel={`${openDowntime}`} /></Center>
            ) : <Center h={140}><Text c="dimmed" size="sm">Không có downtime</Text></Center>}
          </Cell>
        </Grid.Col>
      </Grid>

      {/* Bento row 2: scrap bar (wide) + wip bar */}
      <Grid gutter="md" align="stretch">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Cell title="Phế phẩm theo trạm" icon={<IconRecycle size={18} />} right={<Badge color="red" variant="light" radius="sm">Tổng {totalScrap}</Badge>}>
            {scrapBars.length ? (
              <BarChart h={230} data={scrapBars} dataKey="station" series={[{ name: 'scrap', label: 'Phế phẩm', color: 'red.6' }]} tickLine="y" gridAxis="y" withBarValueLabel barProps={{ radius: 6 }} />
            ) : <Center h={230}><Text c="dimmed" size="sm">Chưa có dữ liệu</Text></Center>}
          </Cell>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Cell title="WIP theo trạm" icon={<IconStack2 size={18} />} right={<Badge color="cobalt" variant="light" radius="sm">Tổng {totalWip}</Badge>}>
            {wipBars.length ? (
              <BarChart h={230} data={wipBars} dataKey="station" series={[{ name: 'wip', label: 'WIP', color: 'cobalt.6' }]} tickLine="y" gridAxis="y" barProps={{ radius: 6 }} />
            ) : <Center h={230}><Text c="dimmed" size="sm">Chưa có WIP</Text></Center>}
          </Cell>
        </Grid.Col>
      </Grid>

      {/* Bento row 3: activity timeline */}
      <Cell title="Hoạt động gần đây" icon={<IconTool size={18} />}>
        {recent.length ? (
          <ScrollArea.Autosize mah={220}>
            <Timeline active={recent.length} bulletSize={22} lineWidth={2} color="cobalt">
              {recent.map((r, i) => (
                <Timeline.Item key={i} bullet={<IconAlertTriangle size={12} />} title={<Text fw={600} size="sm">{String(r.category)} · Trạm {String(r.station_id)}</Text>}>
                  <Text c="dimmed" size="xs">Downtime đang mở — đã trôi <b>{Number(r.elapsed_minutes ?? 0).toFixed(1)}</b> phút</Text>
                </Timeline.Item>
              ))}
            </Timeline>
          </ScrollArea.Autosize>
        ) : <Center h={80}><Text c="dimmed" size="sm">Không có sự kiện gần đây</Text></Center>}
      </Cell>
    </Stack>
  );
}
