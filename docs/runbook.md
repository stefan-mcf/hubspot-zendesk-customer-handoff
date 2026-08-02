# Local operator runbook

## Validate

```bash
make validate
```

## Generate a deterministic plan

```bash
make plan
```

Review the generated files under `build/plan/` before using them as inputs to
any provider-specific tooling.

## Bind a Zendesk organization

After an authorized provider run has returned one organization record:

```bash
customer-handoff bind-user \
  --plan build/plan/handoff-plan.json \
  --organization-readback path/to/organization-readback.json \
  --output build/plan/zendesk-user-upsert.json
```

## Reconcile provider readbacks

```bash
customer-handoff reconcile \
  --plan build/plan/handoff-plan.json \
  --hubspot-readback path/to/hubspot-readback.json \
  --zendesk-organization-readback path/to/organization-readback.json \
  --zendesk-user-readback path/to/user-readback.json \
  --output build/reconciliation.json
```

Provider writes are intentionally outside this public repository. They require
tenant-specific authorization, exact manifests, write-ahead receipts, readback,
and a retained-record or rollback decision.

