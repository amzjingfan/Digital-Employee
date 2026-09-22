# TikTok P3-B0 Data Validation Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 TikTok 事业部中交付租户隔离、可持久化、可重复运行的 P3-B0 数据验证工作台，覆盖 US 试点范围、字段契约、动作级 E0-E3 证据、供应商决定和确定性 Mock 校验。

**Architecture:** 在模块化单体内增加四张 TikTok 租户表和一个独立 `app.tiktok.data_validation` 服务模块。FastAPI 路由只负责认证、映射和错误转换；React 页面把工作台拆成独立面板，由管理员编辑和运行、成员只读。所有就绪状态按当前记录实时派生，Mock 运行只保存摘要，永远不能把真实数据状态提升为就绪。

**Tech Stack:** Python 3.11、FastAPI、SQLModel/SQLAlchemy、PostgreSQL FORCE RLS、Pydantic v2、pytest、React 18、TypeScript strict、Vitest、Testing Library、Tailwind CSS。

**Spec:** [`docs/superpowers/specs/2026-09-22-tiktok-p3b0-data-validation-workbench-design.md`](../specs/2026-09-22-tiktok-p3b0-data-validation-workbench-design.md)

## Global Constraints

- 每个任务开始前和完成后都向 `docs/DEVELOPMENT_LOG.md` 追加目标、范围、命令结果、风险和下一步；不得改写既有记录。
- 只在隔离分支 `codex/tiktok-p3b0-validation` 工作，保留主工作区未提交改动不动；每个任务单独提交。
- 四张业务表都含 `tenant_id`，PostgreSQL 必须 `ENABLE ROW LEVEL SECURITY` 和 `FORCE ROW LEVEL SECURITY`，唯一约束和对象关联包含租户边界。
- 不保存或输出 Token、Cookie、客户端密钥、凭据引用、原始 OAuth 载荷、原始第三方响应、达人地址或明文联系方式。
- 目录 bootstrap 只补缺失项，不覆盖租户编辑，不把任何真实来源自动标记为已授权，不把任何能力自动提升到 E1-E3。
- 所有写操作和 Mock 运行仅允许 `role='admin'`；同租户成员只读。跨租户资源、用户或证据引用返回 404。
- `workbench_ready` 和 `real_data_ready` 分开计算；首版没有真实/脱敏录制回放入口，因此后者始终包含 `recorded_or_real_validation_missing` 阻塞项。
- 不发起外部网络调用，不增加外部依赖，不实现 P3-B1 业务事实表、看板聚合或任何 TikTok 外部写入。
- 所有可执行测试放在 `src/tests/`；每项行为先见失败测试，再写最小实现，再运行通过测试。
- 前端沿用现有两空格、单引号和分号风格；后端保持类型提示、四空格、100 字符 Ruff 行宽。

## Review Focus

- 同一字段的 `sources_json` 出现重复 `source_key`、同用途重复优先级或 `denied + use` 时应返回 422；Task 3 的 schema/service 测试固定该行为。
- 两个管理员基于同一 revision 编辑时，后提交者应收到 409 且不能覆盖先提交结果；Task 3 和 Task 5 覆盖并发冲突。
- E3 已过期，或市场、主体、scope、资产任一不匹配时，`real_data_ready` 必须保持 false；Task 3 覆盖这些组合。
- 两个租户使用相同字段代码、店铺代码、外部业务键和能力代码时，不得互相读取或更新；Task 2、Task 3 和 Task 5 分层覆盖。
- 同一目录版本重复运行 Mock 时摘要和检查结果必须稳定，运行行追加写且不含 fixture 原值；Task 4 覆盖确定性与数据泄露边界。

---

## Task 1: Add tenant-scoped persistence and PostgreSQL RLS

**Files:**

- Modify: `src/backend/app/db/models.py`
- Create: `src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.sql`
- Create: `src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.down.sql`
- Create: `src/tests/backend/test_postgres_tiktok_data_validation_migration.py`
- Modify: `src/tests/backend/test_postgres_acceptance.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**

- Produces: `TikTokDataValidationScope`, `TikTokFieldContract`, `TikTokCapabilityEvidence`, and `TikTokDataValidationRun` SQLModel classes.
- Produces table names consumed by Tasks 2-5: `tiktok_data_validation_scopes`, `tiktok_field_contracts`, `tiktok_capability_evidence`, `tiktok_data_validation_runs`.
- No Task 1 function performs business logic or external calls.

- [ ] **Step 1: Record Task 1 start**

Append the four table names, migration files, RLS requirement, and the rule that no fixture or external payload will be stored.

- [ ] **Step 2: Write failing model and migration tests**

Create `src/tests/backend/test_postgres_tiktok_data_validation_migration.py`:

```python
from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import (
    Tenant,
    TikTokCapabilityEvidence,
    TikTokDataValidationRun,
    TikTokDataValidationScope,
    TikTokFieldContract,
)


ROOT = Path(__file__).resolve().parents[3]
UP = ROOT / "src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.sql"
DOWN = ROOT / "src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.down.sql"
TABLES = (
    "tiktok_data_validation_scopes",
    "tiktok_field_contracts",
    "tiktok_capability_evidence",
    "tiktok_data_validation_runs",
)


def test_sqlmodel_tables_are_tenant_scoped() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Tenant(id="tenant_a", name="Tenant A"))
        db.add(
            TikTokFieldContract(
                tenant_id="tenant_a",
                field_code="order.order_id",
                domain="order",
                label="订单 ID",
                data_type="string",
                required=True,
                business_key="order_id",
                missing_behavior="block_stage",
                sources_json=[],
            )
        )
        db.commit()
        assert db.exec(
            select(TikTokFieldContract).where(TikTokFieldContract.tenant_id == "tenant_a")
        ).one().field_code == "order.order_id"


def test_postgres_migration_has_force_rls_composite_constraints_and_append_only_runs() -> None:
    migration = UP.read_text(encoding="utf-8")
    rollback = DOWN.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in migration
        assert f"DROP TABLE IF EXISTS public.{table}" in rollback
    assert migration.count("app.current_staffdeck_tenant_id()") >= 4
    assert "FOREIGN KEY (tenant_id, store_resource_id)" in migration
    assert "FOREIGN KEY (tenant_id, owner_user_id)" in migration
    assert "FOREIGN KEY (tenant_id, checked_by_user_id)" in migration
    assert "reject_tiktok_data_validation_run_mutation" in migration
    assert "BEFORE UPDATE OR DELETE ON public.tiktok_data_validation_runs" in migration
    assert "GRANT SELECT, INSERT ON public.tiktok_data_validation_runs TO staffdeck_runtime" in migration
