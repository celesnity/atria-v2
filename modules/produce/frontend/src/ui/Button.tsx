import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { useMinderTheme } from 'minder-ui-sdk';

export default function Button({ onClick, disabled, variant = 'primary', children }: { onClick: () => void; disabled?: boolean; variant?: 'primary' | 'ghost' | 'danger'; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  const bg = variant === 'primary' ? tokens.primary : variant === 'danger' ? tokens.error : 'transparent';
  const color = variant === 'ghost' ? tokens.text : '#fff';
  const border = variant === 'ghost' ? `1px solid ${tokens.border}` : 'none';
  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.03 }}
      whileTap={{ scale: disabled ? 1 : 0.97 }}
      onClick={onClick}
      disabled={disabled}
      style={{ background: bg, color, border, borderRadius: 8, padding: '7px 12px', fontSize: 13, fontWeight: 500, cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1 }}
    >
      {children}
    </motion.button>
  );
}
