import { describe, expect, it } from 'vitest';

import {
  canAccessEnterpriseRoute,
  canUseEnterpriseCapability,
  enterpriseRouteRequirement,
  type EnterpriseAuthUser,
} from '@/auth';

function businessUser(
  businessRole: string,
  permissions: EnterpriseAuthUser['enterprise_permissions'],
): EnterpriseAuthUser {
  return {
    id: `user-${businessRole}`,
    tenant_id: 'tenant_demo',
    username: businessRole,
    role: 'member',
    business_role: businessRole,
    enterprise_permissions: permissions,
  };
}

describe('enterprise capability routing', () => {
  it('keeps the operations supervisor read-only in knowledge and writable in schedules', () => {
    const supervisor = businessUser('operations_supervisor', {
      knowledge: ['view'],
      scheduled_tasks: ['view', 'create', 'update', 'delete'],
    });

    expect(canAccessEnterpriseRoute(supervisor, '/enterprise/knowledge')).toBe(true);
    expect(canAccessEnterpriseRoute(supervisor, '/enterprise/knowledge/new')).toBe(false);
    expect(canAccessEnterpriseRoute(supervisor, '/enterprise/scheduled-tasks/new')).toBe(true);
    expect(canAccessEnterpriseRoute(supervisor, '/enterprise/scheduled-tasks/task-1/edit')).toBe(true);
  });

  it('allows listing compliance to curate knowledge without granting tool writes', () => {
    const listing = businessUser('listing_compliance_specialist', {
      knowledge: ['view', 'create', 'update'],
      tools: ['view'],
    });

    expect(canAccessEnterpriseRoute(listing, '/enterprise/knowledge/new')).toBe(true);
    expect(canAccessEnterpriseRoute(listing, '/enterprise/tools/tool-1/edit')).toBe(false);
    expect(canUseEnterpriseCapability(listing, 'tools', 'view')).toBe(true);
  });

  it('maps mutating child routes before their read-only parent route', () => {
    expect(enterpriseRouteRequirement('/enterprise/tools/mcp/new')).toEqual({
      module: 'tools',
      action: 'create',
    });
    expect(enterpriseRouteRequirement('/enterprise/general-skills/demo/edit')).toEqual({
      module: 'general_skills',
      action: 'update',
    });
  });
});
