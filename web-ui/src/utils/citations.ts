// Inline citation refs like [WSM-RR-2040#2] render as badges; blockquotes
// starting with the unverified-suggestion marker render as warning callouts.

export const UNVERIFIED_MARKER = '⚠ Gợi ý chưa kiểm chứng';

// Chunk ids are `<DOC_ID>#<chunk>` where DOC_ID starts with 2+ uppercase
// letters (WSM-RR-2040, TSB-RR-2026-03, DOC002). Plain [note] or array[0]
// stay untouched.
const CITATION_RE = /\[([A-Z]{2,}[A-Z0-9-]*#\d+)\]/g;

export type CitationPart = string | { cite: string };

export function splitCitations(text: string): CitationPart[] {
  if (!text) return [];
  const parts: CitationPart[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION_RE)) {
    const idx = match.index ?? 0;
    if (idx > last) parts.push(text.slice(last, idx));
    parts.push({ cite: match[1] });
    last = idx + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function isUnverifiedSuggestion(text: string): boolean {
  return text.trimStart().startsWith(UNVERIFIED_MARKER);
}
