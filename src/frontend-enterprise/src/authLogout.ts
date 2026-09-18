import {
  clearEnterpriseAuthSession,
  type EnterpriseAuthSession,
} from './auth';

const LOCAL_LOGIN_PATH = '/login';

export type LogoutNavigation = (url: string) => void;

function safeLogoutTarget(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return LOCAL_LOGIN_PATH;
  const candidate = value.trim();
  if (candidate.startsWith('/') && !candidate.startsWith('//')) return candidate;

  try {
    const target = new URL(candidate, window.location.origin);
    if (target.protocol === 'https:') return target.toString();
    if (
      target.protocol === 'http:'
      && (target.hostname === 'localhost' || target.hostname === '127.0.0.1')
    ) {
      return target.toString();
    }
  } catch {
    return LOCAL_LOGIN_PATH;
  }
  return LOCAL_LOGIN_PATH;
}

export async function logoutEnterpriseSession(
  session: EnterpriseAuthSession | null,
  navigate: LogoutNavigation = (url) => window.location.assign(url),
): Promise<void> {
  const oidcSession = session?.auth_mode === 'cookie';
  const endpoint = oidcSession ? '/api/auth/oidc/logout' : '/api/auth/logout';
  const headers: Record<string, string> = session?.token && !oidcSession
    ? { Authorization: `Bearer ${session.token}` }
    : {};
  let redirectUrl = LOCAL_LOGIN_PATH;

  clearEnterpriseAuthSession();
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      credentials: 'include',
      headers,
    });
    if (response.ok && oidcSession) {
      const payload = await response.json() as { redirect_url?: unknown };
      redirectUrl = safeLogoutTarget(payload.redirect_url);
    }
  } catch {
    redirectUrl = LOCAL_LOGIN_PATH;
  }

  navigate(redirectUrl);
}
