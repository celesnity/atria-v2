/**
 * Tools API client — per-tool enable/disable.
 *
 * Toggling a tool off strips its schema from the LLM request on the next turn,
 * cutting it from context without a restart.
 */

const API_BASE = '/api';

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  enabled: boolean;
}

async function fetchAPI<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || err.message || `API error: ${response.statusText}`);
  }
  return response.json();
}

/** List every built-in tool with its current enabled state. */
export async function listTools(): Promise<ToolInfo[]> {
  const data = await fetchAPI<{ tools: ToolInfo[] }>('/tools');
  return data.tools;
}

/** Persist the full set of disabled tool names. Returns the refreshed list. */
export async function updateDisabledTools(disabled: string[]): Promise<ToolInfo[]> {
  const data = await fetchAPI<{ tools: ToolInfo[] }>('/tools', {
    method: 'PUT',
    body: JSON.stringify({ disabled_tools: disabled }),
  });
  return data.tools;
}
