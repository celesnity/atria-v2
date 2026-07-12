import { describe, expect, it } from 'vitest';
import { trimCodePoints } from './stream';

describe('trimCodePoints', () => {
  it('trims from the end by code points', () => {
    expect(trimCodePoints('hello', 2)).toBe('hel');
  });

  it('handles zero and negative counts', () => {
    expect(trimCodePoints('hello', 0)).toBe('hello');
    expect(trimCodePoints('hello', -3)).toBe('hello');
  });

  it('clears the string when trimming everything or more', () => {
    expect(trimCodePoints('abc', 3)).toBe('');
    expect(trimCodePoints('abc', 10)).toBe('');
  });

  it('counts astral characters as one code point (backend uses Python len)', () => {
    // '🚗' is 2 UTF-16 units but 1 code point
    expect(trimCodePoints('xe 🚗', 1)).toBe('xe ');
    expect(trimCodePoints('xe 🚗 ok', 3)).toBe('xe 🚗');
  });
});
