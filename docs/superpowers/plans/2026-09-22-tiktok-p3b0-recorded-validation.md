# TikTok P3-B0 Approved Recorded-Data Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 P3-B0 数据验证工作台中增加经审批的脱敏 JSON 录制回放，使系统能以内存校验和追加写安全摘要证明数据集质量，同时保持 E3、授权和生产就绪门禁独立。

**Architecture:** 浏览器读取本地 JSON 并与审批元数据组成 JSON 请求；后端先按字节流限制 2 MiB，再执行敏感键、结构、审批和数据质量校验。现有追加写运行表扩展 `recorded` 模式，保存范围/契约快照与审批元数据，不保存原始数据；readiness 只接受最新且未失效的通过记录。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、SQLModel/SQLAlchemy、PostgreSQL 16 RLS、React 18、TypeScript 5、Vitest 4、pytest、Ruff。

**Spec:** `docs/superpowers/specs/2026-09-22-tiktok-p3b0-recorded-validation-design.md`

## Global Constraints

- 请求体硬上限 `2 * 1024 * 1024` 字节；六个集合各不超过 500 条，总计不超过 3,000 条。
- 只接受 `application/json`；文件名、原始 JSON、原始字段值和外部授权载荷不进入请求元数据、数据库、日志、响应、测试失败文本或截图。
- 录制审批人必须是同租户 active 用户且不同于执行人；时间顺序为 `period_start <= period_end <= replay_as_of <= approved_at <= now < valid_until`。
- recorded 运行只满足数据集验证部分，绝不创建或升级 capability evidence；E3 和有效资产授权继续独立判断。
- 最新 recorded 运行失败或 scope、contract、catalog、审批任一失效时，不回退使用更旧的成功运行。
- PostgreSQL 仍为权威数据库；新增 schema 只能通过显式迁移，保持 FORCE RLS、同租户外键和运行记录追加写。
- P3-B0 不添加 30 条硬门槛；P3-B1 的 30 条逐条对照保持后续独立退出条件。
- 所有新测试位于 `src/tests/`；不添加新运行时依赖。

## Review Focus

- 缺少 `Content-Length` 的 chunked 请求以及大小边界前后一字节：必须按实际读取字节判定 2 MiB，而不是信任头部；Task 2 固定测试。
- 嵌套、大小写和分隔符变体的敏感键，例如 `OAuth-State`、`access_token`：必须归一化后拒绝；Task 2 固定测试。
- 两条 recorded 运行拥有相同创建时间：必须用 `(created_at, id)` 稳定选择最新记录，失败记录不能被旧成功遮蔽；Task 3 固定测试。
- 解析完成后 scope revision 或字段契约发生变化：持久化事务必须重新读取并以当前状态计算摘要或返回冲突；Task 3 固定测试。
- 浏览器文件名、原始值或 JSON 解析片段进入请求、toast、响应或日志：必须只使用稳定错误码和本地文件状态；Task 4、Task 5 固定测试。

---

## File Structure

