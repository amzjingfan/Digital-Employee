from pathlib import Path

import casbin


def main() -> None:
    deploy_root = Path(__file__).resolve().parent.parent
    enforcer = casbin.Enforcer(
        str(deploy_root / "casbin" / "model.conf"),
        str(deploy_root / "casbin" / "policy.csv.example"),
    )

    checks = [
        ("tenant_admin", "tenant_demo", "/api/enterprise/agents", "POST", True),
        ("tenant_member", "tenant_demo", "/api/enterprise/agents", "GET", True),
        ("tenant_member", "tenant_demo", "/api/enterprise/agents/42", "DELETE", False),
        ("tenant_member", "tenant_demo", "/api/enterprise/teams", "POST", True),
        ("tenant_member", "tenant_other", "/api/enterprise/scheduled-tasks/42", "PUT", True),
        (
            "tenant_member",
            "tenant_demo",
            "/api/enterprise/authorization-decisions",
            "GET",
            False,
        ),
        ("tenant_unknown", "tenant_demo", "/api/enterprise/agents", "GET", False),
        (
            "operations_supervisor",
            "tenant_demo",
            "/api/enterprise/sessions/export",
            "POST",
            True,
        ),
        (
            "operations_supervisor",
            "tenant_demo",
            "/api/enterprise/model-configs",
            "POST",
            False,
        ),
        (
            "after_sales_specialist",
            "tenant_demo",
            "/api/enterprise/feedback/case-1",
            "POST",
            True,
        ),
        (
            "listing_compliance_specialist",
            "tenant_demo",
            "/api/enterprise/knowledge/documents",
            "POST",
            True,
        ),
        (
            "logistics_exception_specialist",
            "tenant_demo",
            "/api/enterprise/scheduled-tasks/task-1",
            "PATCH",
            True,
        ),
        (
            "advertising_inspection_specialist",
            "tenant_demo",
            "/api/enterprise/scheduled-tasks/task-1",
            "DELETE",
            True,
        ),
        (
            "designer",
            "tenant_demo",
            "/api/enterprise/knowledge/documents",
            "PUT",
            True,
        ),
        (
            "procurement_specialist",
            "tenant_demo",
            "/api/enterprise/tools/tool-1",
            "DELETE",
            False,
        ),
    ]

    failures: list[str] = []
    for subject, tenant, resource, action, expected in checks:
        actual = enforcer.enforce(subject, tenant, resource, action)
        if actual != expected:
            failures.append(
                f"{subject=} {tenant=} {resource=} {action=}: "
                f"expected {expected}, received {actual}"
            )

    if failures:
        raise AssertionError("\n".join(failures))

    print(f"Casbin tenant-domain smoke test passed: {len(checks)} decisions")


if __name__ == "__main__":
    main()
