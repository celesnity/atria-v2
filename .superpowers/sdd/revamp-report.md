# Theme-Aware Module Template UI — Revamp Report

## Summary

Rewrote all frontend source files under `modules/module_template/frontend/src/` to consume
`minder-ui-sdk` design tokens instead of hardcoded hex colors. Every component now calls
`useMinderTheme()` at the top of its render function to obtain `tokens`, and all color
references use the appropriate semantic token field.

---

## Files Changed

### `src/theme.ts`
- **Removed** `COLORS`, `STATUS_COLORS`, `CHART_COLORS` exports (all replaced by tokens).
- **Added** `statusColor(tokens, status)` helper — maps `queued`→`tokens.warning`,
  `running`→`tokens.primary`, `done`→`tokens.success`, `error`→`tokens.error`,
  else `tokens.textMuted`.
- **Kept** `variants` (motion variants, color-agnostic) unchanged.
- Added `import type { MinderTokens } from 'minder-ui-sdk'` for the helper's param type.

### `src/ui/StatCard.tsx`
- Added `useMinderTheme()` call.
- Card `background` → `tokens.surface`; `border` → `tokens.border`.
- Resting shadow → `tokens.cardShadow`; hover shadow → `tokens.cardHoverShadow`.
- Icon color → `tokens.primary`; label → `tokens.textMuted`; value → `tokens.text`.

### `src/ui/StatHeader.tsx`
- Added `useMinderTheme()` call.
- `borderBottom` hex → `tokens.border`.
- Brand chip `background` → `tokens.brandGradient`.
- Title text gradient → `tokens.titleGradient` (with `WebkitBackgroundClip: 'text'`).
- Health dot color driven by `tokens.warning` / `tokens.success` / `tokens.error`.
- Muted text → `tokens.textMuted`. No full-page background set here.

### `src/ui/Toast.tsx`
- Extracted `ToastItem` inner component so it can call `useMinderTheme()` per-toast
  (the provider itself doesn't need tokens, but each toast item renders inside the provider).
- `KIND_COLORS` removed; accent per kind is now `tokens.success`, `tokens.error`, `tokens.info`.
- Toast surface → `tokens.surface`; text → `tokens.text`; shadow → `tokens.cardShadow`.

### `src/ui/AnimatedNumber.tsx`
- No color references; left untouched.

### `src/panels/JobsPanel.tsx`
- Added `useMinderTheme()`. Removed `STATUS_COLORS` import.
- Button background → `tokens.primary`.
- Empty-state / footer text → `tokens.textMuted`.
- Job card `background` → `tokens.surface`; `border` → `tokens.border`.
- Progress track background → `tokens.surfaceAlt`.
- Status badge color via `statusColor(tokens, job.status)`.

### `src/panels/MediaPanel.tsx`
- Added `useMinderTheme()`. Removed `COLORS` usage.
- Drop zone border and drag-active color → `tokens.primary` / `tokens.border`.
- Media card `background` → `tokens.surface`; `border` → `tokens.border`.
- Text colors → `tokens.text` / `tokens.textMuted`.
- `useToast()` kept working (no changes to Toast API).

### `src/panels/DataPanel.tsx`
- Added `useMinderTheme()`. Replaced all hex colors with tokens.
- Refresh button border/text → `tokens.border` / `tokens.textMuted`.
- Conversation cards → `tokens.surface`, `tokens.border`, `tokens.primary`, `tokens.text`, `tokens.textMuted`.

### `src/panels/MetricsPanel.tsx`
- Added `useMinderTheme()`. Removed `STATUS_COLORS` and `CHART_COLORS` imports.
- Bar chart status colors via `statusColor(tokens, entry.status)`.
- Pie chart: status-mapped statuses use `statusColor(tokens, ...)`, unknown statuses fall back to
  `tokens.chart[i % tokens.chart.length]` (so all chart slice colors are token-driven).
- `CartesianGrid`, `XAxis`, `YAxis`, `Tooltip` all use `tokens.border` / `tokens.textMuted` / `tokens.surface` / `tokens.text`.
- Media storage card → `tokens.surface`, `tokens.border`, `tokens.text`, `tokens.textMuted`.

### `src/ShowcaseBlock.tsx`
- Converted from Tailwind class-based token references (`bg-bg-000`, `text-text-300`, etc.)
  to inline style `useMinderTheme()` tokens.
- Surface → `tokens.surface`; border → `tokens.border`; text → `tokens.text` / `tokens.textMuted`.
- Progress track → `tokens.surfaceAlt`; fill → `tokens.secondary`.
- Buttons → `tokens.surfaceAlt` background with `tokens.border` border.

---

## Removed-Exports Grep Result

```
$ grep -rn "COLORS\|STATUS_COLORS\|CHART_COLORS" modules/module_template/frontend/src
(no output)
```

No remaining references to the removed exports. ✓

---

## Judgment Calls

1. **`ToastItem` split** — `ToastProvider` renders its children and toast list without itself
   needing tokens, but each rendered `motion.div` toast needs tokens for its colors. Splitting into
   a `ToastItem` sub-component is the cleanest way to call `useMinderTheme()` per-toast without
   restructuring the context/provider pattern.

2. **`MetricsPanel` pie fallback** — For the pie chart, status-known entries use `statusColor`
   (which is semantically correct), and entries with unknown status strings get `tokens.chart[i]`
   instead of a hardcoded color, preserving the original "cycle through chart palette" behavior
   while staying theme-aware.

3. **`ShowcaseBlock` Tailwind → inline** — The original used host-app Tailwind classes
   (`bg-bg-000`, `text-text-100` etc.) which are host-app specifics, not the SDK token system.
   Migrated to inline styles with `tokens` to make them correctly theme-aware per the task spec.

4. **`theme.ts` type import** — `MinderTokens` is typed via `import type` (erased at compile time)
   so there's no runtime import cost; the function itself is just a plain helper.