```

Extend the opt-in PostgreSQL acceptance file with a runtime-role test:

```python
def test_tiktok_data_validation_tables_enforce_rls_and_append_only_runs() -> None:
    tables = (
        "tiktok_data_validation_scopes",
        "tiktok_field_contracts",
        "tiktok_capability_evidence",
        "tiktok_data_validation_runs",
    )
    with engine.connect() as unscoped:
        for table in tables:
            assert unscoped.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0

    suffix = uuid4().hex[:12]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant_demo', true)"))
            user_id = connection.execute(
                text("SELECT id FROM users ORDER BY created_at LIMIT 1")
            ).scalar_one()
            run_id = f"tiktok_dv_accept_{suffix}"
            connection.execute(
                text(
                    "INSERT INTO tiktok_data_validation_runs "
                    "(id, tenant_id, mode, catalog_version, dataset_digest, record_count, "
                    "status, workbench_ready_snapshot, real_data_ready_snapshot, checks_json, "
                    "issues_json, started_by_user_id, created_at) VALUES "
                    "(:id, 'tenant_demo', 'mock', 'p3-b0.v1', :digest, 1, 'passed', "
                    "false, false, '[]'::jsonb, '[]'::jsonb, :user_id, now())"
                ),
                {"id": run_id, "digest": f"sha256:{suffix}", "user_id": user_id},
            )
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                connection.execute(
                    text(
                        "UPDATE tiktok_data_validation_runs SET status='failed' WHERE id=:id"
                    ),
                    {"id": run_id},
                )
            savepoint.rollback()
        finally:
            transaction.rollback()
```

- [ ] **Step 3: Run the new test and observe failure**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_postgres_tiktok_data_validation_migration.py -q
```

Expected: collection fails because the four model classes and migration files do not exist.

- [ ] **Step 4: Add the four SQLModel classes**

Add these exact public class names and field contracts to `app/db/models.py`; implement the listed checks with `UniqueConstraint`, `CheckConstraint`, and `Index`:

```python
class TikTokDataValidationScope(SQLModel, table=True):
    __tablename__ = "tiktok_data_validation_scopes"
    id: str = Field(default_factory=lambda: new_id("tiktok_dv_scope"), primary_key=True)
    tenant_id: str = Field(index=True)
    market: str = Field(default="US", index=True)
    store_resource_id: Optional[str] = Field(default=None, index=True)
    creator_scope_summary: str = ""
    business_owner_user_id: Optional[str] = Field(default=None, index=True)
    data_owner_user_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="draft", index=True)
    revision: int = 1
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class TikTokFieldContract(SQLModel, table=True):
    __tablename__ = "tiktok_field_contracts"
    id: str = Field(default_factory=lambda: new_id("tiktok_field"), primary_key=True)
    tenant_id: str = Field(index=True)
    field_code: str = Field(index=True)
    domain: str = Field(index=True)
    label: str
    data_type: str
    required: bool = True
    owner_user_id: Optional[str] = Field(default=None, index=True)
    business_key: str = ""
    freshness_sla_seconds: Optional[int] = None
    missing_behavior: str = "unknown"
    sources_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="draft", index=True)
    revision: int = 1
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class TikTokCapabilityEvidence(SQLModel, table=True):
    __tablename__ = "tiktok_capability_evidence"
    id: str = Field(default_factory=lambda: new_id("tiktok_cap"), primary_key=True)
    tenant_id: str = Field(index=True)
    entry_code: str = Field(index=True)
    entry_kind: str = Field(index=True)
    platform_domain: str = Field(index=True)
    action: str
    direction: str
    subject_key: str = Field(default="global", index=True)
    resource_id: Optional[str] = Field(default=None, index=True)
    required_scope: str = ""
    endpoint_or_artifact: str = ""
    api_version: str = ""
    evidence_level: str = Field(default="E0", index=True)
    evidence_type: str = Field(default="unverified", index=True)
    status: str = Field(default="unverified", index=True)
    decision: Optional[str] = Field(default=None, index=True)
    summary: str = ""
    evidence_ref: str = ""
    checked_by_user_id: Optional[str] = Field(default=None, index=True)
    checked_at: Optional[datetime] = Field(default=None, index=True)
    valid_until: Optional[datetime] = Field(default=None, index=True)
    revision: int = 1
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class TikTokDataValidationRun(SQLModel, table=True):
    __tablename__ = "tiktok_data_validation_runs"
    id: str = Field(default_factory=lambda: new_id("tiktok_dv_run"), primary_key=True)
    tenant_id: str = Field(index=True)
    mode: str = Field(default="mock", index=True)
    catalog_version: str = Field(index=True)
    dataset_digest: str = Field(index=True)
    record_count: int = 0
    status: str = Field(index=True)
    workbench_ready_snapshot: bool = False
    real_data_ready_snapshot: bool = False
    checks_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    issues_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    started_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
```

Use these constraints:

- Scope unique `(tenant_id, market)`, market `US`, status `draft|active|closed`, revision positive.
- Field unique `(tenant_id, field_code)`, domain and data type enums from the spec, status enum, positive nullable SLA, revision positive.
- Evidence unique `(tenant_id, entry_code, subject_key)`, enum checks for kind/direction/level/type/status/decision, revision positive.
- Run unique `(tenant_id, id)`, mode `mock`, status `passed|failed`, nonnegative record count, and `real_data_ready_snapshot = false`.

- [ ] **Step 5: Write the PostgreSQL up/down migrations**

Create the four tables in dependency order. Add `(tenant_id, id)` unique constraints to referenced tables, composite FKs to `business_resources(tenant_id, id)` and `users(tenant_id, id)`, tenant/status indexes, runtime and worker RLS policies, and grants matching existing migration style.

For run immutability use:

```sql
CREATE OR REPLACE FUNCTION public.reject_tiktok_data_validation_run_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tiktok data validation runs are append-only';
END;
$$;

CREATE TRIGGER tiktok_data_validation_runs_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_data_validation_runs
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_data_validation_run_mutation();
```

The down migration drops the trigger, function, and tables in reverse dependency order inside one transaction.

- [ ] **Step 6: Run focused tests and Ruff**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_postgres_tiktok_data_validation_migration.py -q
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m ruff check src\backend\app\db\models.py src\tests\backend\test_postgres_tiktok_data_validation_migration.py src\tests\backend\test_postgres_acceptance.py
```

Expected: tests pass and Ruff exits zero.

- [ ] **Step 7: Record evidence and commit**

Append changed files, commands/results, migration risks, and Task 2 as next step.

```powershell
git add -- src/backend/app/db/models.py src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.sql src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.down.sql src/tests/backend/test_postgres_tiktok_data_validation_migration.py src/tests/backend/test_postgres_acceptance.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(tiktok): add data validation persistence"
```

---

## Task 2: Add the catalog, idempotent bootstrap, and tenant-scoped workspace read

**Files:**

- Create: `src/backend/app/tiktok/data_validation.py`
- Modify: `src/backend/app/tiktok/schema.py`
- Create: `src/tests/backend/test_tiktok_data_validation.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**