- `src/backend/migrations/20260922_tiktok_recorded_validation_v1.sql`: 扩展运行表、条件约束和同租户外键。
- `src/backend/migrations/20260922_tiktok_recorded_validation_v1.down.sql`: 在无 recorded 审计行时恢复旧 schema；存在 recorded 行时明确拒绝回滚。
- `src/backend/app/db/models.py`: 让 SQLModel 与新列和数据库约束一致。
- `src/backend/app/tiktok/recorded_validation.py`: 有限请求读取、敏感键扫描、严格 dataset 结构和契约摘要；不负责数据库提交。
- `src/backend/app/tiktok/schema.py`: recorded 请求、扩展运行响应和固定错误模型。
- `src/backend/app/tiktok/data_validation.py`: 泛化校验器、recorded 事务、最新运行选择和 readiness 集成。
- `src/backend/app/api/tiktok.py`: recorded HTTP 路由和稳定错误映射。
- `src/frontend-enterprise/src/pages/tiktok/dataValidationTypes.ts`: 工作台共享 TypeScript 合约。
- `src/frontend-enterprise/src/pages/tiktok/TikTokRecordedValidationForm.tsx`: 管理员录制表单、文件生命周期和安全请求。
- `src/frontend-enterprise/src/pages/tiktok/TikTokDataValidationPanel.tsx`: 装配表单、刷新工作区并展示 recorded 摘要。
- `src/tests/backend/test_postgres_tiktok_recorded_validation_migration.py`: 新迁移静态契约。
- `src/tests/backend/test_tiktok_recorded_validation.py`: 输入、服务、租户和 readiness 回归。
- `src/tests/backend/test_tiktok_data_validation_api.py`: recorded 路由、状态码和无泄漏回归。
- `src/tests/backend/test_postgres_acceptance.py`: 可选真实 PostgreSQL 条件约束/RLS/追加写验收。
- `src/tests/frontend/TikTokRecordedValidationForm.test.tsx`: 文件、审批、请求和清理行为。
- `src/tests/frontend/TikTokDataValidationPanel.test.tsx`: 父面板集成和成员只读。

### Task 1: Extend Append-Only Run Persistence

**Files:**
- Create: `src/backend/migrations/20260922_tiktok_recorded_validation_v1.sql`
- Create: `src/backend/migrations/20260922_tiktok_recorded_validation_v1.down.sql`
- Create: `src/tests/backend/test_postgres_tiktok_recorded_validation_migration.py`
- Modify: `src/backend/app/db/models.py:4732-4769`
- Modify: `src/tests/backend/test_postgres_acceptance.py:523-564`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**
- Consumes: 现有 `TikTokDataValidationRun`、`TikTokDataValidationScope` 的 `(tenant_id, id)` 唯一键和追加写触发器。
- Produces: `TikTokDataValidationRun` 的 nullable recorded 元数据列；`mode in {'mock', 'recorded'}`；数据库级条件约束和同租户外键。

- [ ] **Step 1: Append the task start record**

在开发日志追加目标、文件范围、数据库约束和“原始 dataset 不入库”的边界。

- [ ] **Step 2: Write failing migration and model tests**

创建迁移测试，固定新列、条件约束、同租户外键、RLS 及禁止原始数据列：

```python
def test_recorded_migration_adds_safe_metadata_and_conditional_constraints() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN approval_ref" in sql
    assert "ADD COLUMN approved_by_user_id" in sql
    assert "mode IN ('mock', 'recorded')" in sql
    assert "approved_by_user_id <> started_by_user_id" in sql
    assert "FOREIGN KEY (tenant_id, approved_by_user_id)" in sql
    assert "FOREIGN KEY (tenant_id, scope_id)" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "dataset_json" not in sql
    assert "file_name" not in sql


def test_recorded_down_migration_refuses_to_drop_existing_audit_rows() -> None:
    sql = DOWN_MIGRATION.read_text(encoding="utf-8")
    assert "WHERE mode = 'recorded'" in sql
    assert "RAISE EXCEPTION" in sql
    assert "DROP COLUMN approval_ref" in sql
```

扩展模型测试，断言 SQLModel 暴露 11 个 recorded 字段且默认 mock 行全部为 `None`。

- [ ] **Step 3: Run tests and verify the expected failure**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_postgres_tiktok_recorded_validation_migration.py `
  src\tests\backend\test_postgres_tiktok_data_validation_migration.py
```

Expected: FAIL because migration files and model columns do not exist.

- [ ] **Step 4: Implement migration and model**

Add nullable fields to `TikTokDataValidationRun`:

```python
source_label: str | None = None
approval_ref: str | None = None
approved_by_user_id: str | None = Field(default=None, index=True)
approved_at: datetime | None = None
approval_valid_until: datetime | None = None
data_period_start: datetime | None = None
data_period_end: datetime | None = None
replay_as_of: datetime | None = None
scope_id: str | None = Field(default=None, index=True)
scope_revision: int | None = None
contract_digest: str | None = Field(default=None, index=True)
attestation_version: str | None = None
```

