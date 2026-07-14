import { useState, useEffect } from 'react';
import { Check, ArrowLeft, ArrowRight, CornerDownLeft } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chat';
import type { AskUserQuestion } from '../../types';

export function AskUserDialog() {
  const { t } = useTranslation('chat');
  const pendingAskUser = useChatStore(state => {
    const sid = state.currentSessionId;
    return sid ? state.sessionStates[sid]?.pendingAskUser ?? null : null;
  });
  const respondToAskUser = useChatStore(state => state.respondToAskUser);
  const reduce = useReducedMotion();

  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [selectedOptions, setSelectedOptions] = useState<Set<number>>(new Set());
  const [otherText, setOtherText] = useState('');
  const [showOther, setShowOther] = useState(false);

  // Reset state when new request comes in
  useEffect(() => {
    if (pendingAskUser) {
      setCurrentIdx(0);
      setAnswers({});
      setSelectedOptions(new Set());
      setOtherText('');
      setShowOther(false);
    }
  }, [pendingAskUser]);

  // Keyboard shortcuts
  useEffect(() => {
    if (!pendingAskUser) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const questions = pendingAskUser.questions;
      if (!questions || currentIdx >= questions.length) return;
      const q = questions[currentIdx];

      // Number keys to select options
      const num = parseInt(e.key);
      if (!isNaN(num) && num >= 1 && num <= q.options.length) {
        e.preventDefault();
        const optIdx = num - 1;
        if (q.multi_select) {
          setSelectedOptions(prev => {
            const next = new Set(prev);
            if (next.has(optIdx)) next.delete(optIdx);
            else next.add(optIdx);
            return next;
          });
        } else {
          setSelectedOptions(new Set([optIdx]));
          setShowOther(false);
        }
      }

      // 'o' for Other
      if (e.key === 'o' || e.key === 'O') {
        if (!q.multi_select) {
          setSelectedOptions(new Set());
        }
        setShowOther(true);
      }

      // Enter to confirm/next
      if (e.key === 'Enter' && !e.shiftKey) {
        // Don't intercept if typing in the Other input
        if (showOther && document.activeElement?.tagName === 'INPUT') {
          e.preventDefault();
          handleNext();
          return;
        }
        if (selectedOptions.size > 0 || showOther) {
          e.preventDefault();
          handleNext();
        }
      }

      // Escape to cancel
      if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [pendingAskUser, currentIdx, selectedOptions, showOther, otherText]);

  if (!pendingAskUser) return null;

  const questions = pendingAskUser.questions;
  if (!questions || questions.length === 0) return null;

  const currentQuestion: AskUserQuestion = questions[currentIdx];
  const isLastQuestion = currentIdx === questions.length - 1;

  const handleOptionClick = (optIdx: number) => {
    if (currentQuestion.multi_select) {
      setSelectedOptions(prev => {
        const next = new Set(prev);
        if (next.has(optIdx)) next.delete(optIdx);
        else next.add(optIdx);
        return next;
      });
      setShowOther(false);
    } else {
      setSelectedOptions(new Set([optIdx]));
      setShowOther(false);
    }
  };

  const handleOtherClick = () => {
    if (!currentQuestion.multi_select) {
      setSelectedOptions(new Set());
    }
    setShowOther(true);
  };

  const handleNext = () => {
    // Save current answer
    let answer: any;
    if (showOther && otherText.trim()) {
      answer = currentQuestion.multi_select
        ? [...Array.from(selectedOptions).map(i => currentQuestion.options[i].label), otherText.trim()]
        : otherText.trim();
    } else if (selectedOptions.size > 0) {
      if (currentQuestion.multi_select) {
        answer = Array.from(selectedOptions).map(i => currentQuestion.options[i].label);
      } else {
        const idx = Array.from(selectedOptions)[0];
        answer = currentQuestion.options[idx].label;
      }
    } else {
      return; // Nothing selected
    }

    const newAnswers = { ...answers, [String(currentIdx)]: answer };
    setAnswers(newAnswers);

    if (isLastQuestion) {
      // Submit
      respondToAskUser(pendingAskUser.request_id, newAnswers);
    } else {
      // Next question
      setCurrentIdx(currentIdx + 1);
      setSelectedOptions(new Set());
      setOtherText('');
      setShowOther(false);
    }
  };

  const handleBack = () => {
    if (currentIdx > 0) {
      setCurrentIdx(currentIdx - 1);
      setSelectedOptions(new Set());
      setOtherText('');
      setShowOther(false);
    }
  };

  const handleCancel = () => {
    respondToAskUser(pendingAskUser.request_id, null);
  };

  const canAdvance = selectedOptions.size > 0 || (showOther && !!otherText.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-md px-4">
      <motion.div
        initial={reduce ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.97 }}
        animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-lg overflow-hidden rounded-lg border border-hairline-soft bg-canvas shadow-modal"
      >
        {/* Ambient brand wash — top-anchored, barely perceptible. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-28 opacity-[0.07]"
          style={{ background: 'radial-gradient(120% 100% at 80% 0%, hsl(276 66% 55%), transparent 68%)' }}
        />

        {/* Header */}
        <div className="relative flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-hairline-soft">
          <div className="min-w-0">
            {currentQuestion.header && (
              <span className="eyebrow-mono text-accent-cobalt">{currentQuestion.header}</span>
            )}
            <h2 className="mt-1.5 text-[17px] font-[600] leading-snug tracking-[-0.02em] text-ink">
              {currentQuestion.question}
            </h2>
          </div>
          {questions.length > 1 && (
            <span className="mt-0.5 flex-shrink-0 rounded-pill bg-surface-soft px-2.5 py-1 text-[11px] font-mono font-[600] text-text-secondary">
              {String(currentIdx + 1).padStart(2, '0')} / {String(questions.length).padStart(2, '0')}
            </span>
          )}
        </div>

        {/* Options */}
        <div className="relative px-6 py-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentIdx}
              initial={reduce ? false : { opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, x: -12 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="space-y-2"
            >
              {currentQuestion.options.map((opt, i) => {
                const isSelected = selectedOptions.has(i);
                return (
                  <motion.button
                    key={i}
                    onClick={() => handleOptionClick(i)}
                    initial={reduce ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: reduce ? 0 : 0.04 * i, duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                    className={`group flex w-full items-start gap-3 rounded-md border px-4 py-3 text-left transition-all duration-200 ${
                      isSelected
                        ? 'border-accent-cobalt/40 bg-accent-cobalt/[0.07] shadow-glow-accent'
                        : 'border-hairline-soft hover:border-accent-cobalt/30 hover:bg-surface-soft/60 hover:-translate-y-px'
                    }`}
                  >
                    {/* Selection control — radio for single, checkbox for multi. */}
                    <span
                      className={`mt-0.5 grid h-5 w-5 flex-shrink-0 place-items-center border-2 transition-all ${
                        currentQuestion.multi_select ? 'rounded-[5px]' : 'rounded-pill'
                      } ${
                        isSelected
                          ? 'border-transparent bg-gradient-brand'
                          : 'border-hairline group-hover:border-accent-cobalt/50'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
                    </span>

                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <kbd className="rounded-[4px] bg-surface-soft px-1.5 py-0.5 font-mono text-[10px] font-[600] text-text-muted">
                          {i + 1}
                        </kbd>
                        <span className={`text-sm font-[540] tracking-[-0.01em] ${isSelected ? 'text-ink' : 'text-text-secondary group-hover:text-ink'}`}>
                          {opt.label}
                        </span>
                      </span>
                      {opt.description && (
                        <span className="mt-1 block pl-[26px] text-xs leading-relaxed text-text-muted">
                          {opt.description}
                        </span>
                      )}
                    </span>
                  </motion.button>
                );
              })}

              {/* Other */}
              <button
                onClick={handleOtherClick}
                className={`flex w-full items-center gap-3 rounded-md border border-dashed px-4 py-3 text-left transition-all duration-200 ${
                  showOther
                    ? 'border-accent-cobalt/40 bg-accent-cobalt/[0.07]'
                    : 'border-hairline-soft hover:border-accent-cobalt/30 hover:bg-surface-soft/60'
                }`}
              >
                <span
                  className={`grid h-5 w-5 flex-shrink-0 place-items-center rounded-pill border-2 transition-all ${
                    showOther ? 'border-transparent bg-gradient-brand' : 'border-hairline'
                  }`}
                >
                  {showOther && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
                </span>
                <span className="flex items-center gap-2">
                  <kbd className="rounded-[4px] bg-surface-soft px-1.5 py-0.5 font-mono text-[10px] font-[600] text-text-muted">O</kbd>
                  <span className={`text-sm font-[540] ${showOther ? 'text-ink' : 'text-text-secondary'}`}>
                    {t('askUserDialog.somethingElse')}
                  </span>
                </span>
              </button>

              {showOther && (
                <motion.input
                  initial={reduce ? false : { opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  type="text"
                  value={otherText}
                  onChange={e => setOtherText(e.target.value)}
                  placeholder={t('askUserDialog.typeYourAnswer')}
                  className="w-full rounded-md border border-hairline-soft bg-surface-soft/50 px-4 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-text-muted focus:border-accent-cobalt/50 focus:bg-canvas"
                  autoFocus
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer */}
        <div className="relative flex items-center justify-between gap-3 border-t border-hairline-soft bg-surface-soft/40 px-6 py-3.5">
          <button
            onClick={handleCancel}
            className="text-sm font-[500] text-text-muted transition-colors hover:text-ink"
          >
            {t('askUserDialog.cancel')}
          </button>

          <div className="flex items-center gap-2">
            {currentIdx > 0 && (
              <button
                onClick={handleBack}
                className="flex items-center gap-1.5 rounded-pill border border-hairline-soft bg-canvas px-3.5 py-2 text-sm font-[540] text-text-secondary transition-all hover:border-hairline hover:text-ink active:scale-[0.97]"
              >
                <ArrowLeft className="h-4 w-4" />
                {t('askUserDialog.back')}
              </button>
            )}
            <button
              onClick={handleNext}
              disabled={!canAdvance}
              className="flex items-center gap-1.5 rounded-pill bg-gradient-brand px-4 py-2 text-sm font-[540] text-white shadow-glow-nebula transition-all hover:brightness-110 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-none disabled:bg-surface-soft disabled:text-text-muted disabled:opacity-70 disabled:shadow-none"
            >
              {isLastQuestion ? t('askUserDialog.submit') : t('askUserDialog.next')}
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Keyboard hints */}
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 border-t border-hairline-soft/60 px-6 py-2.5 text-[11px] text-text-muted">
          <span className="flex items-center gap-1.5">
            <kbd className="rounded border border-hairline-soft bg-canvas px-1.5 py-0.5 font-mono text-[10px]">1</kbd>
            <span className="text-text-muted/60">–</span>
            <kbd className="rounded border border-hairline-soft bg-canvas px-1.5 py-0.5 font-mono text-[10px]">{currentQuestion.options.length}</kbd>
            {t('askUserDialog.hintSelect')}
          </span>
          <span className="flex items-center gap-1.5">
            <kbd className="flex items-center gap-1 rounded border border-hairline-soft bg-canvas px-1.5 py-0.5 font-mono text-[10px]"><CornerDownLeft className="h-3 w-3" /></kbd>
            {t('askUserDialog.hintConfirm')}
          </span>
          <span className="flex items-center gap-1.5">
            <kbd className="rounded border border-hairline-soft bg-canvas px-1.5 py-0.5 font-mono text-[10px]">Esc</kbd>
            {t('askUserDialog.hintCancel')}
          </span>
        </div>
      </motion.div>
    </div>
  );
}
