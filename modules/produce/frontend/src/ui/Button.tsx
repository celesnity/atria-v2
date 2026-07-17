import type { ReactNode } from 'react';
import { Button as MButton } from '@mantine/core';

export default function Button({ onClick, disabled, variant = 'primary', children }: { onClick: () => void; disabled?: boolean; variant?: 'primary' | 'ghost' | 'danger'; children: ReactNode }) {
  const map = variant === 'primary'
    ? { color: 'cobalt', variant: 'filled' as const }
    : variant === 'danger'
      ? { color: 'red', variant: 'filled' as const }
      : { color: 'gray', variant: 'default' as const };
  return <MButton size="sm" radius="md" disabled={disabled} onClick={onClick} {...map}>{children}</MButton>;
}
