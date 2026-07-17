import { Stack, Group, Text, Badge, Divider, Card, Loader, ThemeIcon } from '@mantine/core';
import { IconClipboardList, IconActivity, IconStack2 } from '@tabler/icons-react';
import DetailModal from '../ui/DetailModal';
import RowDetail from '../ui/RowDetail';
import { useApiQuery } from '../hooks/useApiQuery';
import { statusColorMantine } from '../theme.mantine';

const TASK_LABELS: Record<string, string> = {
  id: 'Mã task', line_id: 'Line', shift_id: 'Ca', station_id: 'Trạm',
  operation_id: 'Công đoạn', part_id: 'Linh kiện', assignee_id: 'Người làm',
  priority: 'Ưu tiên', status: 'Trạng thái', created_at: 'Tạo lúc', updated_at: 'Cập nhật',
};

export default function TaskDetailModal({
  apiBase, task, onClose,
}: {
  apiBase: string;
  task: Record<string, unknown> | null;
  onClose: () => void;
}) {
  const opened = !!task;
  const stationId = task?.station_id as number | undefined;

  // React Query — fetched lazily, only while the modal is open for this station.
  const status = useApiQuery<{ status?: string } | null>(apiBase, stationId ? `/wip/stations/${stationId}/status` : null, { enabled: opened && !!stationId });
  const total = useApiQuery<{ total?: number }>(apiBase, stationId ? `/wip/stations/${stationId}/total` : null, { enabled: opened && !!stationId });

  const liveLoading = status.isFetching || total.isFetching;

  return (
    <DetailModal
      opened={opened}
      onClose={onClose}
      title={task ? `Task #${task.id}` : 'Task'}
      subtitle="Chi tiết công việc & trạng thái trạm trực tiếp"
      icon={<IconClipboardList size={20} />}
      size="lg"
    >
      {task ? (
        <Stack gap="md">
          <Group gap="sm">
            <Badge size="lg" radius="sm" variant="light" color={statusColorMantine(String(task.status))}>
              {String(task.status)}
            </Badge>
            <Badge size="lg" radius="sm" variant="light" color="gray">Ưu tiên {String(task.priority)}</Badge>
          </Group>

          <RowDetail row={task} labels={TASK_LABELS} />

          <Divider label="Trạng thái trạm (trực tiếp)" labelPosition="left" />

          {!stationId ? (
            <Text c="dimmed" size="sm">Task chưa gắn trạm.</Text>
          ) : (
            <Group grow align="stretch">
              <Card withBorder radius="md" padding="md">
                <Group gap={8} mb={6}><ThemeIcon size={26} radius="md" variant="light" color="cobalt"><IconActivity size={15} /></ThemeIcon><Text size="xs" c="dimmed" fw={600} tt="uppercase">Trạng thái trạm {stationId}</Text></Group>
                {liveLoading ? <Loader size="xs" color="cobalt" /> : (
                  <Badge size="lg" radius="sm" variant="light" color={statusColorMantine(String(status.data?.status ?? 'idle'))}>
                    {String(status.data?.status ?? '—')}
                  </Badge>
                )}
              </Card>
              <Card withBorder radius="md" padding="md">
                <Group gap={8} mb={6}><ThemeIcon size={26} radius="md" variant="light" color="teal"><IconStack2 size={15} /></ThemeIcon><Text size="xs" c="dimmed" fw={600} tt="uppercase">Tổng sản lượng</Text></Group>
                {liveLoading ? <Loader size="xs" color="teal" /> : (
                  <Text fw={800} fz={26} lh={1} style={{ fontVariantNumeric: 'tabular-nums' }}>{total.data?.total ?? 0}</Text>
                )}
              </Card>
            </Group>
          )}
        </Stack>
      ) : null}
    </DetailModal>
  );
}
