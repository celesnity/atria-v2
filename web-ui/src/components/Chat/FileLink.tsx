import { Children, Fragment, type ReactNode } from 'react';
import { useChatStore } from '../../stores/chat';
import { useViewerTabsStore } from '../../stores/viewerTabs';
import { looksLikeFileToken, toWorkspaceRelative } from '../../utils/fileLinks';

interface FileLinkProps {
  /** The raw path/filename token exactly as written in the chat. */
  token: string;
  /** 'chip' matches inline-code path pills; 'text' matches bold/inline text. */
  variant?: 'chip' | 'text';
}

/**
 * Renders a file path/name mentioned in chat as a clickable link that opens the
 * file in the right-hand ArtifactViewer. Falls back to plain text when the path
 * can't be resolved inside the current conversation workspace (no dead links).
 */
export function FileLink({ token, variant = 'text' }: FileLinkProps) {
  const convId = useChatStore((s) => s.currentSessionId);
  const workingDir = useChatStore((s) => s.status?.working_dir ?? '');
  const openTab = useViewerTabsStore((s) => s.openTab);

  const rel = convId ? toWorkspaceRelative(token, workingDir) : null;

  // Not resolvable → render the plain token so we never produce a dead link.
  if (!convId || rel == null) {
    return variant === 'chip' ? (
      <code className="text-[14px] px-1.5 py-0.5 rounded-sm font-mono bg-canvas/60 text-ink border border-hairline-soft">
        {token}
      </code>
    ) : (
      <>{token}</>
    );
  }

  const onClick = () => openTab(convId, rel);

  if (variant === 'chip') {
    return (
      <button
        type="button"
        onClick={onClick}
        title={`Open ${rel}`}
        className="text-[14px] px-1.5 py-0.5 rounded-sm font-mono bg-canvas/60 text-sky-500 border border-hairline-soft hover:border-sky-400/60 hover:text-sky-400 cursor-pointer transition-colors align-baseline"
      >
        {token}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      title={`Open ${rel}`}
      className="font-[540] text-sky-500 hover:text-sky-400 underline underline-offset-2 decoration-sky-400/40 hover:decoration-sky-400 cursor-pointer"
    >
      {token}
    </button>
  );
}

/**
 * Renders a free-text string, turning any file-like tokens into clickable
 * FileLinks while preserving surrounding text and whitespace. Used for tool
 * result summary lines like "Created sample_accounts.csv • 273 B • 6 lines".
 */
export function LinkifiedText({ text }: { text: string }) {
  const parts = text.split(/(\s+)/); // keep whitespace chunks to preserve layout
  return (
    <>
      {parts.map((part, i) => {
        // Peel trailing punctuation off the token for detection, keep it visible.
        const m = /^(.*?)([.,;:!?)\]]*)$/.exec(part);
        const core = m ? m[1] : part;
        const trail = m ? m[2] : '';
        if (core && looksLikeFileToken(core)) {
          return (
            <Fragment key={i}>
              <FileLink token={core} variant="text" />
              {trail}
            </Fragment>
          );
        }
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </>
  );
}

/**
 * Wraps mixed markdown children (strings + elements), turning file-like tokens
 * inside the string parts into clickable FileLinks while leaving already-rendered
 * elements (bold, inline code, links, nested lists) untouched. Used for list
 * items and table cells so every file in a returned list is clickable.
 */
export function LinkifiedChildren({ children }: { children: ReactNode }) {
  return (
    <>
      {Children.map(children, (child, i) =>
        typeof child === 'string' ? <LinkifiedText key={i} text={child} /> : child
      )}
    </>
  );
}
