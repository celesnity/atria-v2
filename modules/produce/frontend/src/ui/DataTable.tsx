import type { ReactNode } from 'react';
import { Table, Text, Stack, Badge } from '@mantine/core';
import { statusColorMantine } from '../theme.mantine';

export interface Column<T> { key: string; label: string; render?: (row: T) => ReactNode; }

const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

// Keys whose values are status strings → rendered as semantic chips.
const STATUS_KEYS = new Set(['status', 'trạng thái', 'trang_thai']);

/** Compact, readable cell formatting: ISO timestamps → "dd/MM HH:mm". */
function formatValue(v: unknown): ReactNode {
  if (typeof v === 'string' && ISO_RE.test(v)) {
    const d = new Date(v);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString('vi-VN', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
    }
  }
  return v === null || v === undefined ? '' : String(v);
}

function StatusChip({ value }: { value: string }) {
  if (!value) return null;
  return (
    <Badge variant="light" color={statusColorMantine(value)} radius="sm" size="sm" style={{ fontWeight: 600 }}>
      {value}
    </Badge>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <Stack align="center" gap={8} py={22} style={{ opacity: 0.9 }}>
      <div
        aria-hidden
        style={{
          width: 40, height: 40, borderRadius: 12, display: 'grid', placeItems: 'center',
          color: 'var(--pr-accent)',
          background: 'color-mix(in srgb, var(--pr-accent) 9%, transparent)',
          border: '1px solid color-mix(in srgb, var(--pr-accent) 18%, transparent)',
        }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 8.5 12 4l9 4.5-9 4.5-9-4.5Z" />
          <path d="M3 8.5v7L12 20l9-4.5v-7" opacity="0.5" />
        </svg>
      </div>
      <Text c="dimmed" size="sm" fw={500}>{label}</Text>
    </Stack>
  );
}

export default function DataTable<T extends Record<string, unknown>>({ columns, rows, empty = 'Không có dữ liệu' }: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  if (!rows.length) {
    return <Empty label={empty} />;
  }
  return (
    // Fluid wrapper: the table fills the card width and wraps cell text; a
    // contained horizontal scroll is the graceful fallback only when genuinely
    // needed (rounded + clipped so nothing bleeds past the card edge).
    <div className="pr-tablewrap">
      <Table
        striped
        highlightOnHover
        withRowBorders
        verticalSpacing="xs"
        horizontalSpacing="sm"
        style={{ fontVariantNumeric: 'tabular-nums', width: '100%' }}
      >
        <Table.Thead>
          <Table.Tr>
            {columns.map((c) => (
              <Table.Th key={c.key} style={{ textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.03em', whiteSpace: 'nowrap' }}>{c.label}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, i) => (
            <Table.Tr key={(row.id as number) ?? i}>
              {columns.map((c) => (
                <Table.Td key={c.key} style={{ verticalAlign: 'middle' }}>
                  {c.render
                    ? c.render(row)
                    : STATUS_KEYS.has(c.key.toLowerCase())
                      ? <StatusChip value={String(row[c.key] ?? '')} />
                      : formatValue(row[c.key])}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
