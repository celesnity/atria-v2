import { useState, useEffect, useRef } from 'react';
import { User, X, ChevronDown, Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chat';
import { useUiStore } from '../../stores/ui';
import { apiClient } from '../../api/client';
import type { Persona } from '../../types';

export function PersonaSelector() {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [fetchError, setFetchError] = useState(false);
  const cachedRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedPersona = useChatStore(state => {
    const sid = state.currentSessionId;
    return sid ? state.sessionStates[sid]?.selectedPersona : null;
  });
  const setSelectedPersona = useChatStore(state => state.setSelectedPersona);
  const openSettingsModal = useUiStore(state => state.openSettingsModal);

  // Fetch personas once per mount (lazy, cached after first open)
  useEffect(() => {
    if (!open || cachedRef.current) return;
    cachedRef.current = true;
    apiClient
      .listPersonas()
      .then((data) => setPersonas(data))
      .catch(() => setFetchError(true));
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleSelect = (name: string) => {
    setSelectedPersona(name);
    setOpen(false);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedPersona(null);
  };

  const pillBase =
    'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[11px] font-medium cursor-pointer transition-colors select-none active:scale-[0.98] whitespace-nowrap';
  const pillStyle = 'bg-bg-400/40 text-text-200 border-hairline-soft hover:bg-bg-400/60';

  return (
    <div ref={containerRef} className="relative flex items-center gap-2">
      <button
        onClick={() => setOpen(prev => !prev)}
        className={`${pillBase} ${pillStyle}`}
        title={selectedPersona ? t('personaSelector.currentPersona', { name: selectedPersona }) : t('personaSelector.selectPersona')}
      >
        <User className="w-3 h-3" strokeWidth={2} />
        {selectedPersona ? (
          <>
            <span>{selectedPersona}</span>
            <button
              onClick={handleClear}
              className="ml-1 text-text-200/60 hover:text-text-200 transition-colors"
              title={t('personaSelector.clearPersona')}
            >
              <X className="w-3 h-3" strokeWidth={2} />
            </button>
          </>
        ) : (
          <>
            <span>{t('personaSelector.persona')}</span>
            <ChevronDown className="w-3 h-3" strokeWidth={2} />
          </>
        )}
      </button>

      {open && (
        <div className="absolute bottom-full mb-2 left-0 z-50 min-w-[180px] max-h-64 overflow-y-auto rounded-md border border-hairline-soft bg-bg-300 shadow-soft py-1">
          {fetchError ? (
            <p className="px-3 py-2 text-xs text-semantic-danger">{t('personaSelector.loadError')}</p>
          ) : personas.length === 0 ? (
            <div className="px-3 py-2 text-xs text-text-200/60">
              <p>{t('personaSelector.noPersonas')}</p>
              <button
                onClick={() => { openSettingsModal(); setOpen(false); }}
                className="mt-1 flex items-center gap-1 text-text-200 hover:underline"
              >
                <Settings className="w-3 h-3" />
                {t('personaSelector.openSettings')}
              </button>
            </div>
          ) : (
            personas.map(p => (
              <button
                key={p.name}
                onClick={() => handleSelect(p.name)}
                className={`w-full text-left px-3 py-2 text-xs hover:bg-bg-400/40 transition-colors ${
                  selectedPersona === p.name ? 'text-text-100 font-semibold' : 'text-text-200'
                }`}
              >
                {p.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