Migration drops the old mode/real-ready constraints, adds two composite FKs, requires all recorded metadata for recorded rows and NULL for mock rows, validates separate approver/time order/fixed attestation, and only permits real-ready on passed recorded rows. Preserve the append-only trigger and FORCE RLS. Down migration raises if recorded rows exist before restoring the old schema.

Extend optional PostgreSQL acceptance to insert a valid recorded row and reject same-user approver, cross-tenant references, UPDATE and DELETE.

- [ ] **Step 5: Run persistence verification**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_postgres_tiktok_recorded_validation_migration.py `
  src\tests\backend\test_postgres_tiktok_data_validation_migration.py
& 'src\backend\.venv\Scripts\python.exe' -m ruff check `
  src\tests\backend\test_postgres_tiktok_recorded_validation_migration.py `
  src\tests\backend\test_postgres_acceptance.py
```

Expected: focused tests and Ruff pass. Run PostgreSQL acceptance only when its environment gate is configured.

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- docs/DEVELOPMENT_LOG.md src/backend/app/db/models.py `
  src/backend/migrations/20260922_tiktok_recorded_validation_v1.sql `
  src/backend/migrations/20260922_tiktok_recorded_validation_v1.down.sql `
  src/tests/backend/test_postgres_tiktok_recorded_validation_migration.py `
  src/tests/backend/test_postgres_acceptance.py
git commit -m "feat(tiktok): persist recorded validation evidence"
```

### Task 2: Enforce Bounded and Secret-Free Recorded Input

**Files:**
- Create: `src/backend/app/tiktok/recorded_validation.py`
- Create: `src/tests/backend/test_tiktok_recorded_validation.py`
- Modify: `src/backend/app/tiktok/schema.py:310-455`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**
- Consumes: `FIELD_CATALOG`, `TikTokFieldContract`, FastAPI `Request` stream and Pydantic v2.
- Produces: `MAX_RECORDED_REQUEST_BYTES`, `TikTokRecordedValidationRequest`, `TikTokRecordedValidationInputError`, `read_recorded_validation_request`, `compute_contract_digest`, `normalize_recorded_dataset`.

- [ ] **Step 1: Append the task start record**

Record the 2 MiB limit, six-collection allowlist, sensitive-key rejection, pseudonymization limitation and no raw persistence/logging.

- [ ] **Step 2: Write failing request and stream tests**

```python
@pytest.mark.asyncio
async def test_stream_limit_uses_actual_bytes_without_content_length() -> None:
    accepted = await read_recorded_validation_request(
        _request_with_chunks(_valid_body_bytes(pad_to=MAX_RECORDED_REQUEST_BYTES))
    )
    assert accepted.sanitization_attested is True
    with pytest.raises(TikTokRecordedValidationInputError) as error:
        await read_recorded_validation_request(
            _request_with_chunks(_valid_body_bytes(pad_to=MAX_RECORDED_REQUEST_BYTES + 1))
        )
    assert (error.value.status_code, error.value.code) == (413, "recorded_payload_too_large")


@pytest.mark.parametrize("key", ["access_token", "Access-Token", "OAuth.State", "cookie"])
def test_sensitive_key_variants_are_rejected(key: str) -> None:
    body = _valid_payload_dict()
    body["dataset"]["orders"][0][key] = "forbidden-value"
    with pytest.raises(TikTokRecordedValidationInputError, match="sensitive_field_forbidden"):
        validate_recorded_payload(body)
```

Also cover 415 content type, malformed JSON without parser fragments, unknown collection/field, nested value, depth, 501 rows, total limit, string length, false attestation, naive datetimes and each time-order violation.

- [ ] **Step 3: Run tests and verify the expected failure**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_tiktok_recorded_validation.py -k 'stream or sensitive or schema or time'
```

Expected: import failure because the recorded module and request types do not exist.

