import { defineConfig } from 'i18next-cli';

export default defineConfig({
  locales: ['en', 'vi'],
  extract: {
    input: ['src/**/*.{ts,tsx}'],
    output: 'src/i18n/locales/{{language}}/{{namespace}}.json',
    primaryLanguage: 'en',
    secondaryLanguages: ['vi'],
    defaultNS: 'common',
    nsSeparator: ':',
    keySeparator: '.',
    sort: true,
    // ponytail: extract only ADDS keys, never strips. Dynamic call sites like
    // t(labelKey) / t(meta.labelKey) are invisible to static analysis, so
    // removeUnusedKeys:true would delete keys the UI needs at runtime.
    removeUnusedKeys: false,
    defaultValue: (key, _ns, lang) => (lang === 'en' ? key : ''),
  },
});