- Produces constant `DATA_VALIDATION_CATALOG_VERSION = "p3-b0.v1"`.
- Produces `bootstrap_data_validation_workspace(db: Session, user: User) -> TikTokDataValidationBootstrapResponse`.
- Produces `get_data_validation_workspace(db: Session, user: User) -> TikTokDataValidationWorkspace`.
- Produces catalog entries consumed by Tasks 3-6; later tasks must not create arbitrary client-defined codes.

- [ ] **Step 1: Record Task 2 start**

State the exact initial counts: 30 field contracts and 31 capability/provider entries. Record that bootstrap creates E0/unverified rows only.

- [ ] **Step 2: Write failing bootstrap and isolation tests**

Create a SQLite session helper with two tenants, two admins, one store and one member per tenant. Add tests with these assertions:

```python
def test_bootstrap_is_idempotent_and_does_not_overwrite_tenant_edits() -> None:
    with _session() as db:
        admin = _seed_tenant(db, "tenant_a")
        first = bootstrap_data_validation_workspace(db, admin)
        contract = db.exec(
            select(TikTokFieldContract).where(
                TikTokFieldContract.tenant_id == "tenant_a",
                TikTokFieldContract.field_code == "order.order_id",
            )
        ).one()
        contract.label = "租户自定义订单编号"
        db.add(contract)
        db.commit()

        second = bootstrap_data_validation_workspace(db, admin)

        assert first.created_field_count == 30
        assert first.created_evidence_count == 31
        assert second.created_field_count == 0
        assert second.created_evidence_count == 0
        assert db.get(TikTokFieldContract, contract.id).label == "租户自定义订单编号"


def test_workspace_read_is_tenant_scoped_even_when_codes_match() -> None:
    with _session() as db:
        admin_a = _seed_tenant(db, "tenant_a")
        admin_b = _seed_tenant(db, "tenant_b")
        bootstrap_data_validation_workspace(db, admin_a)
        bootstrap_data_validation_workspace(db, admin_b)

        workspace_a = get_data_validation_workspace(db, admin_a)

        assert workspace_a.tenant_id == "tenant_a"
        assert len(workspace_a.field_contracts) == 30
        assert len(workspace_a.capability_evidence) == 31
        assert {item.tenant_id for item in workspace_a.field_contracts} == {"tenant_a"}
        assert {option.id for option in workspace_a.store_options} == {"store_tenant_a"}
        assert {option.id for option in workspace_a.owner_options} == {
            "admin_tenant_a",
            "member_tenant_a",
        }
```

Also assert every bootstrap field has exactly one `mock_fixture` source with `usage='mock'`, `decision='use'`, `authorization_state='not_required'`, while every capability begins at E0/unverified with no checker or checked time.

- [ ] **Step 3: Run tests and observe failure**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation.py -q
```

Expected: collection fails because `app.tiktok.data_validation` and new schemas do not exist.

- [ ] **Step 4: Add strict schema types**

Add these public Pydantic models in `app/tiktok/schema.py`:

```python
class TikTokFieldSource(BaseModel):
    source_key: str = Field(min_length=1, max_length=120)
    source_type: Literal[
        "official_api", "approved_export", "internal_database", "vendor", "mock_fixture"
    ]
    object_name: str = Field(min_length=1, max_length=160)
    field_path: str = Field(min_length=1, max_length=240)
    priority: int = Field(ge=1)
    usage: Literal["mock", "real"]
    decision: Literal["use", "defer", "reject"]
    authorization_state: Literal["not_required", "unverified", "authorized", "denied"]


class TikTokDataValidationBlocker(BaseModel):
    code: str
    target_type: Literal["workspace", "scope", "field", "capability", "provider", "run"]
    target_code: str
    detail: str


class TikTokDataValidationReadiness(BaseModel):
    workbench_ready: bool
    real_data_ready: bool
    blockers: list[TikTokDataValidationBlocker]
```

Add read models for the four tables, safe store/owner options, bootstrap counts, latest runs, and `TikTokDataValidationWorkspace`. Field sources must serialize as `list[TikTokFieldSource]`; never expose `ExternalAuthorization.credential_ref`, `token_fingerprint`, or `metadata_json`.

- [ ] **Step 5: Define the exact catalogs**

In `data_validation.py`, define immutable field catalog rows for these codes:

```python
FIELD_CODES = (
    "sample.application_id", "sample.creator_id", "sample.product_id",
    "sample.status", "sample.applied_at", "sample.fulfillment_due_at",
    "order.order_id", "order.creator_id", "order.product_id",
    "order.status", "order.created_at", "order.completed_at",
    "logistics.order_id", "logistics.tracking_number",
    "logistics.status", "logistics.occurred_at",
    "video.video_id", "video.creator_id", "video.product_id",
    "video.published_at", "video.view_count", "video.like_count",
    "attribution.pid", "attribution.order_id",
    "attribution.window_start", "attribution.window_end",
    "gmv.order_id", "gmv.amount", "gmv.currency", "gmv.occurred_at",
)
```

Define 27 capability codes and 4 provider decisions:

```python
CAPABILITY_CODES = (
    "seller.shop.read", "seller.permissions.read", "seller.products.read",
    "seller.orders.read", "seller.logistics.read",
    "affiliate.samples.read", "affiliate.orders.read", "affiliate.gmv.read",
    "creator.profiles.read", "creator.videos.read", "partner.collaborations.read",
    "ads.campaigns.read", "ads.product_metrics.read",
    "ads.creative_metrics.read", "ads.attribution.read",
    "live.sessions.read", "live.products.read", "live.engagement.read", "live.gmv.read",
    "messaging.conversations.read", "messaging.suggestions.generate",
    "messaging.manual_send", "messaging.controlled_send",
    "customer_service.tickets.read", "customer_service.suggestions.generate",
    "customer_service.manual_send", "customer_service.controlled_send",
)
PROVIDER_CODES = (
    "provider.fastmoss", "provider.lingxing_erp", "provider.dami_ultra", "provider.feishu"
)
PROVIDER_LABELS = {
    "provider.fastmoss": "FastMoss",
    "provider.lingxing_erp": "领星 / ERP",
    "provider.dami_ultra": "达密 Ultra",
    "provider.feishu": "飞书",
}
```

Each catalog item includes its label, domain, data type/business key/default missing behavior or platform/action/direction. Use `tuple` constants so bootstrap cannot mutate the process catalog.

- [ ] **Step 6: Implement bootstrap and safe workspace reads**

Use only `user.tenant_id` for tenant filters. Call `ensure_tenant_admin` in bootstrap. For each missing code insert one row; for existing codes leave every field untouched. Workspace reads are available to any authenticated tenant user and return:

```python
TikTokDataValidationWorkspace(
    tenant_id=user.tenant_id,
    catalog_version=DATA_VALIDATION_CATALOG_VERSION,
    scope=scope_read,
    field_contracts=field_reads,
    capability_evidence=evidence_reads,
    recent_runs=run_reads,
    store_options=active_tiktok_us_stores,
    owner_options=active_tenant_users,
    readiness=evaluate_data_validation_readiness(
        scope=scope_row,
        field_contracts=field_rows,
        evidence=evidence_rows,
        latest_run=latest_run,
        active_authorizations=authorization_rows,
        now=utc_now(),
        has_recorded_or_real_validation=False,
    ),
)
```

Sort fields by catalog order, evidence by catalog order, owners by username, and runs newest first with a limit of 20. A missing catalog returns a `catalog_not_bootstrapped` blocker instead of creating data on GET.

- [ ] **Step 7: Run focused tests and Ruff**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation.py -q
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m ruff check src\backend\app\tiktok\data_validation.py src\backend\app\tiktok\schema.py src\tests\backend\test_tiktok_data_validation.py
```

