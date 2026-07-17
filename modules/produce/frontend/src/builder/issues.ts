import type { WorkflowGraph } from './engineApi';

export interface MappedIssues {
  /** Issues keyed by node key — each issue string is attached to the first single-quoted
   *  token that matches a known node key. */
  byNodeKey: Record<string, string[]>;
  /** Issues that don't match any node key. */
  general: string[];
}

const QUOTED_RE = /'([^']+)'/g;

/**
 * Map a flat list of engine validation issue strings into per-node buckets.
 *
 * Engine issue strings quote the offending node key in single quotes, e.g.:
 *   "decision 'chk' must have a 'pass' branch"
 *
 * Strategy: scan all single-quoted tokens in the string; attach to the first
 * token that is a known node key. If none match, the issue is general.
 */
export function mapIssues(issues: string[], graph: WorkflowGraph): MappedIssues {
  const knownKeys = new Set(graph.nodes.map((n) => n.key));
  const byNodeKey: Record<string, string[]> = {};
  const general: string[] = [];

  for (const issue of issues) {
    QUOTED_RE.lastIndex = 0; // reset stateful regex
    let matched = false;
    let m: RegExpExecArray | null;
    while ((m = QUOTED_RE.exec(issue)) !== null) {
      const token = m[1];
      if (knownKeys.has(token)) {
        if (!byNodeKey[token]) byNodeKey[token] = [];
        byNodeKey[token].push(issue);
        matched = true;
        break;
      }
    }
    if (!matched) {
      general.push(issue);
    }
  }

  return { byNodeKey, general };
}
