import type { ReactNode } from 'react';

export interface SubTab {
  id: string;
  label: string;
  icon?: ReactNode;
  /** Optional count badge (e.g. open items). */
  badge?: number;
}

/**
 * Segmented sub-navigation for splitting a dense persona route into focused
 * pages. Fully custom-styled (see `.pr-subnav` in the dashboard GlobalStyle)
 * with a sliding-feel active pill, icons and optional count badges.
 */
export default function SubNav({
  tabs,
  value,
  onChange,
}: {
  tabs: SubTab[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="pr-subnav" role="tablist" aria-label="Chế độ xem">
      {tabs.map((t) => {
        const active = value === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`pr-subnav-tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(t.id)}
          >
            {t.icon ? <span className="pr-subnav-ico">{t.icon}</span> : null}
            <span>{t.label}</span>
            {t.badge ? <span className="pr-subnav-badge">{t.badge}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
