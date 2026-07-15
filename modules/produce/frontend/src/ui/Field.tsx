import type { CSSProperties, ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <label
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.03em',
        textTransform: 'uppercase',
        color: tokens.textMuted,
      }}
    >
      {label}
      {children}
    </label>
  );
}

function inputStyle(tokens: ReturnType<typeof useMinderTheme>['tokens']): CSSProperties {
  // surfaceAlt, NOT bg (bg is a gradient in the Celesnity theme — wrong on inputs).
  return {
    background: tokens.surfaceAlt,
    border: `1px solid ${tokens.border}`,
    borderRadius: 10,
    padding: '8px 11px',
    color: tokens.text,
    fontSize: 13,
    fontWeight: 500,
    letterSpacing: 'normal',
    textTransform: 'none',
    fontVariantNumeric: 'tabular-nums',
  };
}

export function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const { tokens } = useMinderTheme();
  return (
    <input
      className="pr-input"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      style={inputStyle(tokens)}
    />
  );
}

export function NumberInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { tokens } = useMinderTheme();
  return (
    <input
      className="pr-input"
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ ...inputStyle(tokens), width: 96 }}
    />
  );
}
