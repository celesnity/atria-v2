import type { ReactNode } from 'react';
import { Input, TextInput as MTextInput, NumberInput as MNumberInput } from '@mantine/core';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <Input.Wrapper label={label} styles={{ label: { textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.03em', fontWeight: 600 } }}>{children}</Input.Wrapper>;
}

export function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return <MTextInput value={value} placeholder={placeholder} onChange={(e) => onChange(e.currentTarget.value)} size="sm" />;
}

export function NumberInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return <MNumberInput value={value} onChange={(v) => onChange(typeof v === 'number' ? v : Number(v) || 0)} size="sm" w={110} hideControls />;
}