- [ ] **Step 4: Implement strict models and finite parsing**

Define six record models with `ConfigDict(extra='forbid')`; values remain JSON scalars so value defects become audited quality failures. Define the six required arrays and bounded metadata request.

```python
MAX_RECORDED_REQUEST_BYTES = 2 * 1024 * 1024
ATTESTATION_VERSION = "p3-b0-recorded.v1"
COLLECTION_LIMIT = 500
TOTAL_RECORD_LIMIT = 3000

async def read_recorded_validation_request(request: Request) -> TikTokRecordedValidationRequest:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise TikTokRecordedValidationInputError("recorded_content_type_required", 415)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_RECORDED_REQUEST_BYTES:
            raise TikTokRecordedValidationInputError("recorded_payload_too_large", 413)
    try:
        raw = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TikTokRecordedValidationInputError("recorded_json_invalid", 422) from None
    return validate_recorded_payload(raw)
```

Scan normalized key names before Pydantic validation and reject nested objects below record scalar values. Exceptions contain only stable codes. Compute contract digest from sorted semantic contract fields and sorted sources using compact UTF-8 JSON.

- [ ] **Step 5: Run input tests and Ruff**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_tiktok_recorded_validation.py -k 'stream or sensitive or schema or time or digest'
& 'src\backend\.venv\Scripts\python.exe' -m ruff check `
  src/backend/app/tiktok/recorded_validation.py src/backend/app/tiktok/schema.py `
  src/tests/backend/test_tiktok_recorded_validation.py
```

Expected: selected tests and Ruff pass; serialized errors contain no synthetic forbidden value.

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- docs/DEVELOPMENT_LOG.md src/backend/app/tiktok/recorded_validation.py `
  src/backend/app/tiktok/schema.py src/tests/backend/test_tiktok_recorded_validation.py
git commit -m "feat(tiktok): validate recorded dataset intake"
```

### Task 3: Run Recorded Validation and Recompute Readiness

**Files:**
- Modify: `src/backend/app/tiktok/data_validation.py:365-645, 870-1281`
- Modify: `src/backend/app/tiktok/schema.py:310-350`
- Modify: `src/tests/backend/test_tiktok_data_validation.py`
- Modify: `src/tests/backend/test_tiktok_recorded_validation.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**
- Consumes: `TikTokRecordedValidationRequest`, `normalize_recorded_dataset`, `compute_contract_digest`, extended run model.
- Produces: `validate_data_validation_dataset`, compatibility wrapper `validate_mock_dataset`, `run_recorded_data_validation`, and readiness parameters `latest_mock_run`, `latest_recorded_run`, `current_contract_digest`.

- [ ] **Step 1: Append the task start record**

Record the transaction boundary, latest-run rule, replay clock, scope/contract invalidation and prohibition on evidence upgrades.

- [ ] **Step 2: Write failing service and readiness tests**

Bootstrap contracts, activate a scope, add a separate approver and submit a normalized dataset. Pin safe persistence and stable latest selection:

```python
def test_recorded_run_persists_only_safe_summary_and_uses_replay_clock() -> None:
    run = run_recorded_data_validation(db, admin, _recorded_request(), now=NOW)
    assert run.mode == "recorded"
    assert run.status == "passed"
    assert run.approved_by_user_id == approver.id
    serialized = run.model_dump_json()
    assert "synthetic-order-value" not in serialized
    assert "dataset" not in serialized


def test_latest_failed_run_overrides_older_success_with_stable_tie_break() -> None:
    _insert_recorded_run(id="run-a", status="passed", created_at=NOW)
    _insert_recorded_run(id="run-b", status="failed", created_at=NOW)
    workspace = get_data_validation_workspace(db, admin)
    codes = {item.code for item in workspace.readiness.blockers}
    assert "latest_recorded_validation_failed" in codes
```

Also test empty required collection, cross-tenant/inactive/self approver, stale scope revision, missing catalog, contract change after pass, catalog mismatch, expired approval, two tenants with identical pseudonymous keys and zero capability-evidence mutations. A race-oriented test changes scope revision before service execution and expects `scope_revision_conflict` with zero new runs.

