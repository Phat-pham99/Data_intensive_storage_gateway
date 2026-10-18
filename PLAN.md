# Portfolio Project: Explainable Data Lifecycle Control Plane

**Author:** Phạm Hồng Phát
**Version:** 4.0 (review-patched edition)
**Purpose:** Portfolio artifact demonstrating Data-Intensive Intelligent Software Systems engineering.
**Classification:** Clean-room, public-safe, non-confidential.
**Status:** SPEC FROZEN after this revision. Changes require a written amendment.

---

## 1. Executive Summary & Goal Alignment

This project is a compact, production-grade **Data Lifecycle Control Plane**. It manages the lifecycle of objects stored in AWS S3, moving beyond simple CRUD operations to demonstrate asynchronous state management, explainable decision-making, and scalable batch orchestration.

### Theme Alignment

| Theme | Implementation in this Project |
| :--- | :--- |
| **Data-Intensive** | Manages object metadata, access patterns, storage tiers, and bulk folder operations. Decouples control plane from data plane so no payload ever traverses the API. |
| **Intelligent Systems** | Explainable, cost-aware policy engine scoring object coldness, size, access risk, and retrieval-cost penalties; what-if simulation; optional scheduled enforcement. |
| **Dependable Systems** | Strict state machine, request- and task-level idempotency, bounded retries, additional-checksum verification, audit logging, single-writer storage-class ownership. |
| **Software Engineering** | FastAPI, Celery (+ beat), PostgreSQL, Redis, AWS S3, Docker Compose, Alembic, pytest, Ruff, GitHub Actions. Phased delivery with exit criteria. |

---

## 2. Clean-Room Declaration

This project is an independent public demonstration inspired by general production experience with enterprise storage and data-lifecycle systems.

* **Strictly Prohibited:** proprietary employer code, employer names in the repo, internal service names, real bucket names, account IDs, business metrics, production data, internal diagrams, private dashboard screenshots.
* **Allowed Wording:** "Inspired by general production experience operating enterprise data-lifecycle systems."

---

## 3. Architecture & Technology Stack

### 3.1 High-Level Architecture

Strict **Control Plane / Data Plane separation**. The FastAPI service never streams object payloads.

```text
[ Client ]
   |  (1) POST /v1/uploads/initiate          (2) PUT bytes directly (presigned)
   |------------------------------------------+------------------+
   v                                                             v
[ FastAPI Control Plane ] <--> [ PostgreSQL ]            [ AWS S3 ]
   |  enqueue / observe          (single source           ^     ^
   v                              of truth)               |     |
[ Redis (broker) ] <--> [ Celery Worker ] -----------------+     |
                          (only writer of storage class          |
                           in worker-enforcement mode)           |
[ Celery Beat ] -----------> scheduled reconcile / expiry sweeps |
                                                                   |
[ Client ] <--------- presigned GET (download) ------------------+
```

Edges that matter:
* Client ↔ S3 directly for bytes (presigned PUT/GET).
* Celery Worker ↔ S3 for server-side `CopyObject` / `RestoreObject` (metadata-class operations, no payload through the worker).
* Celery Worker/Beat ↔ Redis (broker) and ↔ PostgreSQL (state).
* **PostgreSQL is the only source of truth for business state.** The Celery result backend is never read for object or job state.

### 3.2 Technology Stack

* **API & Logic:** Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic.
* **Async:** Celery worker + Celery beat, Redis broker.
* **Database:** PostgreSQL.
* **Storage:** AWS S3 via boto3 (additional-checksum enabled).
* **Infra/Quality:** Docker Compose, pytest, Ruff, GitHub Actions, moto/LocalStack for tests.

### 3.3 Enforcement Mode Matrix (single-writer principle)

Exactly one component owns storage-class mutation at a time:

| Mode | Storage-class writer | `POST /v1/admin/policies/apply` behavior | Worker/reconcile role |
| :--- | :--- | :--- | :--- |
| `worker` (default, demo) | Celery worker (`CopyObject`) | **Projection only** — returns and stores the lifecycle XML/JSON it *would* apply; no AWS call | Enforcer |
| `aws_lifecycle` | AWS S3 Lifecycle (async) | Real `put_bucket_lifecycle_configuration` | Read-only observer: reconcile scan HEADs objects and syncs Postgres to observed class |

Configured via `ENFORCEMENT_MODE` env var. Mixing writers is prohibited by design.

---

## 4. Core Domain Model

### 4.1 Object

