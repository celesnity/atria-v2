import { describe, it, expect } from 'vitest';
import i18n from './index';

describe('i18n', () => {
  it('initializes with en and vi', () => {
    expect(i18n.options.supportedLngs).toContain('en');
    expect(i18n.options.supportedLngs).toContain('vi');
  });

  it('falls back to en for a missing vi key', async () => {
    await i18n.changeLanguage('vi');
    // key exists in en/common.json only:
    expect(i18n.t('common:appName')).toBe('Minder');
  });
});