- [ ] **Step 3: Run tests and verify the expected failure**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_tiktok_recorded_validation.py `
  src\tests\backend\test_tiktok_data_validation.py
```

Expected: FAIL because recorded service and new readiness parameters do not exist.

- [ ] **Step 4: Generalize validation and implement the transaction**

Rename the reusable validator body to `validate_data_validation_dataset`; retain `validate_mock_dataset` as a thin compatibility wrapper. Add `required_collection_empty` for each required active domain with no records.

`run_recorded_data_validation` performs one transaction:

1. `ensure_tenant_admin`.
2. Re-read active tenant scope and compare `scope_revision`.
3. Re-read all catalog contracts and require exactly `FIELD_CODES`.
4. Resolve active same-tenant approver and reject self approval.
5. Re-evaluate time ordering against server `now`.
6. Compute current contract digest.
7. Validate normalized data with `replay_as_of`.
8. Load current evidence, authorizations and latest Mock run.
9. Add one recorded row containing only summary and metadata.
10. Evaluate readiness with the new run, then commit.

Workspace reading selects latest Mock and recorded runs independently. Order recorded runs by `created_at DESC, id DESC`. Replace the boolean recorded flag with explicit qualification emitting:

- `recorded_or_real_validation_missing`
- `latest_recorded_validation_failed`
- `recorded_validation_scope_stale`
- `recorded_validation_contract_stale`
- `recorded_validation_approval_expired`
- `recorded_validation_catalog_stale`

- [ ] **Step 5: Run service regression and Ruff**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_tiktok_recorded_validation.py `
  src\tests\backend\test_tiktok_data_validation.py
& 'src\backend\.venv\Scripts\python.exe' -m ruff check `
  src/backend/app/tiktok/data_validation.py src/backend/app/tiktok/recorded_validation.py `
  src/backend/app/tiktok/schema.py src/tests/backend/test_tiktok_recorded_validation.py `
  src/tests/backend/test_tiktok_data_validation.py
```

Expected: tests and Ruff pass; existing Mock tests still prove Mock never yields real-ready.

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- docs/DEVELOPMENT_LOG.md src/backend/app/tiktok/data_validation.py `
  src/backend/app/tiktok/schema.py src/tests/backend/test_tiktok_data_validation.py `
  src/tests/backend/test_tiktok_recorded_validation.py
git commit -m "feat(tiktok): run approved recorded validation"
```

### Task 4: Expose the Recorded Validation API Safely

**Files:**
- Modify: `src/backend/app/api/tiktok.py:1-180`
- Modify: `src/tests/backend/test_tiktok_data_validation_api.py`
- Modify: `src/tests/backend/test_tiktok_live_write_release_gate.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**
- Consumes: `read_recorded_validation_request`, `run_recorded_data_validation` and their stable exceptions.
- Produces: `POST /api/enterprise/tiktok/data-validation/runs/recorded -> TikTokDataValidationRunRead`.

- [ ] **Step 1: Append the task start record**

Record the local-only write route, body streaming before parsing, status mapping and route-freeze audit update.

- [ ] **Step 2: Write failing route and leak tests**

Use an ASGI `Request` helper with chunked bytes and invoke the async route with `asyncio.run`. Cover admin pass, member 403 before persistence, 413, 415, malformed/sensitive 422, tenant 404, scope 409 and quality-failed 200.

```python
def test_recorded_route_never_returns_filename_or_source_values() -> None:
    response = asyncio.run(
        data_validation_recorded_run(
            request=_recorded_http_request(_body_with_marker("raw-sensitive-marker")),
            current_user=admin,
            db=db,
        )
    )
    serialized = response.model_dump_json()
    assert "raw-sensitive-marker" not in serialized
    assert "customer-export.json" not in serialized
