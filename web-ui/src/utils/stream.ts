/**
 * Remove the last `n` Unicode code points from `text`.
 *
 * Used by the message_retract WS event: the backend counts streamed text in
 * code points (Python len), so trimming must use the same unit — plain
 * String.slice would split astral characters (emoji, some CJK).
 */
export function trimCodePoints(text: string, n: number): string {
  if (n <= 0) return text;
  const points = Array.from(text);
  if (n >= points.length) return '';
  return points.slice(0, points.length - n).join('');
}
