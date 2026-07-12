// D7 rendering conventions: inline citation refs like [WSM-RR-2040#2] become
// styled badges; blockquotes beginning with the unverified-suggestion marker
// get warning styling. splitCitations is the pure half of that.
import { describe, expect, it } from 'vitest';

import { isUnverifiedSuggestion, splitCitations, UNVERIFIED_MARKER } from './citations';

describe('splitCitations', () => {
  it('extracts manual citation refs', () => {
    const parts = splitCitations('Khớp CV bên trong bị mòn [WSM-RR-2040#2].');
    expect(parts).toEqual([
      'Khớp CV bên trong bị mòn ',
      { cite: 'WSM-RR-2040#2' },
      '.',
    ]);
  });

  it('handles multiple citations and EK-style ids', () => {
    const parts = splitCitations('a [TSB-RR-2026-03#0] b [DOC002#12] c');
    expect(parts).toEqual([
      'a ',
      { cite: 'TSB-RR-2026-03#0' },
      ' b ',
      { cite: 'DOC002#12' },
      ' c',
    ]);
  });

  it('leaves plain text and non-citation brackets alone', () => {
    expect(splitCitations('no citations here')).toEqual(['no citations here']);
    expect(splitCitations('array[0] and [note]')).toEqual(['array[0] and [note]']);
  });

  it('returns empty array for empty input', () => {
    expect(splitCitations('')).toEqual([]);
  });
});

describe('isUnverifiedSuggestion', () => {
  it('detects the marker at the start of blockquote text', () => {
    expect(isUnverifiedSuggestion(`${UNVERIFIED_MARKER}: thử kiểm tra rotuyn`)).toBe(true);
    expect(isUnverifiedSuggestion('  ⚠ Gợi ý chưa kiểm chứng — check')).toBe(true);
  });

  it('rejects ordinary quotes', () => {
    expect(isUnverifiedSuggestion('a normal quote')).toBe(false);
  });
});
