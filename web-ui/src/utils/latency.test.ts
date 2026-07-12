import { describe, expect, it } from 'vitest';
import { formatLatency, latencySummary } from './latency';

describe('formatLatency', () => {
  it('renders sub-second values in milliseconds', () => {
    expect(formatLatency(0)).toBe('0ms');
    expect(formatLatency(850.4)).toBe('850ms');
  });

  it('renders seconds with one decimal', () => {
    expect(formatLatency(1000)).toBe('1.0s');
    expect(formatLatency(3240)).toBe('3.2s');
    expect(formatLatency(59949)).toBe('59.9s');
  });

  it('renders minutes with zero-padded seconds', () => {
    expect(formatLatency(65000)).toBe('1m 05s');
    expect(formatLatency(125000)).toBe('2m 05s');
  });

  it('is defensive about garbage input', () => {
    expect(formatLatency(-1)).toBe('—');
    expect(formatLatency(NaN)).toBe('—');
  });
});

describe('latencySummary', () => {
  it('returns null without metrics or without a TTFT', () => {
    expect(latencySummary(undefined)).toBeNull();
    expect(latencySummary({ totalMs: 5000 })).toBeNull();
  });

  it('shows TTFT alone when total is missing', () => {
    expect(latencySummary({ ttftMs: 3240 })).toBe('first token 3.2s');
  });

  it('shows TTFT and total together', () => {
    expect(latencySummary({ ttftMs: 3240, totalMs: 26800 })).toBe(
      'first token 3.2s · total 26.8s'
    );
  });
});
