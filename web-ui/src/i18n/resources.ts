import enCommon from './locales/en/common.json';
import enSettings from './locales/en/settings.json';
import viCommon from './locales/vi/common.json';
import viSettings from './locales/vi/settings.json';

export const resources = {
  en: { common: enCommon, settings: enSettings },
  vi: { common: viCommon, settings: viSettings },
} as const;
// ponytail: hand-listed imports; when the sweep adds namespaces, add the pair here.
// Upgrade path if this grows unwieldy: import.meta.glob('./locales/**/*.json').
