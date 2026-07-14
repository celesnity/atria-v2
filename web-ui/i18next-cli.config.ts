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
    defaultValue: (key, _ns, lang) => (lang === 'en' ? key : ''),
  },
});