- [ ] **Step 8: Record evidence and commit**

```powershell
git add -- src/backend/app/tiktok/data_validation.py src/backend/app/tiktok/schema.py src/tests/backend/test_tiktok_data_validation.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(tiktok): bootstrap data validation catalog"
```

---

## Task 3: Add guarded edits, revision conflicts, and readiness evaluation

**Files:**

- Modify: `src/backend/app/tiktok/data_validation.py`
- Modify: `src/backend/app/tiktok/schema.py`
- Modify: `src/tests/backend/test_tiktok_data_validation.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**

- Produces `update_data_validation_scope(db, user, request)`.
- Produces `update_field_contract(db, user, field_code, request)`.
- Produces `update_capability_evidence(db, user, entry_code, request)`.
- Produces `evaluate_data_validation_readiness(*, scope: TikTokDataValidationScope | None, field_contracts: Sequence[TikTokFieldContract], evidence: Sequence[TikTokCapabilityEvidence], latest_run: TikTokDataValidationRun | None, active_authorizations: Sequence[ExternalAuthorization], now: datetime, has_recorded_or_real_validation: bool) -> TikTokDataValidationReadiness` used by Tasks 4-6.
- Produces domain exceptions `TikTokDataValidationNotFound` and `TikTokDataValidationConflict` for Task 5 HTTP mapping.

- [ ] **Step 1: Record Task 3 start**

Record admin-only mutation, revision checks, same-tenant references, evidence combination rules, and the no-E3-inheritance rule.

- [ ] **Step 2: Add failing source validation and mutation tests**

Add request schemas with `revision` and write tests for:

```python
def test_field_source_rejects_duplicate_priority_and_denied_use() -> None:
    with pytest.raises(ValidationError):
        TikTokFieldContractUpdate(
            revision=1,
            owner_user_id="admin_tenant_a",
            business_key="order_id",
            freshness_sla_seconds=3600,
            missing_behavior="block_stage",
            status="confirmed",
            sources=[
                _source("mock.order.id", priority=1, usage="mock"),
                _source("mock.order.id.copy", priority=1, usage="mock"),
            ],
        )
    with pytest.raises(ValidationError):
        TikTokFieldContractUpdate(
            revision=1,
            owner_user_id="admin_tenant_a",
            business_key="order_id",
            freshness_sla_seconds=3600,
            missing_behavior="block_stage",
            status="confirmed",
            sources=[
                _source(
                    "vendor.order.id",
                    usage="real",
                    decision="use",
                    authorization_state="denied",
                )
            ],
        )


def test_stale_revision_and_cross_tenant_references_do_not_mutate() -> None:
    with _session() as db:
        admin_a = _seed_tenant(db, "tenant_a")
        admin_b = _seed_tenant(db, "tenant_b")
        bootstrap_data_validation_workspace(db, admin_a)
        updated = update_field_contract(
            db, admin_a, "order.order_id", _confirmed_contract(revision=1)
        )
        assert updated.revision == 2
        with pytest.raises(TikTokDataValidationConflict, match="revision_conflict"):
            update_field_contract(
                db, admin_a, "order.order_id", _confirmed_contract(revision=1)
            )
        with pytest.raises(TikTokDataValidationNotFound, match="owner_not_found"):
            update_field_contract(
                db,
                admin_a,
                "order.order_id",
                _confirmed_contract(revision=2, owner_user_id=admin_b.id),
            )
```

Add equivalent tests for an active scope referencing another tenant's store, a member attempting every mutation, an unknown code, and a provider decision without a summary/checker/time.

- [ ] **Step 3: Add failing evidence/readiness tests**

Pin these cases:

- E3 with any evidence type other than `real_account` is rejected.
- E2 only accepts `mock|sandbox|approved_export`; E0 only accepts `unverified`.
- `entry_kind='provider_decision'` requires `decision`, nonblank summary, checker and checked time.
- capability `blocked` with checker/time/summary satisfies the P3-B0 inventory requirement but adds a real-data blocker.
- expired E3, wrong `subject_key`, wrong US store `resource_id`, absent required scope or absent active `ExternalAuthorization` cannot satisfy the real gate.
- E3 on `seller.shop.read` never satisfies `affiliate.orders.read`.

Use one helper that fully configures the workspace, then remove one requirement at a time:

```python
readiness = evaluate_data_validation_readiness(
    scope=scope,
    field_contracts=contracts,
    evidence=entries,
    latest_run=passed_run,
    active_authorizations=authorizations,
    now=datetime(2026, 9, 22, tzinfo=UTC),
    has_recorded_or_real_validation=False,
)
assert readiness.workbench_ready is True
assert readiness.real_data_ready is False
assert "recorded_or_real_validation_missing" in {item.code for item in readiness.blockers}
```

- [ ] **Step 4: Run focused tests and confirm failure**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation.py -q
```

Expected: new update functions, request schemas and readiness evaluator are missing.

- [ ] **Step 5: Implement request schemas and invariants**

Add:

```python
class TikTokDataValidationScopeUpdate(BaseModel):
    revision: int = Field(ge=0)
    store_resource_id: str
    creator_scope_summary: str = Field(min_length=1, max_length=1000)
    business_owner_user_id: str
    data_owner_user_id: str
    status: Literal["draft", "active", "closed"]


class TikTokFieldContractUpdate(BaseModel):
    revision: int = Field(ge=1)
    owner_user_id: str
    business_key: str = Field(min_length=1, max_length=120)
    freshness_sla_seconds: int = Field(gt=0)
    missing_behavior: Literal["unknown", "manual_review", "block_stage", "not_applicable"]
    sources: list[TikTokFieldSource] = Field(min_length=1)
    status: Literal["draft", "confirmed", "blocked", "not_applicable"]


class TikTokCapabilityEvidenceUpdate(BaseModel):
    revision: int = Field(ge=1)
    subject_key: str = Field(min_length=1, max_length=160)
    resource_id: str | None = None
    required_scope: str = Field(max_length=240)
    endpoint_or_artifact: str = Field(max_length=400)
    api_version: str = Field(max_length=80)
    evidence_level: Literal["E0", "E1", "E2", "E3"]
    evidence_type: Literal[
        "unverified", "official_docs", "contract", "mock",
        "sandbox", "approved_export", "real_account"
    ]
    status: Literal["unverified", "verified", "blocked", "not_applicable"]
    decision: Literal["use", "defer", "reject"] | None = None
    summary: str = Field(max_length=2000)
    evidence_ref: str = Field(max_length=400)
    checked_by_user_id: str | None = None
    checked_at: datetime | None = None
    valid_until: datetime | None = None
```

