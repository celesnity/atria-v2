import enCommon from './locales/en/common.json';
import enSettings from './locales/en/settings.json';
import enLayout from './locales/en/layout.json';
import enChat from './locales/en/chat.json';
import enArtifacts from './locales/en/artifacts.json';
import viCommon from './locales/vi/common.json';
import viSettings from './locales/vi/settings.json';
import viLayout from './locales/vi/layout.json';
import viChat from './locales/vi/chat.json';
import viArtifacts from './locales/vi/artifacts.json';

export const resources = {
  en: { common: enCommon, settings: enSettings, layout: enLayout, chat: enChat, artifacts: enArtifacts },
  vi: { common: viCommon, settings: viSettings, layout: viLayout, chat: viChat, artifacts: viArtifacts },
} as const;
// ponytail: hand-listed imports; when the sweep adds namespaces, add the pair here.
// Upgrade path if this grows unwieldy: import.meta.glob('./locales/**/*.json').
