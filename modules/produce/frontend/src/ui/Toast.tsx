import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

interface Toast { id: number; msg: string; kind: 'ok' | 'err'; }
const Ctx = createContext<{ notify: (msg: string, kind?: 'ok' | 'err') => void }>({ notify: () => {} });
export function useToast() { return useContext(Ctx); }

export function ToastProvider({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((msg: string, kind: 'ok' | 'err' = 'ok') => {
    const id = toasts.length + 1 + Math.floor(performance.now());
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, [toasts.length]);
  return (
    <Ctx.Provider value={{ notify }}>
      {children}
      <div style={{ position: 'fixed', bottom: 16, right: 16, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 1000 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{ background: t.kind === 'ok' ? tokens.success : tokens.error, color: '#fff', borderRadius: 8, padding: '8px 14px', fontSize: 13 }}>{t.msg}</div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