Use `model_validator(mode='after')` for unique source keys/priorities, denied-use rejection, evidence-level/type combinations, provider decision requirements, and `valid_until > checked_at`.

- [ ] **Step 6: Implement updates and readiness**

Every update must:

1. call `ensure_tenant_admin(user.tenant_id, user)`;
2. load by `(tenant_id, catalog code)`;
3. validate every referenced store/user in the same tenant and active state;
4. compare request revision before mutation;
5. copy only allowed fields, increment revision, update timestamp, commit and refresh.

`update_data_validation_scope` is the only create-or-update method: when the US scope is absent it accepts `revision=0` and inserts revision 1; when the row exists it requires an exact revision match and increments it. A missing row with nonzero revision and an existing row with revision 0 both raise `revision_conflict`.

Define exceptions with stable codes:

```python
class TikTokDataValidationNotFound(ValueError):
    pass


class TikTokDataValidationConflict(ValueError):
    pass
```

Exception messages begin with `catalog_entry_not_found`, `store_not_found`, `owner_not_found`, `checker_not_found`, or `revision_conflict` so Task 5 can map them without leaking cross-tenant existence.

The readiness evaluator emits stable blocker codes from the spec. Deduplicate by `(code, target_type, target_code)` and sort in catalog order. It must inspect `ExternalAuthorization` only for real readiness; a manually selected `authorized` source without matching E3 and active authorization remains blocked.

- [ ] **Step 7: Run focused tests and Ruff**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation.py -q
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m ruff check src\backend\app\tiktok\data_validation.py src\backend\app\tiktok\schema.py src\tests\backend\test_tiktok_data_validation.py
```

- [ ] **Step 8: Record evidence and commit**

```powershell
git add -- src/backend/app/tiktok/data_validation.py src/backend/app/tiktok/schema.py src/tests/backend/test_tiktok_data_validation.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(tiktok): manage validation contracts and readiness"
```

---

## Task 4: Add deterministic Mock validation and append-only run summaries

**Files:**

- Modify: `src/backend/app/tiktok/data_validation.py`
- Modify: `src/backend/app/tiktok/schema.py`
- Modify: `src/tests/backend/test_tiktok_data_validation.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**

- Produces `validate_mock_dataset(*, contracts: Sequence[TikTokFieldContract], dataset: Mapping[str, list[dict[str, object]]], validation_clock: datetime) -> TikTokMockValidationResult` as a pure function.
- Produces `run_mock_data_validation(db: Session, user: User) -> TikTokDataValidationRunRead`.
- Updates workspace readiness by making the latest passed current-catalog run visible to `get_data_validation_workspace`.

- [ ] **Step 1: Record Task 4 start**

State the fixed fixture clock, deterministic digest requirement, append-only storage, and rule that checks/issues contain no fixture values.

- [ ] **Step 2: Add failing pure-validator tests**

Add a fixed `MOCK_VALIDATION_CLOCK = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)` and tests for:

```python
def test_mock_validation_detects_required_quality_failures_without_raw_values() -> None:
    contracts = _confirmed_field_contracts()
    dataset = deepcopy(MOCK_DATASET)
    dataset["orders"].append(deepcopy(dataset["orders"][0]))
    dataset["gmv"][0].pop("currency")
    dataset["videos"][0]["product_id"] = "unknown-product"

    result = validate_mock_dataset(
        contracts=contracts,
        dataset=dataset,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )

    codes = {issue.code for issue in result.issues}
    assert {"duplicate_business_key", "required_field_missing", "pid_product_conflict"} <= codes
    serialized = result.model_dump_json()
    assert "unknown-product" not in serialized
    assert "mock-order-001" not in serialized


def test_mock_validation_is_deterministic_for_same_catalog_and_fixture() -> None:
    first = validate_mock_dataset(
        contracts=_confirmed_field_contracts(),
        dataset=MOCK_DATASET,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )
    second = validate_mock_dataset(
        contracts=_confirmed_field_contracts(),
        dataset=MOCK_DATASET,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )
    assert first.dataset_digest == second.dataset_digest
    assert first.checks == second.checks
    assert first.issues == second.issues
```

Add separate single-failure tests for stale `observed_at`, negative/invalid decimal amount, lowercase or missing currency, inverted attribution window, broken order/logistics relation, missing key, and a real source with `denied + use` injected directly at persistence level.

- [ ] **Step 3: Add failing persistence tests**

```python
def test_mock_runs_are_appended_and_never_mark_real_data_ready() -> None:
    with _session() as db:
        admin = _fully_configured_workspace(db, "tenant_a")
        first = run_mock_data_validation(db, admin)
        second = run_mock_data_validation(db, admin)
        runs = db.exec(
            select(TikTokDataValidationRun)
            .where(TikTokDataValidationRun.tenant_id == "tenant_a")
            .order_by(TikTokDataValidationRun.created_at)
        ).all()
        assert len(runs) == 2
        assert first.dataset_digest == second.dataset_digest
        assert first.status == second.status == "passed"
        assert first.real_data_ready_snapshot is False
        assert second.real_data_ready_snapshot is False
        serialized = json.dumps(
            [{"checks": row.checks_json, "issues": row.issues_json} for row in runs],
            ensure_ascii=False,
        )
        assert "mock-order-001" not in serialized
        assert "mock-creator-001" not in serialized
        assert get_data_validation_workspace(db, admin).readiness.workbench_ready is True
```

Also assert a member receives 403 before a run row is inserted.

- [ ] **Step 4: Run tests and confirm failure**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation.py -q
```

- [ ] **Step 5: Implement schemas, canonical digest, and validators**

Add safe result models:

```python
class TikTokDataValidationCheck(BaseModel):
    code: str
    passed: bool
    checked_count: int = Field(ge=0)


class TikTokDataValidationIssue(BaseModel):
    code: str
    field_code: str
    severity: Literal["warning", "error"]
    detail: str


class TikTokMockValidationResult(BaseModel):
    catalog_version: str
    dataset_digest: str
    record_count: int
    status: Literal["passed", "failed"]
    checks: list[TikTokDataValidationCheck]
    issues: list[TikTokDataValidationIssue]
