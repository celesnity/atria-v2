import type { ReactNode } from 'react';
import { Table, Text, Center, Group } from '@mantine/core';

export interface Column<T> { key: string; label: string; render?: (row: T) => ReactNode; }

export default function DataTable<T extends Record<string, unknown>>({ columns, rows, empty = 'Không có dữ liệu' }: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  if (!rows.length) {
    return (
      <Center py="lg">
        <Group gap={8}><Text c="dimmed" size="sm">{empty}</Text></Group>
      </Center>
    );
  }
  return (
    <Table.ScrollContainer minWidth={480}>
      <Table striped highlightOnHover withTableBorder verticalSpacing="xs" horizontalSpacing="md" style={{ fontVariantNumeric: 'tabular-nums' }}>
        <Table.Thead>
          <Table.Tr>
            {columns.map((c) => (
              <Table.Th key={c.key} style={{ textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.03em' }}>{c.label}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, i) => (
            <Table.Tr key={(row.id as number) ?? i}>
              {columns.map((c) => (
                <Table.Td key={c.key}>{c.render ? c.render(row) : String(row[c.key] ?? '')}</Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
