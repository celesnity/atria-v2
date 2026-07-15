import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export default function Section({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const { tokens } = useMinderTheme();
  return (
    <section
      className="pr-card"
      style={{
        background: tokens.surface,
        border: `1px solid ${tokens.border}`,
        borderRadius: 16,
        padding: '18px 20px 20px',
        marginBottom: 16,
        boxShadow: tokens.cardShadow,
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 16,
          marginBottom: 16,
          paddingBottom: 14,
          borderBottom: `1px solid ${tokens.border}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            aria-hidden
            style={{ width: 3, height: 15, borderRadius: 2, background: tokens.primary }}
          />
          <h3
            style={{
              margin: 0,
              color: tokens.text,
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: '-0.01em',
            }}
          >
            {title}
          </h3>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          {actions}
        </div>
      </header>
      {children}
    </section>
  );
}
