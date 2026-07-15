import type { CSSProperties, ReactNode } from 'react';
import { motion } from 'motion/react';
import { useMinderTheme } from 'minder-ui-sdk';

export default function Button({
  onClick,
  disabled,
  variant = 'primary',
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'ghost' | 'danger';
  children: ReactNode;
}) {
  const { tokens } = useMinderTheme();

  const base: CSSProperties = {
    borderRadius: 10,
    padding: '8px 14px',
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: '-0.01em',
    lineHeight: 1.1,
    border: '1px solid transparent',
    whiteSpace: 'nowrap',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };

  const skin: CSSProperties =
    variant === 'primary'
      ? {
          background: tokens.primary,
          color: '#fff',
          boxShadow: `0 2px 10px color-mix(in srgb, ${tokens.primary} 35%, transparent)`,
        }
      : variant === 'danger'
        ? {
            background: tokens.error,
            color: '#fff',
            boxShadow: `0 2px 10px color-mix(in srgb, ${tokens.error} 32%, transparent)`,
          }
        : { background: 'transparent', color: tokens.text, borderColor: tokens.border };

  return (
    <motion.button
      className={variant === 'ghost' ? 'pr-btn pr-ghost' : 'pr-btn'}
      whileTap={{ scale: disabled ? 1 : 0.97 }}
      onClick={onClick}
      disabled={disabled}
      style={{ ...base, ...skin }}
    >
      {children}
    </motion.button>
  );
}