```text
id, bucket, key, prefix, filename, size_bytes
checksum_sha256, checksum_algorithm   # verified via S3 additional checksums
etag                                   # informational only; never compared to SHA-256
storage_class      # STANDARD | STANDARD_IA | GLACIER_IR | GLACIER | DEEP_ARCHIVE
lifecycle_state    # see §8
access_count, last_accessed_at
restore_expiry_at  # set when a temporary Glacier restore completes; NULL otherwise
is_synthetic       # TRUE for seeder-created demo rows (honesty flag)
version            # optimistic locking
created_at, updated_at
```

Notes:
* `GLACIER_IR` is instantly retrievable: archived IR objects remain downloadable and use the fast restore path (§5, §8).
* `etag` is MD5 (single-part) or md5-of-md5s (multipart); it is **never** used as the integrity proof. Integrity proof is `ChecksumSHA256`.

### 4.2 Job

```text
id, job_type, status, object_id
parent_job_id        # FK → Job (folder coordinator) or FolderJob; REQUIRED for fan-out children
idempotency_key      # UNIQUE index; request-scoped dedupe
celery_task_id, attempt_count, max_attempts
error_code, error_message, correlation_id
created_at, started_at, finished_at
```

* Celery tasks are additionally idempotent by `(object_id, target_state)` so broker replays are safe.
* Folder aggregates are **recomputed**, never incremented: `COUNT(*) GROUP BY status` over children with `parent_job_id = <coordinator>`.

### 4.3 FolderJob

```text
id, prefix, status, total_objects
completed_objects, failed_objects, skipped_objects   # cached; recomputed on read
created_at, finished_at
```

### 4.4 Policy

JSONB configuration stored in Postgres (data, not code):

```text
id, name, version, enabled, description
weights_json, thresholds_json
cost_assumptions_json   # per-tier $/GB-month, retrieval $/GB, minimum storage
                        # duration (days), request pricing → retrieval-fee and
                        # early-deletion penalties enter the score
enforcement_json        # { "mode": "manual" | "scheduled", "beat_cron": "0 3 * * *" }
s3_lifecycle_projection_json
created_at, updated_at, applied_at
```

### 4.5 AuditEvent

Immutable log: `id, object_id, job_id, previous_state, new_state, event_type, actor, reason, policy_version, correlation_id, created_at`. Written in the same transaction as the state change wherever possible.

---

## 5. API Design (Control Plane)

### 5.1 Public endpoints

**`POST /v1/uploads/initiate`** (`Idempotency-Key` required)
* Creates a `CREATED` object record.
* Returns a **presigned PUT URL** signed with conditions: `Content-Length-Range` (≤ 100 MB, single-part), exact `Content-Type`, and required `x-amz-checksum-sha256` header.
* Zero payload touches the API.

**`POST /v1/uploads/{object_id}/complete`** (`Idempotency-Key` required)
* `HeadObject`; verify size and compare returned `ChecksumSHA256` to the client-declared `checksum_sha256`.
* `HeadObject` 404 (client never uploaded) → `409` with reason `upload_not_found`; object remains `CREATED` until expiry sweep.
* On success: `CREATED → ACTIVE`, audit event, immediate policy evaluation returned.

**`GET /v1/objects/{object_id}/download`**
* `ACTIVE` / `RESTORED` → presigned GET; increment `access_count`, update `last_accessed_at`.
* `ARCHIVED` + `GLACIER_IR` → presigned GET allowed (instant retrieval); audit event `direct_ir_read`.
* `ARCHIVED` + `GLACIER` / `DEEP_ARCHIVE` → `409 Conflict` with restore hint and estimated restore window.
* Known limitation (documented): `access_count` measures issued download URLs, not confirmed byte transfers.

**`POST /v1/objects/{object_id}/archive`** and **`POST /v1/objects/{object_id}/restore`** (`Idempotency-Key` required)
* Validate state; create `Job`; transition to `*_REQUESTED`; enqueue; return `202 Accepted`.
* Restore semantics by class:
  * `GLACIER_IR` — **fast path**: synchronous server-side `CopyObject` back to `STANDARD`, state `ARCHIVED → ACTIVE`, job completes in seconds.
  * `GLACIER` / `DEEP_ARCHIVE` — **slow path**: `RestoreObject`, poll until `ongoing-request="false"`, set `restore_expiry_at`, state `RESTORED`; optional copy-back transitions `RESTORED → ACTIVE`. A scheduled sweep returns `RESTORED` objects past `restore_expiry_at` to `ARCHIVED`.

