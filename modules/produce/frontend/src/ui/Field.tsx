import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: tokens.textMuted }}>
      {label}
      {children}
    </label>
  );
}

function inputStyle(tokens: ReturnType<typeof useMinderTheme>['tokens']) {
  return { background: tokens.bg, border: `1px solid ${tokens.border}`, borderRadius: 8, padding: '7px 10px', color: tokens.text, fontSize: 13 } as const;
}

export function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const { tokens } = useMinderTheme();
  return <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} style={inputStyle(tokens)} />;
}

export function NumberInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { tokens } = useMinderTheme();
  return <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} style={inputStyle(tokens)} />;
}
