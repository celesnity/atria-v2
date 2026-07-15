import { describe, it, expect, afterEach } from 'vitest';
import i18n from './index';

describe('i18n', () => {
  it('initializes with en and vi', () => {
    expect(i18n.options.supportedLngs).toContain('en');
    expect(i18n.options.supportedLngs).toContain('vi');
  });

  it('falls back to en for a missing vi key', async () => {
    await i18n.changeLanguage('vi');
    // key exists in en/common.json only (no vi translation):
    expect(i18n.t('common:appName')).toBe('Minder');
  });

  it('falls back to en when vi value is an empty string', async () => {
    // Simulate what pnpm i18n:extract produces: seeding vi with appName: ""
    i18n.addResource('vi', 'common', 'appName', '');
    await i18n.changeLanguage('vi');
    // returnEmptyString: false must cause i18next to treat "" as missing and
    // fall back to the en value instead of returning a blank string.
    expect(i18n.t('common:appName')).toBe('Minder');
  });

  afterEach(async () => {
    // Reset to en so tests don't bleed language state into each other
    await i18n.changeLanguage('en');
  });
});