**`GET /v1/jobs/{job_id}`**
* Status, attempts, errors; for folder coordinators, aggregates are recomputed from children on every read.

**`POST /v1/jobs/{job_id}/retry`**
* Re-drives a `FAILED` job back to its prior requested state; manual and inspectable.

### 5.2 Batch & admin endpoints

All `/v1/admin/*` require a static `X-Admin-Key` header from env (no JWT; an auth platform is out of scope). Unauthenticated → `403`.

**`POST /v1/folders/archive`**
* Enumerate prefix with S3 pagination, **filtering to `lifecycle_state = ACTIVE` only**.
* Create coordinator `Job` + `FolderJob`; chunk keys (default 500/chunk, configurable); dispatch a Celery `group` of chunk tasks; children carry `parent_job_id`.
* Celery `chord` callback recomputes aggregates; partial failures tolerated and reported.

**`PUT /v1/admin/policies`** — versioned policy update (weights, thresholds, cost model, enforcement).
**`POST /v1/admin/policies/simulate`** — what-if evaluation over existing objects; performs **no writes**; returns per-object recommendations, projected tiered vs active-only cost, and `not_demo_restorable` flags for `GLACIER`/`DEEP_ARCHIVE` targets.
**`POST /v1/admin/policies/apply`** — behavior per enforcement mode (§3.3): projection-only in `worker` mode; real `put_bucket_lifecycle_configuration` in `aws_lifecycle` mode.

### 5.3 Scheduled tasks (Celery beat)

* `reconcile_lifecycle` — when `enforcement.mode = scheduled`: scan `ACTIVE` objects, evaluate policy, enqueue archive jobs for eligible ones. In `aws_lifecycle` mode the same scan is read-only and syncs observed storage classes into Postgres.
* `sweep_expired_uploads` — mark `CREATED` objects older than the presigned TTL as `EXPIRED`.
* `sweep_restore_expiry` — return `RESTORED` objects past `restore_expiry_at` to `ARCHIVED`.

---

## 6. The "Intelligent" Layer: Explainable Policy Engine

### 6.1 Scoring logic

```text
score = (w_age * age_signal)
      + (w_cold * coldness_signal)
      + (w_size * size_signal)
      - (w_risk * access_risk)
      - (w_cost * retrieval_cost_penalty)
```

`retrieval_cost_penalty` accounts for per-GB retrieval fees and minimum-storage-duration early-deletion charges, so cold-but-frequently-restored objects are not over-tiered. Recurring-access patterns (e.g., a monthly batch consumer) raise `access_risk` and exempt the object.

### 6.2 Explainable output

```json
{
  "recommended_tier": "STANDARD_IA",
  "score": 0.72,
  "components": { "age": 0.30, "coldness": 0.25, "size": 0.17, "risk_penalty": -0.00, "cost_penalty": -0.00 },
  "reasons": [
    "Object has not been accessed for 45 days (threshold: 30)",
    "Object size (50 MB) exceeds minimum tiering threshold (128 KB)",
    "Restore latency requirement is compatible with IA"
  ]
}
```

Deterministic, versioned, and auditable: every recommendation records `policy_version`.

---

## 7. Data Plane Mechanics & Scalability

### 7.1 Server-side transitions

Archiving never downloads and re-uploads. The worker issues `CopyObject` (same key or archive prefix per configuration) with a changed `StorageClass`, then verifies via `HeadObject` before state transition. Source removal (if configured) happens only after destination verification.

### 7.2 Folder fan-out (replacing S3 Batch Operations)

1. Paginated prefix enumeration, `ACTIVE` filter.
2. Coordinator chunks keys (500/chunk) and dispatches a Celery `group`.
3. Workers execute with bounded retries and exponential backoff on `503 Slow Down`.
4. `chord` callback recomputes `FolderJob` aggregates from child `Job` rows (`parent_job_id`), never increments counters.

---

## 8. Reliability & State Machine

### 8.1 States

```text
CREATED, ACTIVE, ARCHIVE_REQUESTED, ARCHIVING, ARCHIVED,
RESTORE_REQUESTED, RESTORING, RESTORED, EXPIRED, FAILED
```

### 8.2 Allowed transitions