```

Canonicalize with sorted dictionary keys and compact separators, then calculate `sha256` over UTF-8 bytes. The digest input contains the fixture and catalog version; database JSON stores only check codes/counts and issue metadata.

Implement checks in this order so output stays stable: required/type, business-key uniqueness, relationships, amount/currency, time/window, freshness, PID/product, selected-source authorization. Sort issues by `(code, field_code)`.

- [ ] **Step 6: Implement the run transaction**

`run_mock_data_validation` calls `ensure_tenant_admin`, requires all 30 current-catalog contracts to exist, validates the fixed fixture, evaluates readiness with the new result as latest run, inserts exactly one `TikTokDataValidationRun`, commits and returns a read model. Set `real_data_ready_snapshot=False` unconditionally and assert this invariant before insert.

- [ ] **Step 7: Run focused tests and Ruff**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation.py -q
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m ruff check src\backend\app\tiktok\data_validation.py src\backend\app\tiktok\schema.py src\tests\backend\test_tiktok_data_validation.py
```

- [ ] **Step 8: Record evidence and commit**

```powershell
git add -- src/backend/app/tiktok/data_validation.py src/backend/app/tiktok/schema.py src/tests/backend/test_tiktok_data_validation.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(tiktok): run deterministic data validation"
```

---

## Task 5: Expose the workbench API with admin write controls

**Files:**

- Modify: `src/backend/app/api/tiktok.py`
- Create: `src/tests/backend/test_tiktok_data_validation_api.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**

- Produces the six routes from the approved spec under `/api/enterprise/tiktok/data-validation`.
- Consumes Task 2-4 service functions and schemas without duplicating business rules.
- Produces stable HTTP mapping: not found 404, revision conflict 409, Pydantic validation 422, non-admin 403.

- [ ] **Step 1: Record Task 5 start**

Record route list, read/write permission split, safe error policy, and absence of credential fields.

- [ ] **Step 2: Write failing API tests**

Create route-level tests using temporary SQLModel sessions and direct route calls with explicit `current_user`/`db`. Cover:

```python
def test_member_can_read_but_cannot_bootstrap_edit_or_run() -> None:
    with _session() as db:
        admin, member = _seed_users(db)
        data_validation_bootstrap(current_user=admin, db=db)
        workspace = data_validation_workspace(current_user=member, db=db)
        assert workspace.tenant_id == member.tenant_id

        for call in (
            lambda: data_validation_bootstrap(current_user=member, db=db),
            lambda: data_validation_scope_update(
                request=_scope_request(), current_user=member, db=db
            ),
            lambda: data_validation_mock_run(current_user=member, db=db),
        ):
            with pytest.raises(HTTPException) as error:
                call()
            assert error.value.status_code == 403


def test_api_maps_unknown_code_and_revision_conflict_without_cross_tenant_leak() -> None:
    with _session() as db:
        admin, _member = _seed_users(db)
        data_validation_bootstrap(current_user=admin, db=db)
        with pytest.raises(HTTPException) as missing:
            data_validation_field_update(
                field_code="other-tenant-field",
                request=_field_request(revision=1),
                current_user=admin,
                db=db,
            )
        assert missing.value.status_code == 404
        assert missing.value.detail["code"] == "catalog_entry_not_found"

        data_validation_field_update(
            field_code="order.order_id",
            request=_field_request(revision=1),
            current_user=admin,
            db=db,
        )
        with pytest.raises(HTTPException) as conflict:
            data_validation_field_update(
                field_code="order.order_id",
                request=_field_request(revision=1),
                current_user=admin,
                db=db,
            )
        assert conflict.value.status_code == 409
        assert conflict.value.detail["code"] == "revision_conflict"
```

Also assert the serialized GET response contains neither `credential_ref`, `token_fingerprint`, `metadata_json`, raw fixture record IDs nor secrets.

- [ ] **Step 3: Run API tests and observe failure**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_tiktok_data_validation_api.py -q
```

- [ ] **Step 4: Add the six routes and error mapper**

Add:

```python
@router.get("/data-validation", response_model=TikTokDataValidationWorkspace)
def data_validation_workspace(current_user=Depends(get_current_user), db=Depends(get_session)):
    return get_data_validation_workspace(db, current_user)


@router.post("/data-validation/bootstrap", response_model=TikTokDataValidationBootstrapResponse)
def data_validation_bootstrap(current_user=Depends(get_current_user), db=Depends(get_session)):
    return bootstrap_data_validation_workspace(db, current_user)


@router.put("/data-validation/pilot-scope", response_model=TikTokDataValidationScopeRead)
def data_validation_scope_update(
    request: TikTokDataValidationScopeUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationScopeRead:
    try:
        return update_data_validation_scope(db, current_user, request)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        raise _data_validation_http_error(exc) from exc


@router.put("/data-validation/field-contracts/{field_code}", response_model=TikTokFieldContractRead)
def data_validation_field_update(
    field_code: str,
    request: TikTokFieldContractUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokFieldContractRead:
    try:
        return update_field_contract(db, current_user, field_code, request)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        raise _data_validation_http_error(exc) from exc


@router.put(
    "/data-validation/capability-evidence/{entry_code}",
    response_model=TikTokCapabilityEvidenceRead,
)
def data_validation_evidence_update(
    entry_code: str,
    request: TikTokCapabilityEvidenceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokCapabilityEvidenceRead:
    try:
        return update_capability_evidence(db, current_user, entry_code, request)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        raise _data_validation_http_error(exc) from exc


@router.post("/data-validation/runs/mock", response_model=TikTokDataValidationRunRead)
def data_validation_mock_run(current_user=Depends(get_current_user), db=Depends(get_session)):
    return run_mock_data_validation(db, current_user)
```

Use the file's existing `Annotated` dependency style in final code. Add this mapper and call `db.rollback()` in each exception branch before raising it:

```python
def _data_validation_http_error(
    exc: TikTokDataValidationNotFound | TikTokDataValidationConflict,
) -> HTTPException:
    code, _, message = str(exc).partition(":")
    status_code = 409 if isinstance(exc, TikTokDataValidationConflict) else 404
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message.strip() or code},
    )
```

Catch only these two domain exception types. Let FastAPI/Pydantic produce 422 for invalid request bodies and let the existing permission helper produce 403.

- [ ] **Step 5: Run new API tests plus all existing TikTok backend tests**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q src\tests\backend\test_tiktok_data_validation_api.py src\tests\backend\test_tiktok_business_unit.py src\tests\backend\test_tiktok_connector_authorization.py src\tests\backend\test_tiktok_live_write_release_gate.py src\tests\backend\test_tiktok_m2m_verification.py src\tests\backend\test_tiktok_mock_exception_matrix.py src\tests\backend\test_tiktok_mock_replay_execution.py src\tests\backend\test_tiktok_mock_replay_tasks.py src\tests\backend\test_tiktok_mock_replay.py src\tests\backend\test_tiktok_official_oauth.py src\tests\backend\test_tiktok_production_bootstrap.py src\tests\backend\test_tiktok_release_evidence.py src\tests\backend\test_tiktok_release_gate.py src\tests\backend\test_tiktok_shadow.py
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m ruff check src\backend\app\api\tiktok.py src\tests\backend\test_tiktok_data_validation_api.py
```

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- src/backend/app/api/tiktok.py src/tests/backend/test_tiktok_data_validation_api.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(tiktok): expose data validation workbench API"
```

