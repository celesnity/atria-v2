import {
  ArrowUpRight,
  FileText,
  Image,
  Loader2,
  Paperclip,
  Plus,
  SendHorizontal,
  X,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import TextareaAutosize from "react-textarea-autosize";
import { useChatStore } from "../../stores/chat";
import { useProjectsStore } from "../../stores/projects";
import { AnimatedHeadline } from "../ui/AnimatedHeadline";
import { CosmicField } from "../ui/CosmicField";
import { Eyebrow } from "../ui/Eyebrow";
import { transitions } from "../ui/motion";

// Prompt starters — a gapless 2x2 bento. Concrete brainstorming asks (no cliches).
// Each fills the composer so the first keystroke is optional, not required.
// NOTE: `prompt` values are left as English literals — they are sent to the backend
// as persistent conversation data, so locale-resolving them would persist translated text.
const STARTERS: { kindKey: string; titleKey: string; prompt: string }[] = [
  {
    kindKey: "landingPage.starterKind.brainstorm",
    titleKey: "landingPage.starterTitle.brainstorm",
    prompt: "Help me brainstorm ideas. Ask me about the goal and any constraints first, then lay out a few directions worth exploring.",
  },
  {
    kindKey: "landingPage.starterKind.plan",
    titleKey: "landingPage.starterTitle.plan",
    prompt: "Help me plan this out. Ask what I'm trying to achieve first, then break it into clear steps and milestones.",
  },
  {
    kindKey: "landingPage.starterKind.draft",
    titleKey: "landingPage.starterTitle.draft",
    prompt: "Help me draft this. Ask about the audience and tone first, then propose an outline before we write.",
  },
  {
    kindKey: "landingPage.starterKind.research",
    titleKey: "landingPage.starterTitle.research",
    prompt: "Research two or three ways to approach this and lay out the tradeoffs with sources before recommending one.",
  },
];

export function LandingPage() {
  const { t } = useTranslation('chat');
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileAcceptRef = useRef<string>("");

  const isConnected = useChatStore((state) => state.isConnected);
  const sendMessage = useChatStore((state) => state.sendMessage);

  const { createWorkspaceConversation } = useProjectsStore();
  const reduce = useReducedMotion();

  // Click-outside to dismiss menus
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        plusMenuRef.current &&
        !plusMenuRef.current.contains(e.target as Node)
      ) {
        setShowPlusMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isLoading || !isConnected) return;
    setIsLoading(true);
    setError(null);
    try {
      await createWorkspaceConversation("New Chat"); // backend name — not translated
      sendMessage(input.trim());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('landingPage.failedToLoad'),
      );
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const applyStarter = (prompt: string) => {
    setInput(prompt);
    // Focus the composer and drop the cursor at the end so the user can edit.
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(prompt.length, prompt.length);
      }
    });
  };

  const handleFileUpload = (accept: string) => {
    fileAcceptRef.current = accept;
    setShowPlusMenu(false);
    setTimeout(() => {
      if (fileInputRef.current) {
        fileInputRef.current.accept = accept;
        fileInputRef.current.click();
      }
    }, 0);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) setAttachedFiles((prev) => [...prev, ...Array.from(files)]);
    e.target.value = "";
  };

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="relative flex h-full flex-col items-center justify-center overflow-hidden bg-canvas px-6">
      {/* Ambient cosmic backdrop — subtle starfield + nebula bloom. */}
      <CosmicField count={38} className="opacity-70" />

      <div className="relative z-10 w-full max-w-2xl">
        {/* ── Attention: a refined, compact editorial headline ── */}
        <div className="mb-6 text-center">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transitions.chrome}
          >
            <Eyebrow className="text-text-secondary">{t('landingPage.eyebrow')}</Eyebrow>
          </motion.div>
          <AnimatedHeadline
            as="h2"
            text={t('landingPage.headline')}
            className="mx-auto mt-2.5 max-w-xl text-[28px] md:text-[38px] font-sans font-[600] leading-[1.08] tracking-[-0.03em] text-gradient-brand"
          />
        </div>

        {/* ── Action: the composer card ── */}
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...transitions.editorial, delay: 0.4 }}
          className="rounded-md border border-hairline-soft bg-canvas shadow-soft focus-within:border-ink/20 focus-within:shadow-hover transition-all duration-base"
        >
          <div className="rounded-t-lg px-5 pb-2 pt-5">
            <TextareaAutosize
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('landingPage.composerPlaceholder')}
              disabled={isLoading || !isConnected}
              className="w-full resize-none border-0 bg-transparent text-base leading-relaxed text-ink placeholder-text-muted outline-none disabled:cursor-not-allowed disabled:opacity-50"
              minRows={2}
              maxRows={8}
            />

            {attachedFiles.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {attachedFiles.map((file, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1.5 rounded-md border border-hairline-soft bg-surface-soft px-2.5 py-1 text-xs text-ink"
                  >
                    <Paperclip className="h-3.5 w-3.5 text-text-muted" />
                    {file.name}
                    <button
                      onClick={() => removeFile(i)}
                      className="ml-0.5 text-text-muted hover:text-block-coral"
                      aria-label={t('landingPage.removeFile', { name: file.name })}
                    >
                      <X className="h-3 w-3" strokeWidth={2.5} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Bottom utility bar */}
          <div className="flex items-center justify-between rounded-b-lg border-t border-hairline-soft/60 px-4 py-3">
            <div className="relative" ref={plusMenuRef}>
              <button
                onClick={() => setShowPlusMenu(!showPlusMenu)}
                className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-soft text-text-secondary transition-colors hover:bg-hairline-soft hover:text-ink"
                title={t('landingPage.attachFiles')}
                aria-label={t('landingPage.attachFiles')}
              >
                <Plus className="h-4 w-4" />
              </button>

              {showPlusMenu && (
                <div className="animate-fade-in absolute bottom-full left-0 z-50 mb-2 w-48 overflow-hidden rounded-md border border-hairline-soft bg-canvas shadow-modal">
                  <button
                    onClick={() => handleFileUpload(".png,.jpg,.jpeg,.gif,.webp")}
                    className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-ink hover:bg-surface-soft"
                  >
                    <Image className="h-4 w-4 text-text-muted" />
                    {t('landingPage.uploadImage')}
                  </button>
                  <button
                    onClick={() => handleFileUpload(".pdf,.docx")}
                    className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-ink hover:bg-surface-soft"
                  >
                    <FileText className="h-4 w-4 text-text-muted" />
                    {t('landingPage.uploadDocument')}
                  </button>
                </div>
              )}
            </div>

            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading || !isConnected}
              className="flex h-9 items-center gap-2 rounded-pill bg-gradient-brand px-4 text-btn text-[15px] text-white shadow-glow-nebula transition-all hover:brightness-110 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-none disabled:bg-surface-soft disabled:text-text-muted disabled:opacity-60 disabled:shadow-none"
              title={t('landingPage.sendEnter')}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <span className="hidden sm:inline">{t('landingPage.send')}</span>
                  <SendHorizontal className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </motion.div>

        {error && (
          <p className="animate-fade-in mt-3 text-center text-sm font-[540] text-block-coral">
            {error}
          </p>
        )}

        {/* ── Interest: gapless prompt-starter bento (grid-flow-dense, no voids) ── */}
        <div className="mt-4 grid grid-flow-dense grid-cols-1 gap-2 sm:grid-cols-2">
          {STARTERS.map((s, i) => (
            <motion.button
              key={s.titleKey}
              type="button"
              onClick={() => applyStarter(s.prompt)}
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...transitions.editorial, delay: 0.5 + i * 0.06 }}
              className="group flex flex-col items-start gap-1.5 rounded-md border border-hairline-soft bg-surface-soft/50 p-3.5 text-left transition-all duration-base hover:border-ink/20 hover:bg-surface-soft hover:-translate-y-0.5"
            >
              <div className="flex w-full items-center justify-between">
                <span className="eyebrow-mono text-text-muted">{t(s.kindKey)}</span>
                <ArrowUpRight className="h-4 w-4 text-text-muted opacity-0 transition-all duration-base group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100" />
              </div>
              <span className="text-[15px] font-[540] tracking-[-0.01em] text-ink">
                {t(s.titleKey)}
              </span>
            </motion.button>
          ))}
        </div>

        <p className="mt-6 text-center text-xs text-text-muted">
          <kbd className="rounded border border-hairline-soft bg-surface-soft px-1.5 py-0.5 text-xs">
            Enter
          </kbd>{" "}
          {t('landingPage.hintSend')}{" "}
          <kbd className="rounded border border-hairline-soft bg-surface-soft px-1.5 py-0.5 text-xs">
            Shift + Enter
          </kbd>{" "}
          {t('landingPage.hintNewLine')}
        </p>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  );
}