```

Update frozen expectations by exactly one route and one audited Python file. Assert no external HTTP client call and no addition to external-write capability lists.

- [ ] **Step 3: Run tests and verify the expected failure**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_tiktok_data_validation_api.py `
  src\tests\backend\test_tiktok_live_write_release_gate.py
```

Expected: FAIL because route and freeze entries do not exist.

- [ ] **Step 4: Implement the async route and stable mapping**

```python
@router.post(
    "/data-validation/runs/recorded",
    response_model=TikTokDataValidationRunRead,
)
async def data_validation_recorded_run(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationRunRead:
    payload = await read_recorded_validation_request(request)
    try:
        return run_recorded_data_validation(db, current_user, payload)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        db.rollback()
        raise _data_validation_http_error(exc) from exc
```

Map input exceptions to their own 413/415/422 status with only `{code, message}`. Ensure FastAPI dependencies authenticate before body consumption. Roll back every service exception after parsing.

- [ ] **Step 5: Run API regression and Ruff**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q `
  src\tests\backend\test_tiktok_recorded_validation.py `
  src\tests\backend\test_tiktok_data_validation_api.py `
  src\tests\backend\test_tiktok_live_write_release_gate.py `
  src\tests\backend\test_tiktok_business_unit.py
& 'src\backend\.venv\Scripts\python.exe' -m ruff check `
  src/backend/app/api/tiktok.py src/backend/app/tiktok/recorded_validation.py `
  src/tests/backend/test_tiktok_data_validation_api.py `
  src/tests/backend/test_tiktok_live_write_release_gate.py
```

Expected: selected tests and Ruff pass; route/file freeze counts match the reviewed surface.

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- docs/DEVELOPMENT_LOG.md src/backend/app/api/tiktok.py `
  src/tests/backend/test_tiktok_data_validation_api.py `
  src/tests/backend/test_tiktok_live_write_release_gate.py
git commit -m "feat(tiktok): expose recorded validation API"
```

### Task 5: Add the Administrator Recorded-Replay UI

**Files:**
- Create: `src/frontend-enterprise/src/pages/tiktok/dataValidationTypes.ts`
- Create: `src/frontend-enterprise/src/pages/tiktok/TikTokRecordedValidationForm.tsx`
- Create: `src/tests/frontend/TikTokRecordedValidationForm.test.tsx`
- Modify: `src/frontend-enterprise/src/pages/tiktok/TikTokDataValidationPanel.tsx`
- Modify: `src/tests/frontend/TikTokDataValidationPanel.test.tsx`
- Modify: `src/frontend-enterprise/src/i18n/en.json`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**
- Consumes: workspace scope/owners, `api.post`, recorded endpoint and stable blocker codes.
- Produces: shared `ValidationRun`/`Workspace` types and `TikTokRecordedValidationForm({ currentUserId, scope, ownerOptions, onCompleted })`.

- [ ] **Step 1: Append the task start record**

Record client file lifetime, no browser storage/logging, member read-only behavior and separation of recorded success from E3 readiness.

- [ ] **Step 2: Write failing component and integration tests**

```tsx
it('submits dataset without filename and clears the file after completion', async () => {
  const file = new File([JSON.stringify(validDataset)], 'private-export-name.json', {
    type: 'application/json',
  });
  await user.upload(screen.getByLabelText('选择脱敏 JSON'), file);
  await fillApprovalForm(user);
  await user.click(screen.getByRole('checkbox', { name: '确认文件已脱敏并获准回放' }));
  await user.click(screen.getByRole('button', { name: '运行录制回放' }));

  expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/data-validation/runs/recorded',
    expect.objectContaining({ dataset: validDataset, sanitization_attested: true }),
  );
  expect(JSON.stringify(vi.mocked(api.post).mock.calls[0][1])).not.toContain(file.name);
  expect(screen.getByLabelText('选择脱敏 JSON')).toHaveValue('');
});
```

Also cover client rejection over 2 MiB, malformed JSON without echo, disabled submit until scope/file/approver/attestation exist, self-approver exclusion, UTC conversion, metadata retained but file cleared after API failure, and zero `console.log` calls. Panel tests assert members have no file input or submit button while both roles see safe run summaries and blocker codes.

- [ ] **Step 3: Run tests and verify the expected failure**

```powershell
npm --prefix src/frontend-enterprise test -- TikTokRecordedValidationForm.test.tsx TikTokDataValidationPanel.test.tsx
```

Expected: FAIL because component, shared types and recorded section do not exist.

- [ ] **Step 4: Implement shared types and the recorded form**

Move existing workbench type declarations to `dataValidationTypes.ts`; extend `ValidationRun` with `mode` and nullable safe approval fields.

The form must keep `File` only in state and parsed dataset only inside submit; check `file.size` before `file.text()`; parse without rendering exception detail; omit `file.name`; convert local datetimes to UTC; exclude current user from approvers; clear the input with a changing React `key` in `finally`; retain non-sensitive metadata; call `onCompleted` after a persisted passed or failed run.

Mount the component only for administrators. Rename the run section to “验证运行”, label mode as Mock/录制回放 and show only safe approval reference/expiry for recorded rows. Add English entries for all new Chinese literals.

- [ ] **Step 5: Run frontend gates**

```powershell
npm --prefix src/frontend-enterprise test -- TikTokRecordedValidationForm.test.tsx TikTokDataValidationPanel.test.tsx
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise run i18n:check
npm --prefix src/frontend-enterprise run config:check
```

Expected: component/integration tests, typecheck, i18n and configuration checks pass.

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- docs/DEVELOPMENT_LOG.md `
  src/frontend-enterprise/src/pages/tiktok/dataValidationTypes.ts `
  src/frontend-enterprise/src/pages/tiktok/TikTokRecordedValidationForm.tsx `
  src/frontend-enterprise/src/pages/tiktok/TikTokDataValidationPanel.tsx `
  src/frontend-enterprise/src/i18n/en.json `
  src/tests/frontend/TikTokRecordedValidationForm.test.tsx `
  src/tests/frontend/TikTokDataValidationPanel.test.tsx
git commit -m "feat(tiktok): add recorded validation workflow"
```

### Task 6: Verify the Full Increment and Record Acceptance

**Files:**
- Modify: `docs/PROJECT_MEMORY.md`
- Modify: `docs/SESSION_HANDOFF.md`
- Modify: `docs/README.md`
- Modify: `docs/DEVELOPMENT_LOG.md`
- Create: `docs/screenshots/tiktok-p3b0/recorded-admin-result.jpg`
- Create: `docs/screenshots/tiktok-p3b0/recorded-member-read-only.jpg`
- Modify only for defects: files from Tasks 1-5 and their tests

**Interfaces:**
- Consumes: all earlier tasks and approved spec.
- Produces: fresh repository gate evidence, administrator/member browser acceptance, safe screenshots and durable handoff.

- [ ] **Step 1: Append the verification start record**

Record the backend/frontend/browser matrix, optional PostgreSQL condition, screenshot safety and known full-backend baseline.

- [ ] **Step 2: Run the complete focused backend matrix**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q --basetemp .pytest-recorded-final `
  src\tests\backend\test_tiktok_recorded_validation.py `
  src\tests\backend\test_tiktok_data_validation.py `
  src\tests\backend\test_tiktok_data_validation_api.py `
  src\tests\backend\test_postgres_tiktok_recorded_validation_migration.py `
  src\tests\backend\test_postgres_tiktok_data_validation_migration.py `
  src\tests\backend\test_tiktok_business_unit.py `
  src\tests\backend\test_tiktok_connector_authorization.py `
  src\tests\backend\test_tiktok_live_write_release_gate.py `
  src\tests\backend\test_tiktok_m2m_verification.py `
  src\tests\backend\test_tiktok_mock_exception_matrix.py `
  src\tests\backend\test_tiktok_mock_replay_execution.py `
  src\tests\backend\test_tiktok_mock_replay_tasks.py `
  src\tests\backend\test_tiktok_mock_replay.py `
  src\tests\backend\test_tiktok_official_oauth.py `
  src\tests\backend\test_tiktok_production_bootstrap.py `
  src\tests\backend\test_tiktok_release_evidence.py `
  src\tests\backend\test_tiktok_release_gate.py `
  src\tests\backend\test_tiktok_shadow.py
& 'src\backend\.venv\Scripts\python.exe' src\tests\check_test_layout.py
```

Expected: all selected tests and layout guard pass. Keep optional PostgreSQL evidence separate when its environment gate is absent.

- [ ] **Step 3: Run Python static checks**

```powershell
& 'src\backend\.venv\Scripts\python.exe' -m ruff check `
  src/backend/app/api/tiktok.py src/backend/app/tiktok/data_validation.py `
  src/backend/app/tiktok/recorded_validation.py src/backend/app/tiktok/schema.py `
  src/tests/backend/test_tiktok_recorded_validation.py `
  src/tests/backend/test_tiktok_data_validation.py `
  src/tests/backend/test_tiktok_data_validation_api.py `
  src/tests/backend/test_postgres_tiktok_recorded_validation_migration.py `
  src/tests/backend/test_postgres_acceptance.py
& 'src\backend\.venv\Scripts\python.exe' -m ruff check --ignore UP045,FURB157 `
  src/backend/app/db/models.py
```

Expected: changed code passes while preserving the documented shared-model historical exception.

- [ ] **Step 4: Run complete frontend gates serially**

```powershell
npm --prefix src/frontend-enterprise test -- --maxWorkers=1 --no-file-parallelism
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise run i18n:check
npm --prefix src/frontend-enterprise run config:check
npm --prefix src/frontend-enterprise run build
```

Expected: all frontend gates pass in a context allowed to read protected ignored `.env.local` without printing it.

- [ ] **Step 5: Apply migration and perform browser acceptance**

Use the repository migration runner and an isolated port; do not print connection values or copy secrets into tracked files.

Administrator checks:

- submit a synthetic file whose browser-only filename contains a marker;
- complete separate-approver metadata and a successful recorded run;
- verify response/page contain no filename or source values;
- run a second dataset with one quality defect and confirm latest failure blocks readiness;
- refresh and verify both append-only summaries persist.

Member checks:

- recorded summaries and blockers remain visible;
- file input, attestation, approval editor and recorded button are absent.

Save and visually inspect only safe screenshots at the planned paths.

- [ ] **Step 6: Review the whole branch against standards and spec**

Review `git diff 5a34f63...HEAD` for repository structure, tenant/RLS boundaries, append-only evidence, no secrets, 2 MiB actual-byte limit, strict schema, independent approver, replay clock, stale invalidation, latest-run rule, E3 separation and member read-only. Fix each Critical or Important finding with a regression test and rerun affected gates.

- [ ] **Step 7: Update durable documentation**

Record the stable recorded-validation boundary in `PROJECT_MEMORY.md`; exact branch/HEAD, counts, browser evidence, cleanup and remaining E3 blockers in `SESSION_HANDOFF.md`; plan/spec/screenshots in `README.md`; commands, outcomes and risks in `DEVELOPMENT_LOG.md`. Do not describe synthetic recorded success as production authorization or P3-B1 completion.

- [ ] **Step 8: Run final repository checks and commit**

```powershell
git diff --check
git status --short
git add -- docs/PROJECT_MEMORY.md docs/SESSION_HANDOFF.md docs/README.md `
  docs/DEVELOPMENT_LOG.md docs/screenshots/tiktok-p3b0/recorded-admin-result.jpg `
  docs/screenshots/tiktok-p3b0/recorded-member-read-only.jpg
git commit -m "docs(tiktok): record recorded validation acceptance"
git status --short
```

Expected: commit succeeds and worktree is clean. If a screenshot is unsafe or unavailable, omit it and document the exact limitation.
