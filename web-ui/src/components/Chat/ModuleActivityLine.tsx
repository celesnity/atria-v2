import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { Message } from '../../types';
import { JsonView } from './JsonView';

interface Props {
  message: Message;
  hasResult: boolean;
}

const GENERIC = { running: 'Working…', done: 'Done' };

export type ActivityView = {
  kind: 'running' | 'done' | 'error';
  text: string;
  /** Verbose error detail — tool name, raw error, stack hint. Only set on error. */
  detail?: string;
  /** Verbose machine-readable payload for the expandable detail. Set on BOTH
   *  error and done, so successes are as inspectable as failures. */
  debug?: {
    tool?: string;
    args?: Record<string, unknown>;
    error?: string;
    success?: boolean;
    summary?: unknown;
    result?: unknown;
    call_id?: string;
  };
};

/**
 * Full, verbose debug payload for the expandable detail — everything the backend
 * attached to this tool call (name, args, success flag, summary, raw result,
 * call id), so both failures AND successes are fully inspectable from the chat.
 */
function buildDebug(
  message: Message,
  extra?: Record<string, unknown>,
): NonNullable<ActivityView['debug']> {
  return {
    tool: message.tool_name,
    args: message.tool_args,
    success: message.tool_success,
    summary: message.tool_summary,
    result: message.tool_result,
    call_id: message.tool_call_id,
    ...extra,
  };
}

/**
 * Extract a human-readable error string from every place the backend might
 * stash it: `tool_error`, `tool_result.error`, `tool_result.content` when
 * `success === false`, or the stringified result as a last resort.
 */
function extractError(message: Message): string {
  if (message.tool_error) return String(message.tool_error);
  const r = message.tool_result as any;
  if (r && typeof r === 'object') {
    if (r.error) return String(r.error);
    if (r.success === false && r.content) return String(r.content);
    if (r.message) return String(r.message);
  }
  if (typeof r === 'string' && r) return r;
  return 'no error message';
}

/**
 * Pure helper: derives the view state from a message and whether a result has
 * arrived. Exported for unit testing without a DOM environment.
 */
export function activityView(message: Message, hasResult: boolean): ActivityView {
  const failed =
    message.tool_success === false ||
    (message.tool_result && (message.tool_result as any).success === false) ||
    !!message.tool_error;

  if (failed) {
    const err = extractError(message);
    const tool = message.tool_name || 'tool';
    const firstLine = err.split('\n')[0].trim();
    return {
      kind: 'error',
      text: `Couldn’t finish — ${tool} failed: ${firstLine}`,
      detail: err,
      debug: buildDebug(message, { error: err }),
    };
  }

  const labels = message.activity ?? GENERIC;
  return hasResult
    ? { kind: 'done', text: labels.done, debug: buildDebug(message) }
    : { kind: 'running', text: labels.running };
}

/**
 * Friendly, non-technical activity line shown in Simple Mode in place of the
 * technical tool-call card. No commands, paths, or buttons — just plain
 * language with a spinner while running and a quiet checkmark when done.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export function ModuleActivityLine({ message, hasResult }: Props) {
  const { t } = useTranslation('chat');
  const view = activityView(message, hasResult);
  const [expanded, setExpanded] = useState(false);

  // Running: a spinner only — there is nothing to inspect yet.
  if (view.kind === 'running') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-[13px] text-ink/70">
        <span className="inline-block w-3 h-3 border-[1.5px] border-ink/30 border-t-transparent rounded-md animate-spin flex-shrink-0" />
        <span>{view.text}</span>
      </div>
    );
  }

  // Error AND done share the same expandable "+ details / − hide" affordance, so
  // a successful call is as inspectable as a failed one. The payload is the full
  // verbose {tool, args, success, summary, result, call_id} dump.
  const isError = view.kind === 'error';
  // Structured payload → render as a JSON tree; only fall back to plain text
  // when there is no debug object to inspect.
  const debugObj =
    view.debug && typeof view.debug === 'object' && Object.keys(view.debug).length > 0
      ? view.debug
      : null;
  const detailText = view.detail || '';
  const hasDetail = !!debugObj || detailText.trim().length > 0;

  const tone = isError
    ? { text: 'text-block-coral', pre: 'bg-block-coral/10 border-block-coral/30' }
    : { text: 'text-semantic-success', pre: 'bg-semantic-success/10 border-semantic-success/30' };
  const Icon = isError ? AlertTriangle : CheckCircle2;

  return (
    <div className={`px-3 py-2 text-[13px] ${tone.text} space-y-1`}>
      <div className="flex items-start gap-2">
        <Icon
          aria-hidden
          className="w-3.5 h-3.5 mt-0.5 flex-shrink-0"
          strokeWidth={isError ? 1.5 : 2}
        />
        <span className="flex-1 break-words">{view.text}</span>
        {hasDetail && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="text-[11px] font-mono opacity-70 hover:opacity-100 transition-opacity flex-shrink-0"
            aria-label={expanded ? t('activityLine.hideDetail') : t('activityLine.showDetail')}
          >
            {expanded ? t('activityLine.hide') : t('activityLine.details')}
          </button>
        )}
      </div>
      {hasDetail && expanded && (
        <div className="ml-6 max-h-80 overflow-auto" aria-label={t('activityLine.detailPayload')}>
          {debugObj ? (
            <JsonView data={debugObj} />
          ) : (
            <pre
              className={`text-[11px] font-mono whitespace-pre-wrap break-words border rounded-md px-2 py-1.5 ${tone.pre}`}
            >
{detailText}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
