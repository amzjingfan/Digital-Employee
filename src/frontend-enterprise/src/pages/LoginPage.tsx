import { useEffect, useState, type KeyboardEvent } from 'react';

import { api, TENANT_ID } from '../api/client';
import { setEnterpriseAuthSession, type EnterpriseAuthSession } from '../auth';
import { useI18n } from '../i18n';
import AppHeader from '../components/AppHeader';
import BrandLogo from '../components/BrandLogo';
import IconFieldClear from '../assets/icons/field-clear.svg?react';
import IconFieldEye from '../assets/icons/field-eye.svg?react';
import IconFieldEyeOn from '../assets/icons/field-eye-on.svg?react';
import loginPreview from '../assets/staffdeck/login-preview.png';

export type LoginPageProps = {
  onLogin: (session: EnterpriseAuthSession) => void;
};

/**
 * Signed-out landing / login page. Mirrors Figma node 68:201 (`Login_light`):
 * a full-bleed hero with the Joukir wordmark and a product-preview placeholder
 * anchored to the bottom. Clicking "登录" slides the credentials form (node 68:1563)
 * down into view in place of the call-to-action button.
 */
export default function LoginPage({ onLogin }: LoginPageProps) {
  const { locale, hydrateLocale } = useI18n();
  const initialQuery = new URLSearchParams(window.location.search);
  const invitationToken = initialQuery.get('invite_token') || '';
  const invitationTenantId = initialQuery.get('tenant_id') || TENANT_ID;
  const [oidcEnabled, setOidcEnabled] = useState(false);
  const [showForm, setShowForm] = useState(Boolean(invitationToken));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [usernameError, setUsernameError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void api.get<{ enabled: boolean }>('/api/auth/oidc/config')
      .then(({ enabled }) => {
        if (!cancelled) setOidcEnabled(enabled);
      })
      .catch(() => {
        if (!cancelled) setOidcEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (!oidcEnabled || query.get('oidc') !== 'success') return;
    let cancelled = false;
    setLoading(true);
    void api.get<EnterpriseAuthSession['user']>('/api/auth/me')
      .then((user) => {
        if (cancelled) return;
        const session: EnterpriseAuthSession = { auth_mode: 'cookie', user };
        setEnterpriseAuthSession(session);
        if (user.effective_locale) {
          hydrateLocale(user.effective_locale === 'en' ? 'en-US' : 'zh-CN');
        }
        query.delete('oidc');
        const suffix = query.toString();
        window.history.replaceState({}, '', `${window.location.pathname}${suffix ? `?${suffix}` : ''}`);
        onLogin(session);
      })
      .catch(() => {
        if (!cancelled) setUsernameError('企业登录会话无效，请重试');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hydrateLocale, oidcEnabled, onLogin]);

  function startOIDCLogin() {
    const current = `${window.location.pathname}${window.location.search}`;
    const returnTo = current === '/login' || current === '/' ? '/workspace/gallery' : current;
    const oidcLocale = locale === 'en-US' ? 'en' : 'zh-CN';
    window.location.assign(
      `/api/auth/oidc/login?return_to=${encodeURIComponent(returnTo)}&locale=${encodeURIComponent(oidcLocale)}`,
    );
  }

  async function login() {
    const trimmedUsername = username.trim();
    const trimmedPassword = password.trim();
    setUsernameError(invitationToken || trimmedUsername ? '' : '请输入账号');
    setPasswordError(trimmedPassword ? '' : '请输入密码');
    if ((!invitationToken && !trimmedUsername) || !trimmedPassword) return;

    setLoading(true);
    try {
      const session = invitationToken
        ? await api.post<EnterpriseAuthSession>('/api/auth/invitations/accept', {
            tenant_id: invitationTenantId,
            token: invitationToken,
            password: trimmedPassword,
          })
        : await api.post<EnterpriseAuthSession>('/api/auth/login', {
            tenant_id: TENANT_ID,
            username: trimmedUsername,
            password: trimmedPassword,
          });
      setEnterpriseAuthSession(session);
      if (session.user.effective_locale) {
        hydrateLocale(session.user.effective_locale === 'en' ? 'en-US' : 'zh-CN');
      }
      onLogin(session);
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '登录失败';
      setUsernameError('账号输入错误');
      setPasswordError(messageText || '密码输入错误');
    } finally {
      setLoading(false);
    }
  }

  function onFieldKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') void login();
  }

  const inputBaseClass =
    'flex h-[44px] w-full items-center gap-[8px] rounded-[10px] border bg-white px-[16px] transition-colors';

  return (
    <div className="relative flex min-h-screen flex-col bg-white">
      <AppHeader
        className="h-[60px] shrink-0 px-[32px]"
        left={<BrandLogo markSize={28} />}
        right={null}
      />

      <main className="flex flex-1 flex-col items-center px-[32px]">
        <div className="flex flex-col items-center pt-[60px]">
          <span className="flex items-center justify-center rounded-[10px] border-[0.5px] border-[#e3e7f1] bg-[#f6f6f6] px-[20px] py-[6px] text-[14px] text-[#464c5e]">
            {invitationToken ? '接受企业账号邀请' : '我们来做什么？'}
          </span>
          <h1 className="mt-[6px] text-center text-[54px] font-semibold leading-[80px] tracking-[1.08px] text-[#18181a]">
            九骥 Joukir
            <br />
            数字员工运营平台
          </h1>

          {!showForm ? (
            <div className="mt-[24px] flex flex-col items-center gap-[12px]">
              {oidcEnabled ? (
                <button
                  type="button"
                  onClick={startOIDCLogin}
                  className="flex items-center justify-center rounded-[10px] bg-[#18181a] px-[36px] py-[10px] text-[16px] font-normal text-white transition-colors hover:bg-[#18181a]/90"
                >
                  企业 SSO 登录
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => setShowForm(true)}
                className={`${oidcEnabled ? 'text-[#464c5e] underline-offset-4 hover:underline' : 'rounded-[10px] bg-[#18181a] px-[36px] py-[10px] text-white hover:bg-[#18181a]/90'} flex items-center justify-center text-[16px] font-normal transition-colors`}
              >
                登录
              </button>
            </div>
          ) : (
            <form
              className="mt-[24px] flex w-[320px] flex-col duration-300 ease-out animate-in fade-in slide-in-from-top-4"
              onSubmit={(event) => {
                event.preventDefault();
                void login();
              }}
            >
              {!invitationToken && (
                <div
                  className={`${inputBaseClass} ${usernameError ? 'border-[#f54a45]' : username ? 'border-[#18181a]' : 'border-[#e3e7f1]'}`}
                >
                  <input
                    value={username}
                    autoComplete="username"
                    placeholder="请输入账号（首次使用请输入admin）"
                    aria-label="账号"
                    onChange={(event) => {
                      setUsername(event.target.value);
                      if (usernameError) setUsernameError('');
                    }}
                    onKeyDown={onFieldKeyDown}
                    className="min-w-0 flex-1 border-0 bg-transparent text-[14px] text-[#18181a] outline-none placeholder:text-[#757f9c]"
                  />
                  {username && (
                    <button
                      type="button"
                      aria-label="清空账号"
                      onClick={() => {
                        setUsername('');
                        setUsernameError('');
                      }}
                      className="grid size-[18px] shrink-0 place-items-center text-[#667085] outline-none transition-colors hover:text-[#464c5e]"
                    >
                      <IconFieldClear className="size-[18px]" />
                    </button>
                  )}
                </div>
              )}

              <div
                className={`${invitationToken ? '' : 'mt-[24px]'} ${inputBaseClass} ${passwordError ? 'border-[#f54a45]' : password ? 'border-[#18181a]' : 'border-[#e3e7f1]'}`}
              >
                <input
                  value={password}
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="请输入密码（首次使用请输入admin）"
                  aria-label="密码"
                  onChange={(event) => {
                    setPassword(event.target.value);
                    if (passwordError) setPasswordError('');
                  }}
                  onKeyDown={onFieldKeyDown}
                  className="min-w-0 flex-1 border-0 bg-transparent text-[14px] text-[#18181a] outline-none placeholder:text-[#757f9c]"
                />
                <button
                  type="button"
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="grid size-[18px] shrink-0 place-items-center text-[#677185] outline-none transition-colors hover:text-[#464c5e]"
                >
                  {showPassword ? (
                    <IconFieldEyeOn className="size-[18px]" />
                  ) : (
                    <IconFieldEye className="size-[18px]" />
                  )}
                </button>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-[24px] flex h-[40px] w-[120px] items-center justify-center self-center rounded-[10px] bg-[#18181a] text-[16px] font-normal text-white transition-colors hover:bg-[#18181a]/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? (invitationToken ? '激活中…' : '登录中…') : (invitationToken ? '激活并登录' : '登录')}
              </button>
            </form>
          )}
        </div>

        <div className="relative mt-[32px] w-full max-w-[1200px]">
          <img
            src={loginPreview}
            alt="九骥 Joukir 产品预览"
            className="h-auto w-full max-w-[1200px] select-none object-contain"
            draggable={false}
          />
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 size-full"
            viewBox="0 0 2400 1492"
            preserveAspectRatio="xMinYMin meet"
          >
            <rect x="132" y="63" width="238" height="65" fill="white" />
            <text x="139" y="110" fill="#18181a" fontSize="35" fontWeight="700">
              九骥 Joukir
            </text>
          </svg>
        </div>
      </main>
    </div>
  );
}
