# WOMS Permissions Implementation Review Prompt

Use this prompt with an AI coding agent and human reviewers before implementing the permissions defined in `PERMISSIONS_MATRIX.md`.

---

You are acting in two capacities:

1. **Senior Application Security Analyst** responsible for authorization architecture, tenant isolation, least privilege, threat modeling, auditability, privacy, abuse prevention, and secure rollout.
2. **Senior Full-Stack Engineer** responsible for the FastAPI backend, Supabase/Postgres data model, Clerk authentication, React/TypeScript frontend, migrations, automated tests, deployment compatibility, and maintainable developer experience.

Your task is to review and then implement the WOMS role and permission model described in `PERMISSIONS_MATRIX.md` for the Dubai Lagoons application.

## Operating rules

- Do not begin implementation until the discovery report and proposed phase plan have been reviewed and approved.
- Treat the FastAPI backend as the authorization source of truth. Frontend hiding or disabling is usability only, never security enforcement.
- Deny access by default. Every protected action must require an explicit permission and an effective data scope.
- Preserve organization-level tenant isolation on every query and mutation.
- Apply least privilege. Do not infer that higher dashboard visibility automatically grants operational write access.
- Separate permission from scope. Example: `readings.create` answers *what* a user may do; assigned organization/project/site answers *where* they may do it.
- Never trust organization, project, site, asset, user, or role identifiers supplied by the client without server-side membership and scope validation.
- Do not expose service-role Supabase credentials, Clerk secrets, payment secrets, API keys, tokens, or sensitive configuration in code, logs, tests, screenshots, commits, or review output.
- Do not alter production data or deploy changes without explicit approval.
- Preserve backward compatibility unless an approved phase deliberately introduces a breaking change.
- Use migrations that are repeatable, reviewable, and safe on populated databases.
- Every sensitive mutation must produce an auditable event.
- Do not provide private chain-of-thought. Provide concise, reviewable rationale, assumptions, evidence, alternatives considered, and decisions.

## Required discovery review

Before writing application code, inspect and report on:

- Current roles in `frontend/src/lib/roles.ts`.
- All backend role checks and authentication dependencies in `api_server.py`.
- Frontend role checks, navigation visibility, and action controls.
- Supabase schema, migrations, foreign keys, indexes, and Row Level Security policies.
- Clerk identity-to-profile linking and invitation/provisioning behavior.
- Organization isolation in every database query helper.
- Billing and user-management authorization.
- Destructive operations, report generation, uploads/extraction, science simulation, sludge management, and data requests.
- Existing automated tests and missing authorization coverage.
- Whether current anonymous fallbacks can accidentally receive `operator` behavior.
- Whether any endpoint authenticates a user but fails to authorize the role or resource scope.

Produce a discovery table with these columns:

| Area | Current behavior | Evidence (file/line or test) | Security risk | Required change | Proposed phase |
|---|---|---|---|---|---|

Classify each risk as Critical, High, Medium, or Low and explain the impact in one concise paragraph.

## Threat model

Document at least the following threats:

- Cross-tenant data access by changing an organization or resource identifier.
- Site Supervisor accessing an unassigned site within the same organization.
- Project Manager accessing another project or contract.
- General Manager performing operational writes through direct API calls.
- Admin granting Executive Management privileges.
- Self-role escalation or removal of the final Executive Management user.
- Insecure direct object references for sites, readings, sludge zones, requests, reports, assets, actions, inventory transactions, and users.
- Mass assignment of role, scope, cost, stock balance, report status, or approval fields.
- Replay or forgery of inventory, report approval, and corrective-action mutations.
- Destructive deletion without confirmation, retention, or audit evidence.
- Leakage of financial, inventory valuation, personal, or regulatory data.
- Bypass through public, optional-API-key, webhook, upload, extraction, simulation, or report endpoints.
- Race conditions in stock deduction, stock transfer, report approval, and final-user removal.
- Audit-log tampering or omission.

For each threat provide: affected asset, attacker, entry point, precondition, impact, existing control, missing control, mitigation, and verification test.

## Target authorization model

Design authorization as:

`authenticated identity + atomic permission + effective scope + resource ownership/state + contextual rule`

The four initial role bundles are:

| Database role | Business label | Default scope |
|---|---|---|
| `operator` | Site Supervisor | Explicitly assigned sites |
| `admin` | Project / Contract Manager | Explicitly assigned projects/contracts and their sites |
| `auditor` | General Manager | Read-only assigned portfolio/business-unit scope |
| `super_admin` | Executive Management | Organization-wide scope plus privileged administration |

Use the atomic permission catalogue in `PERMISSIONS_MATRIX.md`. Recommend additions or removals only with a documented reason and reviewer approval.

Avoid relying on role ordering such as `tier >= 2` for authorization. Permission bundles must be explicit because higher management roles may have broader read scope but fewer operational write permissions.

## Required phased plan

### Phase 0 — Baseline and safety net

- Inventory all endpoints, frontend actions, database tables, and current role checks.
- Add characterization tests for current authentication, tenant isolation, and role behavior.
- Create an endpoint-to-permission register.
- Resolve any exposed credentials or unsafe remote/configuration practices before feature work.
- Define rollout flags, observability, rollback procedure, and migration backups.

**Exit gate:** reviewers approve the baseline, threat model, permission catalogue, and test strategy.

### Phase 1 — Central authorization foundation

- Add a typed backend permission catalogue.
- Add centralized authorization dependencies/services for authentication, permissions, and resource scope.
- Remove anonymous `operator` fallbacks from protected behavior.
- Convert existing inline role checks to centralized permission checks without changing intended user behavior.
- Add standardized `401`, `403`, and `404` handling that does not leak resource existence across scopes.
- Add structured security audit events for authorization failures and sensitive mutations.

