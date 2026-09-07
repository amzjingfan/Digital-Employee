import { EnterpriseRoute } from './enums/routes';

export type EnterpriseCapabilityAction = 'view' | 'create' | 'update' | 'delete';

export type EnterpriseCapabilityModule =
  | 'accounts'
  | 'agents'
  | 'authorization'
  | 'business_resources'
  | 'operations_reports'
  | 'work_tasks'
  | 'channels'
  | 'feedback'
  | 'general_skills'
  | 'identity_roles'
  | 'knowledge'
  | 'memories'
  | 'models'
  | 'runtime_settings'
  | 'scheduled_tasks'
  | 'skills'
  | 'teams'
  | 'tools'
  | 'tiktok';

export type EnterpriseAuthUser = {
  id: string;
  tenant_id: string;
  username: string;
  display_name?: string;
  role: 'admin' | 'member';
  business_role?: string;
  authorization_source?: 'local' | 'oidc_groups' | 'oidc_admin' | string;
  identity_groups?: string[];
  role_synced_at?: string;
  enterprise_permissions?: Partial<Record<EnterpriseCapabilityModule, EnterpriseCapabilityAction[]>>;
  avatar_url?: string;
  preferred_locale?: 'zh-CN' | 'en';
  preferred_timezone?: string;
  effective_locale?: 'zh-CN' | 'en';
  effective_timezone?: string;
};

export type EnterpriseAuthSession = {
  token?: string;
  auth_mode?: 'bearer' | 'cookie';
  user: EnterpriseAuthUser;
};

export const ENTERPRISE_AUTH_STORAGE_KEY = 'ultrarag_auth';

export function getEnterpriseAuthSession(): EnterpriseAuthSession | null {
  return readStoredSession(ENTERPRISE_AUTH_STORAGE_KEY);
}

