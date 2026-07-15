import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export interface Column<T> { key: string; label: string; render?: (row: T) => ReactNode; }

export default function DataTable<T extends Record<string, unknown>>({ columns, rows, empty = 'No data' }: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  const { tokens } = useMinderTheme();
  if (!rows.length) return <div style={{ color: tokens.textMuted, padding: '24px 0', textAlign: 'center', fontSize: 13 }}>{empty}</div>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: 'left', padding: '8px 10px', color: tokens.textMuted, borderBottom: `1px solid ${tokens.border}`, fontWeight: 600 }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={(row.id as number) ?? i}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: '8px 10px', color: tokens.text, borderBottom: `1px solid ${tokens.border}` }}>
                  {c.render ? c.render(row) : String(row[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
