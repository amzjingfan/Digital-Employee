export type FieldSource = {
  source_key: string;
  source_type: string;
  object_name: string;
  field_path: string;
  priority: number;
  usage: 'mock' | 'real';
  decision: 'use' | 'defer' | 'reject';
  authorization_state: 'not_required' | 'unverified' | 'authorized' | 'denied';
};

export type ValidationScope = {
  id: string;
  store_resource_id: string | null;
  creator_scope_summary: string;
  business_owner_user_id: string | null;
  data_owner_user_id: string | null;
  status: 'draft' | 'active' | 'closed';
  revision: number;
};

export type FieldContract = {
  id: string;
  tenant_id: string;
  field_code: string;
  domain: string;
  label: string;
  data_type: string;
  required: boolean;
  owner_user_id: string | null;
  business_key: string;
  freshness_sla_seconds: number | null;
  missing_behavior: 'unknown' | 'manual_review' | 'block_stage' | 'not_applicable';
  sources: FieldSource[];
  status: 'draft' | 'confirmed' | 'blocked' | 'not_applicable';
  revision: number;
};

export type CapabilityEvidence = {
  id: string;
  tenant_id: string;
  entry_code: string;
  entry_kind: 'capability' | 'provider_decision';
  platform_domain: string;
  action: string;
  direction: string;
  subject_key: string;
  resource_id: string | null;
  required_scope: string;
  endpoint_or_artifact: string;
  api_version: string;
  evidence_level: 'E0' | 'E1' | 'E2' | 'E3';
  evidence_type: 'unverified' | 'official_docs' | 'contract' | 'mock' | 'sandbox' | 'approved_export' | 'real_account';
  status: 'unverified' | 'verified' | 'blocked' | 'not_applicable';
  decision: 'use' | 'defer' | 'reject' | null;
  summary: string;
  evidence_ref: string;
  checked_by_user_id: string | null;
  checked_at: string | null;
  valid_until: string | null;
  revision: number;
};

export type ValidationRun = {
  id: string;
  tenant_id: string;
  mode: 'mock' | 'recorded';
  catalog_version: string;
  dataset_digest: string;
  record_count: number;
  status: 'passed' | 'failed';
  workbench_ready_snapshot: boolean;
  real_data_ready_snapshot: boolean;
  checks: { code: string; passed: boolean; checked_count: number }[];
  issues: { code: string; field_code: string; severity: string; detail: string }[];
  started_by_user_id: string;
  source_label?: string | null;
  approval_ref?: string | null;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  approval_valid_until?: string | null;
  data_period_start?: string | null;
  data_period_end?: string | null;
  replay_as_of?: string | null;
  scope_id?: string | null;
  scope_revision?: number | null;
  contract_digest?: string | null;
  attestation_version?: string | null;
  created_at: string;
};

export type ValidationOption = { id: string; label: string };

export type Workspace = {
  tenant_id: string;
  catalog_version: string;
  scope: ValidationScope | null;
  readiness: {
    workbench_ready: boolean;
    real_data_ready: boolean;
    blockers: { code: string; target_type: string; target_code: string; detail: string }[];
  };
  field_contracts: FieldContract[];
  capability_evidence: CapabilityEvidence[];
  recent_runs: ValidationRun[];
  store_options: ValidationOption[];
  owner_options: ValidationOption[];
};
