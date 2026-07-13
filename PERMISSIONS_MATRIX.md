# WOMS Role and Permission Matrix

Source guide: [Comprehensive Technical and Operational Architecture of the Integrated Water Operations Management System for GCC Engineered Lagoons](https://docs.google.com/document/d/1yTQKZWTxnWCJJP8YYDvRBjmC3Fqr0ngmz88wrHDEHoo/edit?tab=t.0)

Code baseline audited: version `0.5.0`, commit `0b496a2`.

## Legend

- **V** — view/read
- **A** — perform operational action or create/update records
- **M** — administer/configure
- **—** — no permission
- **Implemented** — enforced by the current backend
- **Partial** — some UI/API support exists, but scope or enforcement is incomplete
- **Gap** — required by the guide but not implemented

Permissions must be enforced by the FastAPI backend. Hiding a frontend control is not an authorization boundary.

## Current roles

| Database role | Business role | Tier | Intended data scope | Primary job function | Current implementation |
|---|---|---:|---|---|---|
| `operator` | Site Supervisor | 1 | Assigned sites only | Capture field and laboratory data, execute inspections and treatments, manage corrective actions, and record chemical usage | Operational writes are allowed, but assigned-site scoping is not implemented; access is currently organization-wide |
| `admin` | Project / Contract Manager | 2 | Assigned project/contract portfolio | Manage project compliance, sites, users, risks, actions, stock, and contract performance | Site, user, billing, and operational administration exists at organization scope; project-level assignment is not implemented |
| `auditor` | General Manager | 3 | Portfolio across projects/business units | Read-only oversight of compliance, KPIs, trends, cost, inventory, and operational health | Read-only behavior is enforced for key writes; portfolio/business-unit scoping and several management KPIs are not implemented |
| `super_admin` | Executive Management | 4 | Entire organization | Strategic oversight, regulatory risk, financial summaries, inventory valuation, and privileged administration | Full organization access and privileged user administration exist; business-unit hierarchy, inventory, and financial summaries are incomplete |

## Permission map

| Domain / permission | Site Supervisor | Project / Contract Manager | General Manager | Executive Management | Delivery state and enforcement note |
|---|:---:|:---:|:---:|:---:|---|
| Sign in and view own profile | V | V | V | V | **Implemented** — invitation/profile flow exists |
| View platform version and health | V | V | V | V | **Implemented** — version/health are intentionally public |
| View assigned site list | V | V | V | V | **Partial** — all roles currently receive every site in their organization |
| View site water-quality readings | V | V | V | V | **Partial** — organization isolation exists; site assignment does not |
| View site compliance status and alert level | V | V | V | V | **Partial** — same scope limitation as readings |
| View alerts, response protocols, science intelligence, and reference material | V | V | V | V | **Implemented/Partial** — broadly visible; not all views are backed by scoped persisted data |
| View role-specific dashboard | V | V | V | V | **Implemented** — tiered dashboards exist in the frontend |
| Upload/extract a laboratory report | A | A | — | A | **Implemented** — frontend hides upload for `auditor`; backend blocks pending/anonymous users but should explicitly allow-list roles |
| Assess readings without saving | A | A | V | A | **Partial** — endpoint uses optional API-key control and is not role-scoped |
| Record or overwrite water-quality readings | A | A | — | A | **Implemented** — backend allow-list excludes `auditor`; assigned-site validation is missing |
| Record/update sludge survey zones | A | A | — | A | **Implemented** — role allow-list exists; assigned-site validation is missing |
| Delete sludge survey zones | A | A | — | A | **Implemented**, but least privilege suggests restricting destructive deletion to Manager/Admin or adding approval/audit controls |
| View algae/community forecasts | V | V | V | V | **Implemented** at organization scope |
| Raise and fulfil laboratory/data requests | A | A | — | A | **Implemented** — role allow-list exists; assigned-site validation is missing |
| Generate/view compliance reports | V | V | V | V | **Implemented/Partial** — authenticated access exists; report approval/publishing permissions are not separated |
| Export auditable final regulatory report | — | A | V | A | **Gap** — draft versus final generation exists, but approval/sign-off roles are not enforced |
| Create site | — | M | — | M | **Implemented** — `admin` and `super_admin` only, with plan limit |
| Delete site and associated data | — | M | — | M | **Implemented**, but high-risk deletion needs explicit confirmation, audit logging, and preferably soft-delete/retention |
| Configure asset type, equipment, checklist, lab parameters, and maintenance schedule | — | M | V | M | **Gap** — required by the guide; asset/maintenance configuration module is not present |
| View corrective actions | V | V | V | V | **Gap** — alert protocols exist, but persisted corrective-action workflow is not present |
| Create/update assigned corrective actions | A | A | — | A | **Gap** — guide assigns execution to Site Supervisors and oversight to Managers |
| Approve/close corrective actions | — | M | V | M | **Gap** — should include owner, due date, evidence, approval, and immutable audit history |
| View chemical and consumable stock | V | V | V | V | **Gap** — live inventory module is not present |
| Record chemical usage against a site/asset/task | A | A | — | A | **Gap** — should atomically deduct stock and preserve batch/expiry traceability |
| Receive low-stock and expiry alerts | V | V | V | V | **Gap** — thresholds and inventory alerts are not present |
| Receive/adjust/transfer inventory | — | M | V | M | **Gap** — recommend Manager/Admin control; Site Supervisor may submit a request but should not adjust stock balances directly |
| Configure items, batch numbers, expiry dates, storage locations, costs, and reorder thresholds | — | M | V | M | **Gap** — master-data and stock-control permissions required |
| View site/project chemical consumption | V | V | V | V | **Gap** — operator sees assigned-site usage; higher roles receive aggregated views |
| View monthly chemical expenditure | — | V | V | V | **Gap** — financial visibility begins at Manager tier |
| View organization-wide inventory valuation | — | — | V | V | **Gap** — guide identifies this as a General Manager/Executive KPI |
| View operational KPIs for assigned sites | V | V | V | V | **Partial** — some compliance indicators exist; task completion and dosing accuracy do not |
| View per-project status, risks, outstanding actions, resolution time, and stock alerts | — | V | V | V | **Partial/Gap** — project dashboard exists, but action, inventory, and resolution-time data are absent |
| View portfolio KPIs, trends, expenditure, and asset turnover | — | — | V | V | **Partial/Gap** — portfolio dashboard exists; financial/inventory KPIs are absent |
| View organization compliance, regulatory risk trends, financial summary, and inventory valuation | — | — | V | V | **Partial/Gap** — executive dashboard exists; full strategic dataset is absent |
| Run digital-twin diagnoses and simulations | A | A | V | A | **Partial** — science endpoints exist; explicit role policy is not enforced |
| View organization users | — | M | — | M | **Implemented** — `admin` and `super_admin` only |
| Invite Site Supervisor, Manager, or General Manager | — | M | — | M | **Implemented** — both administrative roles can invite non-executive roles |
| Assign/change non-executive roles | — | M | — | M | **Implemented** — self-role changes are blocked |
| Grant Executive Management role | — | — | — | M | **Implemented** — `super_admin` only |
| Remove non-executive users | — | M | — | M | **Implemented** |
| Remove an Executive Management user | — | — | — | M | **Implemented** — another `super_admin` only; self-removal is blocked |
| View subscription and site allowance | — | V | — | V | **Partial** — backend returns billing status to every authenticated role, while the frontend shows billing only to admins |
| Start checkout, open billing portal, or cancel subscription | — | M | — | M | **Implemented** — `admin` and `super_admin` only |
| Configure organization/business-unit structure | — | — | V | M | **Gap** — organization exists, but business units and delegated hierarchy do not |
| View security/audit log | — | V | V | V | **Gap** — required for traceability and regulatory evidence |
| Configure roles and permission bundles | — | — | — | M | **Gap** — roles are currently hard-coded; recommended only after stable atomic permissions are introduced |

## Recommended atomic permission catalogue

These stable permission keys can replace scattered role-name checks. Roles should receive bundles of these keys, with separate data-scope rules.

| Permission key | Purpose |
|---|---|
| `sites.read` | List and view sites within effective scope |
| `sites.create` | Create a site/asset container |
| `sites.update` | Edit site metadata and configuration |
| `sites.delete` | Delete/retire a site |
| `readings.read` | View laboratory and field readings |
| `readings.create` | Record or upload readings |
| `readings.overwrite` | Replace an existing reporting-period reading |
| `reports.read` | View compliance reports |
| `reports.generate_draft` | Generate draft reports |
| `reports.approve_final` | Approve/finalize regulatory reports |
| `sludge.read` | View sludge surveys |
| `sludge.write` | Create/update sludge surveys |
| `sludge.delete` | Delete sludge surveys |
| `requests.read` | View lab/data requests |
| `requests.create` | Raise requests |
| `requests.fulfil` | Mark requests fulfilled |
| `actions.read` | View corrective actions |
| `actions.create` | Create/assign corrective actions |
| `actions.update` | Record work, evidence, and progress |
| `actions.close` | Approve closure |
| `inventory.read` | View scoped stock and consumables |
| `inventory.consume` | Record usage against an operation |
| `inventory.receive` | Receive stock into a location |
| `inventory.transfer` | Transfer stock between locations |
| `inventory.adjust` | Correct stock balances with reason/audit trail |
| `inventory.configure` | Manage items, batches, costs, expiry, and thresholds |
| `inventory.valuation.read` | View inventory financial valuation |
| `assets.read` | View asset/equipment details |
| `assets.configure` | Configure asset types, equipment, checklists, and schedules |
| `science.read` | View forecasts, diagnoses, and recommendations |
| `science.simulate` | Run digital-twin scenarios |
| `analytics.site.read` | View site operational KPIs |
| `analytics.project.read` | View project/contract KPIs |
| `analytics.portfolio.read` | View portfolio/business-unit KPIs |
| `analytics.executive.read` | View organization-wide strategic and financial KPIs |
| `users.read` | List organization users |
| `users.invite` | Invite users into allowed scopes/roles |
| `users.role.assign` | Assign non-executive roles |
| `users.executive.assign` | Grant Executive Management role |
| `users.remove` | Remove organization membership |
| `billing.read` | View subscription and usage |
| `billing.manage` | Purchase, change, or cancel a subscription |
| `organization.configure` | Manage organization and business-unit structure |
| `audit.read` | View security and operational audit events |
| `permissions.configure` | Maintain custom role bundles, if enabled later |

## Required scope dimensions

Every authorization decision should combine an atomic permission with an effective scope:

| Scope dimension | Examples | Required behavior |
|---|---|---|
| Organization | Tenant/organization ID | Mandatory isolation boundary for every persisted query |
| Business unit | Division or operating company | Executive/General Manager aggregation and delegated oversight |
| Project/contract | Client contract or managed portfolio | Project Manager authority boundary |
| Site | Lagoon, lake, pond, or water feature | Site Supervisor assignment boundary |
| Asset | Pump, filter, dosing system, or water body | Maintenance, chemical usage, and cost attribution boundary |
| Inventory location | Warehouse, vehicle, or site store | Stock visibility and transaction authority boundary |

## Priority authorization gaps

1. Add user-to-site and user-to-project assignments and enforce them in every backend query.
2. Centralize authorization in a permission dependency/service instead of inline role string checks.
3. Explicitly role-protect extraction, simulation, reporting finalization, and billing-status endpoints.
4. Add corrective-action, inventory, asset configuration, and audit-log data models before exposing their permissions.
5. Add immutable audit events for destructive actions, role changes, report approval, stock adjustments, and billing changes.
6. Align frontend visibility with backend authorization, but treat the backend as the source of truth.
