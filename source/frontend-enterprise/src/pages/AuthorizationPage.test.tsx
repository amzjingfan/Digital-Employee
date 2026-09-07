// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import AuthorizationPage from './AuthorizationPage';

vi.mock('../api/client', () => ({
  TENANT_ID: 'tenant_demo',
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

describe('AuthorizationPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockImplementation(async (path) => (
      path.includes('authorization-policies')
        ? []
        : [
            {
              id: 'authz_1',
              subject_id: 'user_demo',
              role: 'tenant_member',
              object: '/api/enterprise/agents/not-a-real-agent',
              action: 'DELETE',
              effect: 'deny',
              reason: 'no_matching_allow_policy',
              policy_version: 'abc123',
              request_id: 'req_test_denied',
              occurred_at: '2026-08-30T08:30:00',
            },
          ]
    ) as never);
  });

  it('renders authorization evidence for administrators', async () => {
    render(<AuthorizationPage />);

    expect(await screen.findByText('req_test_denied')).toBeTruthy();
    expect(screen.getByText('DELETE')).toBeTruthy();
    expect(screen.getAllByText('拒绝').length).toBeGreaterThan(0);
  });
});