export function setEnterpriseAuthSession(session: EnterpriseAuthSession): void {
  try {
    window.localStorage.setItem(ENTERPRISE_AUTH_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // 存储超限等异常(极端情况):降级为不带头像字段的最小会话再试一次
    try {
      const minimal: EnterpriseAuthSession = {
        ...session,
        user: { ...session.user, avatar_url: undefined },
      };
      window.localStorage.setItem(ENTERPRISE_AUTH_STORAGE_KEY, JSON.stringify(minimal));
    } catch {
      // 抛出真实原因,避免被登录流程误报为账号/密码错误
      throw new Error('浏览器存储空间不足，请清理站点数据后重试');
    }
  }
}

export function clearEnterpriseAuthSession(): void {
  window.localStorage.removeItem(ENTERPRISE_AUTH_STORAGE_KEY);
}

function readStoredSession(key: string): EnterpriseAuthSession | null {
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as EnterpriseAuthSession;
    if ((!parsed.token && parsed.auth_mode !== 'cookie') || !parsed.user?.id) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function hasEnterpriseAuthCredential(session?: EnterpriseAuthSession | null): boolean {
  return Boolean(session?.token || session?.auth_mode === 'cookie');
}

export function enterpriseAuthHeaders(
  session: EnterpriseAuthSession | null = getEnterpriseAuthSession(),
): Record<string, string> {
  return session?.token && session.auth_mode !== 'cookie'
    ? { Authorization: `Bearer ${session.token}` }
    : {};
}

export function isEnterpriseAdmin(user?: EnterpriseAuthUser | null): boolean {
  return user?.role === 'admin';
}

const ADMIN_ONLY_MODULES = new Set<EnterpriseCapabilityModule>([
  'accounts',
  'authorization',
  'identity_roles',
  'models',
  'runtime_settings',
]);

const ROUTE_MODULES: Array<[string, EnterpriseCapabilityModule]> = [
  [EnterpriseRoute.IdentityRoles, 'identity_roles'],
  [EnterpriseRoute.Authorization, 'authorization'],
  [EnterpriseRoute.RuntimeSettings, 'runtime_settings'],
  [EnterpriseRoute.ScheduledTasks, 'scheduled_tasks'],
  [EnterpriseRoute.BusinessResources, 'business_resources'],
  [EnterpriseRoute.OperationsReports, 'operations_reports'],
  [EnterpriseRoute.WorkTasks, 'work_tasks'],
  [EnterpriseRoute.CrossborderOperations, 'work_tasks'],
  [EnterpriseRoute.ProductLifecycle, 'work_tasks'],
  [EnterpriseRoute.AdvertisingGovernance, 'work_tasks'],
  [EnterpriseRoute.GeneralSkills, 'general_skills'],
  [EnterpriseRoute.Knowledge, 'knowledge'],
  [EnterpriseRoute.Channels, 'channels'],
  [EnterpriseRoute.Accounts, 'accounts'],
  [EnterpriseRoute.Models, 'models'],
  [EnterpriseRoute.Agents, 'agents'],
  [EnterpriseRoute.Teams, 'teams'],
  [EnterpriseRoute.Memories, 'memories'],
  [EnterpriseRoute.Feedback, 'feedback'],
  [EnterpriseRoute.Skills, 'skills'],
  [EnterpriseRoute.Tools, 'tools'],
  [EnterpriseRoute.Dashboard, 'agents'],
  [EnterpriseRoute.Platform, 'agents'],
  [EnterpriseRoute.TikTokBusinessUnit, 'tiktok'],
];

export function canUseEnterpriseCapability(
  user: EnterpriseAuthUser | null | undefined,
  module: EnterpriseCapabilityModule,
  action: EnterpriseCapabilityAction = 'view',
): boolean {
  if (!user) return false;
  if (isEnterpriseAdmin(user)) return true;
  const manifest = user.enterprise_permissions;
  if (manifest && Object.keys(manifest).length > 0) {
    return manifest[module]?.includes(action) === true;
  }
  // Compatibility for sessions created before capability manifests existed.
  // The refreshed /api/auth/me response replaces this fallback before rendering.
  return action === 'view' && !ADMIN_ONLY_MODULES.has(module);
}

export function enterpriseRouteRequirement(
  path: string,
): { module: EnterpriseCapabilityModule; action: EnterpriseCapabilityAction } | null {
  if (path === '/enterprise') return { module: 'agents', action: 'view' };
  if (path === `${EnterpriseRoute.Knowledge}/new`) return { module: 'knowledge', action: 'create' };
  if (path === `${EnterpriseRoute.GeneralSkills}/new`) return { module: 'general_skills', action: 'create' };
  if (path.startsWith(`${EnterpriseRoute.GeneralSkills}/`) && path.endsWith('/edit')) {
    return { module: 'general_skills', action: 'update' };
  }
  if (path === `${EnterpriseRoute.Tools}/new` || path === `${EnterpriseRoute.Tools}/mcp/new`) {
    return { module: 'tools', action: 'create' };
  }
  if (path.startsWith(`${EnterpriseRoute.Tools}/`) && path.endsWith('/edit')) {
    return { module: 'tools', action: 'update' };
  }
  if (path.startsWith(`${EnterpriseRoute.Tools}/`) && path.endsWith('/test')) {
    return { module: 'tools', action: 'create' };
  }
  if (path === `${EnterpriseRoute.ScheduledTasks}/new`) {
    return { module: 'scheduled_tasks', action: 'create' };
  }
  if (path.startsWith(`${EnterpriseRoute.ScheduledTasks}/`) && path.endsWith('/edit')) {
    return { module: 'scheduled_tasks', action: 'update' };
  }
  const match = ROUTE_MODULES.find(([route]) => path === route || path.startsWith(`${route}/`));
  return match ? { module: match[1], action: 'view' } : null;
}

export function canAccessEnterpriseRoute(
  user: EnterpriseAuthUser | null | undefined,
  path: string,
): boolean {
  const requirement = enterpriseRouteRequirement(path);
  return !requirement || canUseEnterpriseCapability(user, requirement.module, requirement.action);
}

export function isGalleryEmployee(agent?: { metadata?: Record<string, unknown> } | null): boolean {
  return agent?.metadata?.published_to_gallery === true;
}

export function isEmployeeOwnedBy(
  agent: { metadata?: Record<string, unknown> },
  user?: EnterpriseAuthUser | null,
): boolean {
  if (!user) return false;
  const metadata = agent.metadata || {};
  const ownerUserId = metadata.owner_user_id;
  return ownerUserId === user.id;
}
