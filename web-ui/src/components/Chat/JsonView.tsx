import { useState } from 'react';
import { ChevronRight } from 'lucide-react';

/**
 * Compact, collapsible, syntax-coloured JSON viewer tuned for the narrow chat
 * rail (~20vw). Renders structured tool payloads as an inspectable key/value
 * tree instead of a raw `JSON.stringify` blob: keys, strings, numbers and
 * booleans each carry a brand-palette colour, nested objects/arrays collapse,
 * and long strings wrap rather than forcing horizontal scroll.
 */

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

const CLR = {
  key: 'text-accent-2',
  string: 'text-semantic-success',
  number: 'text-block-lilac',
  bool: 'text-accent-3',
  null: 'text-ink/35',
  punc: 'text-ink/30',
  preview: 'text-ink/30',
} as const;

function Primitive({ value }: { value: Exclude<Json, Json[] | object> }) {
  if (typeof value === 'string') {
    return (
      <span className={`${CLR.string} break-words whitespace-pre-wrap`}>
        "{value}"
      </span>
    );
  }
  if (typeof value === 'number') return <span className={CLR.number}>{value}</span>;
  if (typeof value === 'boolean') return <span className={CLR.bool}>{String(value)}</span>;
  return <span className={CLR.null}>null</span>;
}

function isContainer(v: Json): v is Json[] | { [k: string]: Json } {
  return v !== null && typeof v === 'object';
}

function entriesOf(v: Json[] | { [k: string]: Json }): Array<[string, Json]> {
  return Array.isArray(v)
    ? v.map((item, i) => [String(i), item] as [string, Json])
    : Object.entries(v);
}

function Node({
  k,
  value,
  depth,
  isLast,
}: {
  k?: string;
  value: Json;
  depth: number;
  isLast: boolean;
}) {
  const container = isContainer(value);
  // Collapse deep or large containers by default; keep the top two levels open.
  const childCount = container ? entriesOf(value).length : 0;
  const [open, setOpen] = useState(depth < 2 && childCount <= 24);

  const comma = isLast ? null : <span className={CLR.punc}>,</span>;
  const keyLabel = k !== undefined && (
    <>
      <span className={CLR.key}>{k}</span>
      <span className={CLR.punc}>: </span>
    </>
  );

  if (!container) {
    return (
      <div className="whitespace-pre-wrap break-words">
        {keyLabel}
        <Primitive value={value as Exclude<Json, Json[] | object>} />
        {comma}
      </div>
    );
  }

  const isArr = Array.isArray(value);
  const open_b = isArr ? '[' : '{';
  const close_b = isArr ? ']' : '}';
  const kids = entriesOf(value);

  if (childCount === 0) {
    return (
      <div>
        {keyLabel}
        <span className={CLR.punc}>{open_b}{close_b}</span>
        {comma}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-start gap-0.5 text-left hover:opacity-80 focus-visible:outline-none focus-visible:shadow-focus-ring rounded-sm"
        aria-expanded={open}
      >
        <ChevronRight
          className={`w-3 h-3 mt-[3px] flex-shrink-0 ${CLR.punc} transition-transform duration-fast ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        />
        <span>
          {keyLabel}
          <span className={CLR.punc}>{open_b}</span>
          {!open && (
            <span className={CLR.preview}>
              {' '}
              {childCount} {isArr ? 'item' : 'key'}
              {childCount === 1 ? '' : 's'} {close_b}
              {comma}
            </span>
          )}
        </span>
      </button>

      {open && (
        <div className="border-l border-hairline-soft/40 ml-[5px] pl-2">
          {kids.map(([ck, cv], i) => (
            <Node
              key={ck}
              k={isArr ? undefined : ck}
              value={cv}
              depth={depth + 1}
              isLast={i === kids.length - 1}
            />
          ))}
        </div>
      )}
      {open && (
        <div>
          <span className={CLR.punc}>{close_b}</span>
          {comma}
        </div>
      )}
    </div>
  );
}

export function JsonView({ data }: { data: unknown }) {
  return (
    <div className="font-mono text-[11.5px] leading-[1.6] text-ink/60 rounded-md bg-surface-soft/60 px-2.5 py-2 overflow-x-auto">
      <Node value={data as Json} depth={0} isLast />
    </div>
  );
}
