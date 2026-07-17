import { createContext, createElement, useContext, useEffect, useState, type ReactNode } from 'react';

/**
 * Popup portal layer for module dashboards.
 *
 * When a module is embedded in the Minder host, its root element lives inside a
 * scrolling / possibly transformed host container. A modal that portals into the
 * module's own scope is therefore trapped in that container instead of overlaying
 * the whole viewport ("the SDK doesn't pass the popup through").
 *
 * `MinderPopupProvider` mounts a single layer node directly on `document.body`
 * (top of the stacking order, outside any host clip/transform) and exposes it via
 * `useMinderPopupTarget()`. Modules pass that node as the portal target for
 * modals, popovers, tooltips and select dropdowns.
 *
 * The layer copies the module's theme scope so scoped CSS variables still resolve
 * on the portaled content:
 *  - `scopeAttribute` — the same attribute used as the module's Mantine
 *    `cssVariablesSelector` (e.g. `data-produce-dashboard`).
 *  - `colorScheme` — mirrored onto `data-mantine-color-scheme` for light/dark.
 */
const PopupTargetContext = createContext<HTMLElement | null>(null);

export interface MinderPopupProviderProps {
  children: ReactNode;
  /** Attribute to stamp on the layer so Mantine's scoped CSS variables match
   *  (pass the same string used for `cssVariablesSelector`, without brackets). */
  scopeAttribute?: string;
  /** Active color scheme, mirrored to `data-mantine-color-scheme`. */
  colorScheme?: 'light' | 'dark';
  /** z-index for the layer (default sits above typical host chrome). */
  zIndex?: number;
}

export function MinderPopupProvider({
  children,
  scopeAttribute,
  colorScheme,
  zIndex = 2_147_483_000,
}: MinderPopupProviderProps) {
  const [layer, setLayer] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const el = document.createElement('div');
    el.setAttribute('data-minder-popup-layer', '');
    // A zero-size, fixed, high-z mount point. Portaled fixed overlays escape the
    // zero size and paint above host chrome; the node itself captures no clicks.
    el.style.cssText = `position:fixed;top:0;left:0;width:0;height:0;z-index:${zIndex};`;
    document.body.appendChild(el);
    setLayer(el);
    return () => {
      document.body.removeChild(el);
      setLayer(null);
    };
  }, [zIndex]);

  // Keep theme scope in sync so scoped CSS variables + color scheme resolve on
  // the portaled popups (updates without re-mounting the layer).
  useEffect(() => {
    if (!layer) return;
    if (scopeAttribute) layer.setAttribute(scopeAttribute, '');
    if (colorScheme) {
      layer.setAttribute('data-mantine-color-scheme', colorScheme);
      // Also drive the CSS `color-scheme` property so any `light-dark()` values
      // resolve to the right side on portaled content.
      layer.style.colorScheme = colorScheme;
    }
  }, [layer, scopeAttribute, colorScheme]);

  return createElement(PopupTargetContext.Provider, { value: layer }, children);
}

/**
 * Returns the host-level popup layer node (or `null` before it mounts / when
 * rendered standalone). Pass it as the portal target, e.g.:
 *
 *   const target = useMinderPopupTarget();
 *   <Modal portalProps={{ target: target ?? undefined }} ... />
 */
export function useMinderPopupTarget(): HTMLElement | null {
  return useContext(PopupTargetContext);
}
