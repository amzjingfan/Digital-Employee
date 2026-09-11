// @vitest-environment jsdom

import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ENTERPRISE_AUTH_STORAGE_KEY } from '@/auth';
import LanguageSwitcher from '@/components/LanguageSwitcher';

import { I18nProvider, resolveInitialLocale } from '@/i18n/index';

describe('locale preference resolution', () => {
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('resolves saved locale before browser language and defaults to English', () => {
    expect(resolveInitialLocale('zh-CN', ['en-US'])).toBe('zh-CN');
    expect(resolveInitialLocale(null, ['zh-HK', 'en-US'])).toBe('zh-CN');
    expect(resolveInitialLocale(null, ['fr-FR'])).toBe('en-US');
  });

  it('persists an authenticated language switch to the server preference API', async () => {
    window.localStorage.setItem(ENTERPRISE_AUTH_STORAGE_KEY, JSON.stringify({
      token: 'session-token',
      user: {
        id: 'user_member',
        tenant_id: 'tenant_demo',
        username: 'member',
        role: 'member',
      },
    }));
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(createElement(I18nProvider, null, createElement(LanguageSwitcher)));
    await user.click(screen.getByRole('button', { name: '切换语言' }));
    await user.click(await screen.findByText('English'));

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/preferences', expect.objectContaining({
      method: 'PUT',
      body: expect.stringContaining('"locale":"en"'),
    }));
    expect(window.localStorage.getItem('staffdeck_locale')).toBe('en-US');
  });
});
