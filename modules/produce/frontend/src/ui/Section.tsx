import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export default function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <section style={{ background: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 12, padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0, color: tokens.text, fontSize: 15, fontWeight: 600 }}>{title}</h3>
        <div style={{ display: 'flex', gap: 8 }}>{actions}</div>
      </div>
      {children}
    </section>
  );
}
