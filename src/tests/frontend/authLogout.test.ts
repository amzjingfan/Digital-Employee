// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ENTERPRISE_AUTH_STORAGE_KEY,
  setEnterpriseAuthSession,
  type EnterpriseAuthSession,
} from '@/auth';
import { logoutEnterpriseSession } from '@/authLogout';

const user = {
  id: 'user-1',
  tenant_id: 'tenant_demo',
  username: 'operator',
  role: 'member' as const,
};

function cookieSession(): EnterpriseAuthSession {
  return { auth_mode: 'cookie', user };
}

function bearerSession(): EnterpriseAuthSession {
  return { auth_mode: 'bearer', token: 'local-token', user };
}

function response(options: { ok?: boolean; body?: unknown } = {}): Response {
  return {
    ok: options.ok ?? true,
    json: async () => options.body ?? {},
  } as Response;
}

describe('logoutEnterpriseSession', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('prepares OIDC logout, clears local state, and navigates to Casdoor', async () => {
    const session = cookieSession();
    setEnterpriseAuthSession(session);
    const fetchMock = vi.fn().mockResolvedValue(response({
      body: {
        redirect_url: 'https://identity.example.com/api/logout?client_id=joukir',
      },
    }));
    const navigate = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await logoutEnterpriseSession(session, navigate);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/oidc/logout',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
    expect(window.localStorage.getItem(ENTERPRISE_AUTH_STORAGE_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith(
      'https://identity.example.com/api/logout?client_id=joukir',
    );
  });

  it('logs out a bearer session locally without calling Casdoor', async () => {
    const session = bearerSession();
    setEnterpriseAuthSession(session);
    const fetchMock = vi.fn().mockResolvedValue(response());
    const navigate = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await logoutEnterpriseSession(session, navigate);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: 'Bearer local-token' },
      }),
    );
    expect(window.localStorage.getItem(ENTERPRISE_AUTH_STORAGE_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login');
  });

  it.each([
    ['network rejection', () => Promise.reject(new TypeError('network unavailable'))],
    ['non-success response', () => Promise.resolve(response({ ok: false }))],
  ])('clears local state and returns to login after %s', async (_name, request) => {
    const session = cookieSession();
    setEnterpriseAuthSession(session);
    const navigate = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockImplementation(request));

    await logoutEnterpriseSession(session, navigate);

    expect(window.localStorage.getItem(ENTERPRISE_AUTH_STORAGE_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login');
  });

  it('rejects a dangerous provider redirect', async () => {
    const session = cookieSession();
    setEnterpriseAuthSession(session);
    const navigate = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      body: { redirect_url: 'javascript:alert(document.domain)' },
    })));

    await logoutEnterpriseSession(session, navigate);

    expect(navigate).toHaveBeenCalledWith('/login');
  });

  it('allows a loopback HTTP Casdoor redirect for development', async () => {
    const session = cookieSession();
    const navigate = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      body: { redirect_url: 'http://localhost:18000/api/logout?client_id=joukir' },
    })));

    await logoutEnterpriseSession(session, navigate);

    expect(navigate).toHaveBeenCalledWith(
      'http://localhost:18000/api/logout?client_id=joukir',
    );
  });
});