---

## Task 6: Add the TikTok “数据验证” frontend workbench

**Files:**

- Create: `src/frontend-enterprise/src/pages/tiktok/TikTokDataValidationPanel.tsx`
- Modify: `src/frontend-enterprise/src/pages/TikTokBusinessUnitPage.tsx`
- Create: `src/tests/frontend/TikTokDataValidationPanel.test.tsx`
- Modify: `docs/DEVELOPMENT_LOG.md`

**Interfaces:**

- Produces `TikTokDataValidationPanel({ currentUser }: { currentUser: EnterpriseAuthUser })`.
- Consumes the six API routes from Task 5.
- Keeps workbench data/fetch/edit state inside the panel; the existing page only owns active tab selection.

- [ ] **Step 1: Record Task 6 start**

Record visible UI scope, role differences, accessibility labels, error behavior, and the rule that no raw Mock rows or credential fields are rendered.

- [ ] **Step 2: Write failing administrator and member UI tests**

Mock `@/api/client` and render the panel directly. Use this fixture shape:

```typescript
const workspace = {
  tenant_id: 'tenant_demo',
  catalog_version: 'p3-b0.v1',
  scope: null,
  readiness: {
    workbench_ready: true,
    real_data_ready: false,
    blockers: [{
      code: 'recorded_or_real_validation_missing',
      target_type: 'workspace',
      target_code: 'real_data',
      detail: '缺少真实或脱敏录制回放',
    }],
  },
  field_contracts: [{
    field_code: 'order.order_id',
    domain: 'order',
    label: '订单 ID',
    required: true,
    owner_user_id: 'admin',
    business_key: 'order_id',
    freshness_sla_seconds: 3600,
    missing_behavior: 'block_stage',
    sources: [{
      source_key: 'mock.order.order_id',
      source_type: 'mock_fixture',
      object_name: 'orders',
      field_path: 'order_id',
      priority: 1,
      usage: 'mock',
      decision: 'use',
      authorization_state: 'not_required',
    }],
    status: 'confirmed',
    revision: 2,
  }],
  capability_evidence: [{
    entry_code: 'seller.orders.read',
    entry_kind: 'capability',
    platform_domain: 'Seller',
    action: '读取订单',
    direction: 'read',
    subject_key: 'global',
    evidence_level: 'E2',
    evidence_type: 'mock',
    status: 'verified',
    decision: null,
    summary: 'Mock 契约已验证',
    revision: 2,
  }],
  recent_runs: [{
    id: 'run-1',
    mode: 'mock',
    catalog_version: 'p3-b0.v1',
    dataset_digest: 'sha256:digest',
    record_count: 6,
    status: 'passed',
    workbench_ready_snapshot: true,
    real_data_ready_snapshot: false,
    checks: [{ code: 'required_fields', passed: true, checked_count: 30 }],
    issues: [],
    created_at: '2026-09-22T00:00:00Z',
  }],
  store_options: [{ id: 'store-us', label: 'TikTok Shop US' }],
  owner_options: [{ id: 'admin', label: '管理员' }],
};
```

Tests:

```typescript
it('shows separate readiness states and lets an admin run Mock validation', async () => {
  vi.mocked(api.get).mockResolvedValue(workspace);
  vi.mocked(api.post).mockResolvedValue(workspace.recent_runs[0]);
  render(<TikTokDataValidationPanel currentUser={adminUser} />);

  expect(await screen.findByText('工作台配置就绪')).toBeInTheDocument();
  expect(screen.getByText('真实数据未就绪')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '运行 Mock 校验' }));
  expect(api.post).toHaveBeenCalledWith('/api/enterprise/tiktok/data-validation/runs/mock');
  expect(screen.queryByText('mock-order-001')).not.toBeInTheDocument();
});


it('keeps the same tenant workspace read-only for a member', async () => {
  vi.mocked(api.get).mockResolvedValue(workspace);
  render(<TikTokDataValidationPanel currentUser={memberUser} />);

  expect(await screen.findByText('只读模式')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '初始化验证目录' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '运行 Mock 校验' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '保存字段契约' })).not.toBeInTheDocument();
});
```

Add tests for empty/unbootstrapped state, bootstrap reload, scope save, API error notice, field save with revision, capability save, provider decision, and status badges for blocked/expired/E0-E3.

- [ ] **Step 3: Run the new frontend test and observe failure**

```powershell
npm --prefix src/frontend-enterprise test -- TikTokDataValidationPanel.test.tsx
```

Expected: module/component not found.

- [ ] **Step 4: Implement the focused panel**

The component loads only when mounted and owns:

```typescript
const [workspace, setWorkspace] = useState<TikTokDataValidationWorkspace | null>(null);
const [loading, setLoading] = useState(true);
const [busyKey, setBusyKey] = useState<string | null>(null);

const load = useCallback(async () => {
  setLoading(true);
  try {
    setWorkspace(await api.get<TikTokDataValidationWorkspace>(
      '/api/enterprise/tiktok/data-validation',
    ));
  } catch (error) {
    notify.error(error instanceof Error ? error.message : '加载数据验证工作台失败');
  } finally {
    setLoading(false);
  }
}, []);
```

Render five semantic sections:

1. two separate readiness cards plus blocker list;
2. US pilot scope form with store/owner selects and creator scope text;
3. field table grouped by domain with inline editable owner/key/SLA/missing behavior/status/source summary;
4. capability matrix and provider decisions with level/type/status/decision/summary/check time;
5. Mock run action and recent safe summaries.

Each save sends the row's current `revision`, disables only that row through `busyKey`, reloads after success, and displays API 409/422 messages without clearing the user's form. Do not render fixture values, authorization metadata or secret-related fields.

- [ ] **Step 5: Mount the seventh tab in the existing page**

Change the tab union and navigation:

```typescript
type TikTokTab =
  | 'overview' | 'employees' | 'assets' | 'tasks'
  | 'skills' | 'risk' | 'data-validation';

['data-validation', '数据验证'],
```

Mount only while active so initial TikTok page load does not add an API request:

```tsx
{activeTab === 'data-validation' && (
  <TikTokDataValidationPanel currentUser={currentUser} />
)}
```

- [ ] **Step 6: Run frontend focused tests, typecheck, i18n and config checks**

```powershell
npm --prefix src/frontend-enterprise test -- TikTokDataValidationPanel.test.tsx
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise run i18n:check
npm --prefix src/frontend-enterprise run config:check
```

