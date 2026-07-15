import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => ReactNode;
}

export default function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  empty = 'Không có dữ liệu',
}: {
  columns: Column<T>[];
  rows: T[];
  empty?: string;
}) {
  const { tokens } = useMinderTheme();

  if (!rows.length) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          padding: '28px 0',
          color: tokens.textMuted,
          fontSize: 13,
        }}
      >
        <span
          aria-hidden
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: tokens.textMuted,
            opacity: 0.5,
          }}
        />
        {empty}
      </div>
    );
  }

  return (
    <div
      style={{
        overflow: 'hidden',
        borderRadius: 12,
        border: `1px solid ${tokens.border}`,
        background: tokens.surfaceAlt,
      }}
    >
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  style={{
                    textAlign: 'left',
                    padding: '10px 13px',
                    color: tokens.textMuted,
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: '0.03em',
                    textTransform: 'uppercase',
                    borderBottom: `1px solid ${tokens.border}`,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={(row.id as number) ?? i} className="pr-row">
                {columns.map((c) => (
                  <td
                    key={c.key}
                    style={{
                      padding: '9px 13px',
                      color: tokens.text,
                      borderBottom:
                        i === rows.length - 1 ? 'none' : `1px solid ${tokens.border}`,
                    }}
                  >
                    {c.render ? c.render(row) : String(row[c.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