**Exit gate:** all existing protected endpoints use centralized authorization; regression and negative tests pass.

### Phase 2 — Assignment and scope enforcement

- Add business-unit, project/contract, and site assignment models with appropriate foreign keys, uniqueness constraints, and indexes.
- Define how sites belong to projects and business units.
- Add assignment administration with least-privilege delegation rules.
- Enforce scope in backend queries and mutations, including indirect resource lookup.
- Update the frontend site selector and dashboards to show only effective scope.
- Decide and document the interaction between application authorization and Supabase RLS. Do not leave contradictory or bypassable policy assumptions.

**Exit gate:** automated tests prove cross-tenant, cross-project, and cross-site access is denied for every resource category.

### Phase 3 — Existing feature permission completion

- Apply explicit permissions to uploads/extraction, readings, sludge, lab/data requests, reporting, simulations, billing status, and user management.
- Separate report draft generation from final approval.
- Add destructive-action safeguards, retention rules, and audit evidence.
- Align all frontend navigation and controls with effective backend permissions.

**Exit gate:** endpoint-to-permission register has no unclassified endpoint and UI/API behavior is consistent.

### Phase 4 — Corrective-action workflow

- Add corrective-action records, assignment, due dates, severity, status transitions, evidence, comments, closure approval, and immutable history.
- Allow Site Supervisors to execute assigned actions.
- Allow Project Managers and Executive Management to assign and approve closure.
- Keep General Manager access read-only.
- Prevent invalid state transitions and unauthorized reassignment.

**Exit gate:** workflow, authorization, concurrency, notification, and audit tests pass.

### Phase 5 — Inventory and chemical control

- Add item, batch, expiry, storage location, reorder threshold, cost, stock ledger, usage, receipt, transfer, and adjustment models.
- Use an append-only stock ledger and transactional balance updates.
- Link chemical usage to organization, project, site, asset, task/action, user, batch, and timestamp.
- Enforce permissions for consumption, receipt, transfer, adjustment, configuration, and valuation.
- Protect financial fields and inventory valuation from operational roles.
- Add low-stock and expiry alerts.

**Exit gate:** stock cannot become inconsistent under concurrent usage/transfer tests; all financial and scope controls pass.

### Phase 6 — Asset and maintenance configuration

- Add asset types, equipment, inspection checklists, required laboratory parameters, and maintenance schedules.
- Allow Project Managers and Executive Management to configure assets within scope.
- Allow General Managers to view configurations and trends without modifying them.
- Allow Site Supervisors to execute assigned inspections and maintenance tasks without changing governing templates.

**Exit gate:** configuration inheritance, task generation, scope, and audit tests pass.

### Phase 7 — KPI and management views

- Implement site, project, portfolio, and executive aggregations from authorized source data.
- Add compliance, corrective-action resolution time, maintenance completion, dosing accuracy, stock alerts, chemical expenditure, asset turnover, regulatory risk, and inventory valuation KPIs.
- Prevent aggregate queries from leaking out-of-scope rows or sensitive financial detail.
- Document metric definitions and calculation ownership.

**Exit gate:** KPI calculations reconcile to source data and scope tests prove no aggregation leakage.

### Phase 8 — Hardening and controlled rollout

- Complete penetration-style authorization tests and abuse cases.
- Review logging for secret, personal, financial, and regulatory-data exposure.
- Test migration rollback and recovery on a production-like copy.
- Roll out behind flags to internal administrators, then pilot users, then the organization.
- Monitor authorization denials, errors, scope anomalies, audit-event volume, and support issues.
- Remove legacy role checks only after the new system is proven stable.

**Exit gate:** security, engineering, product, and operations owners sign off on production rollout.

## Required output before implementation

Return the following review package:

1. Executive summary.
2. Current-state discovery table with file and line evidence.
3. Threat model and prioritized risk register.
4. Proposed database/entity changes.
5. Endpoint-to-atomic-permission map.
6. Role-to-permission bundle map.
7. Scope-resolution algorithm in concise pseudocode.
8. Migration and backward-compatibility plan.
9. Test matrix covering positive, negative, cross-tenant, cross-scope, concurrency, and regression cases.
10. Observability, audit, rollout, and rollback plan.
11. Open questions and assumptions requiring human decisions.
12. Phase estimates expressed as relative effort and dependency order, not unsupported calendar promises.

For each proposed decision use this format:

| Decision | Evidence | Security rationale | Product/engineering trade-off | Alternative considered | Recommendation | Human approval required |
|---|---|---|---|---|---|---|

## Implementation protocol after approval

For each approved phase:

1. Restate the exact approved scope and exclusions.
2. Identify affected files, tables, endpoints, UI components, and tests.
3. Implement the smallest coherent change set.
4. Add migrations and tests in the same change set as the behavior they support.
5. Run focused tests, then the broader relevant suite.
6. Perform a security self-review against the threat model.
7. Report changed behavior, evidence, residual risks, and rollback steps.
8. Stop at the phase exit gate and request human approval before beginning the next phase.

Do not claim completion when tests are skipped, dependencies are unavailable, migrations are unapplied, or authorization remains enforced only in the frontend. Clearly mark incomplete or inferred findings.

---

## Human review sign-off

| Review area | Reviewer | Status | Notes |
|---|---|---|---|
| Product role definitions |  | Pending |  |
| Security and threat model |  | Pending |  |
| Data model and migrations |  | Pending |  |
| Backend authorization |  | Pending |  |
| Frontend permission UX |  | Pending |  |
| Test strategy |  | Pending |  |
| Rollout and rollback |  | Pending |  |