- [ ] **Step 7: Record evidence and commit**

```powershell
git add -- src/frontend-enterprise/src/pages/tiktok/TikTokDataValidationPanel.tsx src/frontend-enterprise/src/pages/TikTokBusinessUnitPage.tsx src/tests/frontend/TikTokDataValidationPanel.test.tsx docs/DEVELOPMENT_LOG.md
git commit -m "feat(tiktok): add data validation workbench UI"
```

---

## Task 7: Run repository gates and perform dual-role browser acceptance

**Files:**

- Modify: `docs/PROJECT_MEMORY.md`
- Modify: `docs/SESSION_HANDOFF.md`
- Modify: `docs/README.md`
- Modify: `docs/DEVELOPMENT_LOG.md`
- Create if screenshots are captured: `docs/screenshots/tiktok-p3b0/*.png`

**Interfaces:**

- Consumes all prior tasks as one feature branch.
- Produces fresh verification evidence, browser acceptance for administrator and member, durable architecture memory, and exact next actions for real E3/recorded validation.

- [ ] **Step 1: Record Task 7 start**

Record the complete verification matrix, the known full-backend baseline caveat, and that browser screenshots must exclude secrets, PII and raw external payloads.

- [ ] **Step 2: Run all focused backend tests and migration/layout gates**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini -q src\tests\backend\test_tiktok_data_validation.py src\tests\backend\test_tiktok_data_validation_api.py src\tests\backend\test_postgres_tiktok_data_validation_migration.py src\tests\backend\test_tiktok_business_unit.py src\tests\backend\test_tiktok_connector_authorization.py src\tests\backend\test_tiktok_live_write_release_gate.py src\tests\backend\test_tiktok_m2m_verification.py src\tests\backend\test_tiktok_mock_exception_matrix.py src\tests\backend\test_tiktok_mock_replay_execution.py src\tests\backend\test_tiktok_mock_replay_tasks.py src\tests\backend\test_tiktok_mock_replay.py src\tests\backend\test_tiktok_official_oauth.py src\tests\backend\test_tiktok_production_bootstrap.py src\tests\backend\test_tiktok_release_evidence.py src\tests\backend\test_tiktok_release_gate.py src\tests\backend\test_tiktok_shadow.py
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' src\tests\check_test_layout.py
```

Expected: all focused tests and layout check pass. Do not convert the known full-suite baseline into a feature success claim.

If `STAFFDECK_RUN_POSTGRES_ACCEPTANCE=1` is already configured for the isolated acceptance database, also run:

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m pytest -c pytest.ini src\tests\backend\test_postgres_acceptance.py -k tiktok_data_validation -q
```

If the variable is absent, record the opt-in PostgreSQL runtime test as skipped; the static migration/RLS test remains mandatory.

- [ ] **Step 3: Run Ruff on every changed Python file**

```powershell
& 'E:\develop\数字员工\joukir\src\backend\.venv\Scripts\python.exe' -m ruff check src\backend\app\db\models.py src\backend\app\tiktok\data_validation.py src\backend\app\tiktok\schema.py src\backend\app\api\tiktok.py src\tests\backend\test_tiktok_data_validation.py src\tests\backend\test_tiktok_data_validation_api.py src\tests\backend\test_postgres_tiktok_data_validation_migration.py src\tests\backend\test_postgres_acceptance.py
```

- [ ] **Step 4: Run complete frontend gates and production build**

```powershell
npm --prefix src/frontend-enterprise test
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise run i18n:check
npm --prefix src/frontend-enterprise run config:check
npm --prefix src/frontend-enterprise run build
```

Expected: Vitest, test TypeScript, i18n, config and build exit zero. Record an existing Vite chunk warning separately if it remains non-fatal.

- [ ] **Step 5: Start the isolated worktree and locate its selected port**

Use the existing worktree runtime handoff without printing protected configuration:

```powershell
& src\scripts\dev_up.ps1 --detach
& src\scripts\dev_status.ps1
```

The launcher selects the next free port if 5173 is occupied. Read `.dev/app.port` for the worktree only; do not stop or alter the main workspace service.

- [ ] **Step 6: Perform administrator browser acceptance**

Using the isolated local test database and a local administrator session:

1. open `/enterprise/tiktok` and select “数据验证”;
2. bootstrap the catalog and verify 30 field rows plus 31 capability/provider rows;
3. configure US scope and save one field/evidence row, refresh, and confirm revision-backed persistence;
4. run Mock validation and confirm the summary passes without raw record values;
5. confirm “工作台配置” and “真实数据” are separate and Mock leaves real data unready;
6. capture one screenshot with no credentials, PII, OAuth payloads or raw fixture data.

- [ ] **Step 7: Perform member browser acceptance**

Use an existing local member account in the isolated test database. If none exists, create one through the normal administrator account UI with a runtime-only random password, perform the check, then deactivate/delete that temporary account through the same UI without recording the password.

Verify the member can open the same tenant workbench and see safe summaries, while bootstrap, edit, and Mock-run controls are absent. Capture one safe screenshot.

- [ ] **Step 8: Stop the isolated service and update durable docs**

```powershell
& src\scripts\dev_down.ps1
```

Update:

- `PROJECT_MEMORY.md`: four-table P3-B0 workbench boundary, action-level evidence, and Mock/real readiness separation.
- `SESSION_HANDOFF.md`: branch, commit list, test/browser evidence, any blockers, and the next real E3/recorded-validation action.
- `docs/README.md`: link the implementation plan and screenshot directory if screenshots exist.
- `DEVELOPMENT_LOG.md`: exact fresh command results, selected port, role checks, remaining risks and next step.

- [ ] **Step 9: Verify the final branch diff**

```powershell
git status --short
git diff --check
git log --oneline --decorate -8
```

Confirm only planned files are changed and no ignored runtime data, `.env`, credentials, local database, logs or pytest temp directories are staged.

- [ ] **Step 10: Commit final documentation and request review**

```powershell
git add -- docs/PROJECT_MEMORY.md docs/SESSION_HANDOFF.md docs/README.md docs/DEVELOPMENT_LOG.md docs/screenshots/tiktok-p3b0
git commit -m "docs(tiktok): record P3-B0 workbench verification"
```

If no screenshots were created, omit that path from `git add`. Invoke `superpowers:requesting-code-review`, review the whole branch against the approved spec, fix any finding with a fresh targeted test, rerun affected gates, and only then report implementation status.

## Completion Evidence Required

Before claiming the workbench is complete, the final report must include:

- branch and final commit IDs;
- new and total TikTok backend test counts from fresh output;
- frontend file/test counts, typecheck, i18n, config and build results;
- migration/RLS and test-layout results;
- administrator/member browser routes and screenshot links;
- explicit statement that `real_data_ready` remains false until a matching E3 plus real or approved recorded validation exists;
- any full-backend baseline failures, clearly separated from this feature's focused gates.
