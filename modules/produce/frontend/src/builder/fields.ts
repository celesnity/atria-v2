import type { NodePortMeta } from './engineApi';

/** Secret name heuristics — if the port name contains any of these, use password widget. */
const SECRET_HINTS = ['secret', 'password', 'token', 'api_key', 'apikey', 'credential'];

/**
 * Map a NodePortMeta to the appropriate form widget type.
 *
 * Priority:
 * 1. enum type OR non-empty options array → 'select'
 * 2. Explicit type matches: textarea, number, boolean, json, code
 * 3. Secret name heuristics → 'password'
 * 4. Default → 'text'
 */
export function widgetFor(
  port: NodePortMeta,
): 'text' | 'textarea' | 'number' | 'switch' | 'select' | 'json' | 'password' {
  const t = port.type.toLowerCase();

  if (t === 'enum' || port.options.length > 0) return 'select';
  if (t === 'textarea') return 'textarea';
  if (t === 'number' || t === 'integer' || t === 'float') return 'number';
  if (t === 'boolean' || t === 'bool') return 'switch';
  if (t === 'json' || t === 'object' || t === 'dict') return 'json';
  if (t === 'code') return 'json'; // render code as a JSON/textarea widget

  const nameLower = port.name.toLowerCase();
  if (SECRET_HINTS.some((hint) => nameLower.includes(hint))) return 'password';

  return 'text';
}
