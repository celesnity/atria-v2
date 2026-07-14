/**
 * Pure reducer for the "Thinking…" indicator shown between turn start and the
 * first visible output (streamed token or tool activity). Fills the gap while a
 * reasoning model thinks internally before emitting its first token.
 */
export function nextIndicatorState(
  current: boolean,
  event: 'start' | 'chunk' | 'tool' | 'complete',
): boolean {
  switch (event) {
    case 'start':
      return true;
    case 'chunk':
    case 'tool':
    case 'complete':
      return false;
    default:
      return current;
  }
}