```python
ALLOWED_TRANSITIONS = {
    "CREATED":           {"ACTIVE", "EXPIRED"},
    "ACTIVE":            {"ARCHIVE_REQUESTED"},
    "ARCHIVE_REQUESTED": {"ARCHIVING", "FAILED"},
    "ARCHIVING":         {"ARCHIVED", "FAILED"},
    "ARCHIVED":          {"RESTORE_REQUESTED"},          # + direct IR download allowed
    "RESTORE_REQUESTED": {"RESTORING", "ACTIVE", "FAILED"},  # ACTIVE = GLACIER_IR fast path
    "RESTORING":         {"RESTORED", "FAILED"},
    "RESTORED":          {"ACTIVE", "ARCHIVED"},         # ARCHIVED = restore-expiry sweep
    "FAILED":            {"ARCHIVE_REQUESTED", "RESTORE_REQUESTED", "ACTIVE"},
}
```

Rules:
* All transitions validated; conflicting commands rejected while a non-terminal job exists.
* Optimistic locking, spelled out once: `UPDATE objects SET state=:new, version=version+1 WHERE id=:id AND version=:v`; `rowcount == 0` → re-read and reject or retry.
* Idempotency enforced by **unique index** on `jobs.idempotency_key` with `ON CONFLICT` returning the existing job; no check-then-insert.
* Bounded retries with exponential backoff; retry exhaustion → `FAILED`, inspectable and re-drivable.
* Worker restart never corrupts state: Postgres is authoritative; in-flight tasks are replay-safe by `(object_id, target_state)`.

---

## 9. Phased Delivery Plan

Phase 1 is **Complete**. New fields introduced by this revision (`jobs.parent_job_id`, `objects.restore_expiry_at`, `objects.is_synthetic`, `objects.checksum_algorithm`) ship as **reversible migration `0002_review_patches`** in Phase 2 with no `alembic check` drift.

| Phase | Deliverable | Depends On | Status |
| :--- | :--- | :--- | :--- |
| 1 — Foundation | Containerized stack, schema, migrations, CI | — | Complete |
| 2 — Control Plane | Presigned upload/download, checksum verification, sweeps | 1 | Planned |
| 3 — Async Core | Archive/restore jobs, state machine, idempotency, IR fast path, slow path | 2 | Planned |
| 4 — Intelligence | Policy engine, simulation, seeder | 3 | Planned |
| 5 — Scale & Admin | Folder fan-out, enforcement modes, beat tasks, admin auth, metrics | 4 | Planned |

### 9.1 Phase 2 — Control Plane (patched)
* Presigned PUT with `Content-Length-Range`, content-type, and required `x-amz-checksum-sha256` conditions.
* `complete` verifies `HeadObject` size + `ChecksumSHA256`; handles `upload_not_found`.
* Download rules per §5.1 including the `ARCHIVED + GLACIER_IR` allowance.
* `sweep_expired_uploads` task; `CREATED → EXPIRED`.
* Migration `0002_review_patches`.
* Exit criteria: upload→complete→download round trip against moto/LocalStack; checksum mismatch rejected; stale uploads expire; every transition test-covered.

### 9.2 Phase 3 — Async Core (patched)
* Archive/restore endpoints, jobs, `202` semantics, `GET /v1/jobs/{id}`, retry endpoint.
* Server-side `CopyObject` transitions; GLACIER_IR fast path; GLACIER/DEEP_ARCHIVE slow path with `RestoreObject` polling and `restore_expiry_at`.
* `parent_job_id` present on all jobs; unique idempotency index; optimistic locking.
* Exit criteria: duplicate/concurrent commands deduplicated; transient failures retry then `FAILED`; slow path tested with mocked `RestoreObject`; state machine unit-covered for every allowed and denied transition.

### 9.3 Phase 4 — Intelligence (patched)
* Scoring function with retrieval-cost penalty; explainable output; versioned policies.
* `POST /v1/admin/policies/simulate` (no writes; `not_demo_restorable` flags).
* **Synthetic seeder** (§10) so simulation has a scored population on day one.
* Exit criteria: recommendations deterministic and fully explained; cost assumptions measurably change outcomes; simulation performs zero writes.

### 9.4 Phase 5 — Scale & Admin (patched)
* Folder fan-out with `ACTIVE` filter, chunking, chord recompute.
* Enforcement mode matrix (§3.3); `policies/apply` projection vs real apply.
* Beat tasks: `reconcile_lifecycle`, `sweep_restore_expiry` (beat service added to compose).
* `X-Admin-Key` auth on `/v1/admin/*`; Prometheus metrics; structured logs.
* Exit criteria: folder archive reports recomputed aggregates and tolerates partial failure; unauthenticated admin → `403`; projection mode makes zero AWS mutation calls.

