import { SimpleGrid, Text, Badge, Paper } from '@mantine/core';
import { statusColorMantine } from '../theme.mantine';

const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

function fmt(v: unknown) {
  if (typeof v === 'string' && ISO_RE.test(v)) {
    const d = new Date(v);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }
  }
  if (v === null || v === undefined || v === '') return '—';
  return String(v);
}

const STATUS_KEYS = new Set(['status', 'trạng thái']);

/** Render a record as a labelled detail grid. `labels` maps raw keys → display. */
export default function RowDetail({
  row,
  labels = {},
  hide = [],
  columns = 2,
}: {
  row: Record<string, unknown>;
  labels?: Record<string, string>;
  hide?: string[];
  columns?: number;
}) {
  const entries = Object.entries(row).filter(([k]) => !hide.includes(k));
  return (
    <SimpleGrid cols={{ base: 1, xs: columns }} spacing="xs" verticalSpacing="xs">
      {entries.map(([k, v]) => (
        <Paper key={k} withBorder radius="md" p="xs" bg="var(--pr-surface-alt, transparent)">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.04em' }}>
            {labels[k] ?? k}
          </Text>
          {STATUS_KEYS.has(k.toLowerCase()) && v ? (
            <Badge mt={4} variant="light" color={statusColorMantine(String(v))} radius="sm" size="sm">{String(v)}</Badge>
          ) : (
            <Text size="sm" fw={600} mt={2} style={{ overflowWrap: 'anywhere' }}>{fmt(v)}</Text>
          )}
        </Paper>
      ))}
    </SimpleGrid>
  );
}
