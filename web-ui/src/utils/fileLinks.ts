// Detect and resolve file references mentioned in chat text so they can be
// opened in the right-hand ArtifactViewer via viewerTabs.openTab().
//
// The agent typically writes either an absolute container path
// (e.g. /root/.atria/workspaces/user-1/new-chat/sample_accounts.csv) or a bare
// filename (sample_accounts.csv). openTab() expects a path RELATIVE to the
// conversation workspace, so we strip the workspace prefix here.

// File extension at the end of a token (bounded to avoid turning arbitrary
// dotted words into links). Broad but reasonable for a coding assistant.
const FILE_EXT_RE = /\.[a-z0-9]{1,8}$/i;

/** A token looks like a filesystem path: has a separator and a filename+ext. */
export function looksLikePath(token: string): boolean {
  const t = token.trim();
  if (!t || /\s/.test(t)) return false; // a path token has no inner whitespace
  if (!t.includes('/')) return false;
  const base = t.split('/').pop() || '';
  return FILE_EXT_RE.test(base);
}

/** A bare token looks like a filename: no separators but has an extension. */
export function looksLikeFilename(token: string): boolean {
  const t = token.trim();
  if (!t || /\s/.test(t)) return false;
  if (t.includes('/')) return false;
  return FILE_EXT_RE.test(t);
}

/** True when a token is worth turning into a clickable file link. */
export function looksLikeFileToken(token: string): boolean {
  return looksLikePath(token) || looksLikeFilename(token);
}

/**
 * Convert a mentioned path/filename into a path relative to the conversation
 * workspace, suitable for openTab(). Returns null when the token can't be
 * resolved to something inside the workspace, so callers can leave it as plain
 * text instead of producing a dead link.
 */
export function toWorkspaceRelative(token: string, workingDir: string): string | null {
  const t = token.trim();
  if (!t) return null;
  const root = (workingDir || '').replace(/\/+$/, '');

  if (t.startsWith('/')) {
    // Absolute path inside the workspace → strip the prefix.
    if (root && (t === root || t.startsWith(root + '/'))) {
      return t.slice(root.length).replace(/^\/+/, '');
    }
    // Absolute but outside the workspace: not reachable via the conv fs route.
    return null;
  }

  // Already relative (or a bare filename) → use as-is.
  return t.replace(/^\.\//, '');
}