### 9.5 Cross-phase quality gates
Ruff + tests green in CI; reversible migrations with no drift; no secrets committed; endpoints documented in OpenAPI and test-covered; Postgres remains the only source of truth.

---

## 10. Synthetic Workload & Demo Enablers

**`scripts/seed_workload.py`** — metadata-only by default:
`--objects N --cold-ratio r --seed s --backdate-max-days D [--with-bytes]`
* Creates `ACTIVE` rows with synthetic sizes, backdated `created_at` / `last_accessed_at`, synthetic access counts, and `is_synthetic = TRUE`.
* Profiles: `hot`, `mixed`, `cold`.
* Makes policy simulation and the reconcile loop demonstrable without waiting 30 days and without uploading bytes.

**`scripts/generate_workload.py`** — small real files for the presigned round-trip demo.
Physical bytes processed and logical bytes represented are reported separately; no unsupported scale claims.

---

## 11. Observability (minimal, deliberate)

Metrics: `operations_total{type,status}`, `operation_retries_total{type}`, `checksum_failures_total`, `policy_recommendations_total{tier}`, `folder_job_objects_total{status}`, `restore_verified_total`, `storage_class_transitions_total{from,to}`.
Structured logs: `service, object_id, job_id, correlation_id, state, event, attempt, error`.
One dashboard optional; not a completion gate.

---

## 12. Testing

* **Unit:** state machine (including IR fast path, expiry sweep transitions, denied transitions), policy determinism and explanations, idempotency conflict handling, cost model with minimum-duration penalties, checksum comparison logic.
* **Integration (moto/LocalStack):** presigned initiate→complete→download; archive/restore happy paths; duplicate command; injected transient failure → retry → success; checksum mismatch; folder fan-out with `task_always_eager`; simulation write-freedom.
* **CI:** Ruff, tests, migrations up/down, secret scan.

---

## 13. Definition of Success & CV Integration

Completion checklist:
* [ ] Compose stack healthy; readiness reports DB + Redis ok. *(P1)*
* [ ] Presigned uploads with checksum conditions; zero payload through API. *(P2)*
* [ ] Server-side transitions; zero payload through worker. *(P3)*
* [ ] GLACIER_IR objects downloadable while archived and restorable in seconds. *(P3)*
* [ ] Idempotency via unique index; replays safe. *(P3)*
* [ ] Policy engine explains every recommendation; simulation writes nothing. *(P4)*
* [ ] Seeder produces a scored synthetic population. *(P4)*
* [ ] Folder fan-out recomputes aggregates; partial failure tolerated. *(P5)*
* [ ] Enforcement modes enforce single-writer ownership. *(P5)*
* [ ] Tests and CI green. *(all)*

CV entry:
> **Explainable Data Lifecycle Control Plane** | Python, FastAPI, Celery, PostgreSQL, AWS S3
> * Architected a control-plane/data-plane separated storage lifecycle system: presigned transfers keep payloads out of the API while Celery workers execute server-side S3 storage-class transitions.
> * Engineered chunked fan-out batch archival with recomputed aggregate progress, request- and task-level idempotency, and bounded retries.
> * Designed an explainable, cost-aware tiering policy engine with retrieval-fee penalties, what-if simulation, and single-writer enforcement modes against AWS S3 lifecycle configuration.

---

## 14. Changelog v3 → v4 (review patches)

* **F1** GLACIER_IR terminal-state trap closed: archived IR objects are downloadable and use a synchronous fast restore path.
* **F2** Integrity proof corrected: S3 additional checksums (`ChecksumSHA256`) replace ETag comparison; single-part cap declared.
* **F3** `parent_job_id` added; folder aggregates recomputed from children, never incremented.
* **F4** Single-writer principle: enforcement mode matrix; lifecycle apply is projection-only in worker mode.
* **F5** Enforcement loop specified: `reconcile_lifecycle` beat task (or explicit manual-only mode).
* **F6** Metadata-only synthetic seeder with backdating and `is_synthetic` honesty flag.
* **F7** Glacier slow path specified: `RestoreObject` polling, `restore_expiry_at`, expiry sweep; demo defaults avoid non-instant tiers.
* Minor: stale-upload sweep; presigned PUT conditions; unique idempotency index; `ACTIVE`-only fan-out filter; optimistic-lock pattern spelled out; Postgres as sole source of truth; JWT mention removed; diagram edges corrected.

**Freeze notice:** this spec is now frozen. Further changes require a written amendment with rationale. Build, do not edit.