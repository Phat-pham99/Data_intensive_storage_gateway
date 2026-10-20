# Smart Data Control Plane

A production-inspired reference project for application-aware object lifecycle governance. The target system uses PostgreSQL to store searchable business metadata and durable intent, executes archive and restore operations against S3-compatible storage, and reconciles catalog state with actual object bytes.

**The control plane decides. Object storage executes. The reconciler verifies.**

**Current status: foundation only.** The repository contains infrastructure, models, migrations, a Celery bootstrap, and foundation tests. Upload, policy evaluation, archive/restore, reconciliation, and benchmarks are planned, not demonstrated capabilities. This is not a production-ready service.

The authoritative scope, reliability contract, and exit criteria are in [PLAN.md](PLAN.md).

## Problem and Evaluation

Native storage lifecycle rules are useful for storage-level conditions. Application-aware decisions may also require workflow completion, application access history, legal holds, and remaining retention. A separate metadata catalog enables those decisions but introduces synchronization and operational costs.

**Engineering question:** Under what workload and failure conditions does an application-aware metadata control plane justify its additional consistency and operational overhead?

The core evaluation will test:

- Whether selective indexed discovery justifies catalog maintenance, using equivalent-result baselines and measured write/index overhead.
- Whether durable intent, idempotent execution, and reconciliation recover from specified interruptions without deleting the last verified copy.

Negative results and limitations belong in the report. Cost modeling is a deferred extension, not evidence of measured financial savings.

## Current Implementation and Target

| Area | Existing foundation | Core-release target |
| --- | --- | --- |
| API | FastAPI service metadata and health endpoints | Verified upload/download, metadata discovery, lifecycle requests, operation status |
| Persistence | PostgreSQL models and initial Alembic migration | Desired/observed state, immutable versions, durable operations, outbox, audit and findings |
| Messaging | Celery with Redis; health task | RabbitMQ, confirmed publication, idempotent worker, bounded retries and dead-letter handling |
| Storage | S3 configuration fields; no MinIO Compose service | MinIO staging namespace and private active/archive locations |
| Policies | Model foundation | One seeded, deterministic, versioned policy with acceptance/rejection reasons |
| Recovery | No lifecycle recovery workflow yet | Bounded reconciliation and documented failure-injection results |
| Evidence | Configuration, enum/state-transition, and health test files | Real-service integration tests, recovery matrix, reproducible discovery benchmark |

Milestone 1 migrates Redis to RabbitMQ and adds MinIO. The target will not maintain two broker paths, and PostgreSQL will be authoritative for operation status rather than a Celery result backend.

## Target Architecture

```text
Client --HTTP--> FastAPI --transactions--> PostgreSQL
  |                                         |
  +--presigned upload--> MinIO staging       +-- operations + outbox
                                            |
                                      outbox dispatcher
                                            |
                                         RabbitMQ
                                            |
                                     Celery worker
                                      /          \
                               MinIO active   MinIO archive

Reconciler compares catalog intent, operation progress, and storage facts.
```

This diagram describes the target, not the currently running Compose stack. Keep the existing single-codebase layout; domain policy and transition rules remain independent of adapters.

### Planned reliability guarantees and limits

- Persist state changes, operation intent, audit events, and outbox messages in one PostgreSQL transaction. Expect at-least-once delivery, not exactly-once execution.
- Bind each operation to an immutable object version and checksum. Reject conflicting reuse of an idempotency key.
- Serialize mutations per object using database constraints and session advisory locks. Begin with one execution worker at concurrency 1; live takeover and distributed fencing are deferred.
- Verify actual destination size and SHA-256 before deleting an archive source or declaring success. Verification reads stored bytes; it is not a zero-payload-through-worker design.
- Restore returns the object to `ACTIVE` and intentionally retains the archive copy. Reconciliation must distinguish that replica from unexpected duplication.
- Persist attempts and bounded retry deadlines; preserve exhausted failures and diagnostic dead-letter evidence.
- Record discrepancies and repair only evidence-backed, authorized cases. Destructive ambiguity requires manual review.

Worker timeout alone does not establish exclusive ownership. The core assumes controlled single-worker restart, settled in-flight requests, and bounded storage timeouts. See the full [reliability contract](PLAN.md#4-reliability-contract) before implementing recovery.

## Run the Existing Foundation

Prerequisites: Docker with Docker Compose. Local development additionally requires Python 3.12+; `uv` is optional.

```bash
cp .env.example .env
docker compose up --build
```

The current Compose configuration starts PostgreSQL 16, Redis 7, FastAPI, and a Celery worker with the health task registered. It does **not** provide MinIO, RabbitMQ, or a working lifecycle demonstration. The API container applies migrations at startup.

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

OpenAPI documentation: <http://localhost:8000/docs>. Readiness currently checks PostgreSQL and Redis; it is not evidence of storage or lifecycle readiness.

Treat this foundation as a trusted local development environment only. The current Compose file publishes service ports without loopback-only binding; restrict network access before starting it. Loopback binding and least-privilege storage permissions are planned baseline work, not existing protections.

### Current configuration

See [.env.example](.env.example) and [app/config.py](app/config.py). Keep real secrets outside Git.

| Variable | Current purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection URL |
| `REDIS_URL` | Default Celery broker/backend and current readiness dependency |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Optional Celery URL overrides; readiness still checks Redis |
| `S3_REGION`, `S3_BUCKET`, `S3_ENDPOINT_URL` | Storage configuration fields; workflows are not implemented |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Optional storage credentials; use local synthetic resources only |
| `ADMIN_API_KEY` | Configuration field only; no admin endpoint enforcement is implemented |

Do not interpret configuration fields as evidence that their associated features exist.

## API Status

Currently implemented:

```text
GET /                 Service metadata
GET /health           Process liveness
GET /health/ready     PostgreSQL and Redis readiness
```

The planned core API adds upload initiation/completion, object lookup and cursor-paginated discovery, download, application-access recording, archive/restore requests, job status, an admin retry endpoint, and metrics. These routes are specified in [PLAN.md](PLAN.md#6-deterministic-policy-and-minimal-interfaces); they are not available yet.

Policy evaluation, outbox/retry dispatch, reconciliation, and finding inspection will start as bounded CLI commands rather than a large admin API.

## Delivery Milestones

All four consolidated milestones remain planned. The existing foundation is a starting point, not a completed Milestone 1.

| Milestone | Required exit evidence | Status |
| --- | --- | --- |
| 1. Verified catalog round trip | RabbitMQ/MinIO setup; upload, checksum verification, query, download, duplicate handling, and restart persistence | Planned |
| 2. One complete lifecycle | Explainable policy -> archive -> restore; durable intent, safe duplicates, concurrency guards, retry/dead-letter evidence | Planned |
| 3. Recovery and demonstration | Bounded reconciliation, findings, minimal metrics, and documented outcomes for every failure-matrix case | Planned |
| 4. Evaluation and public evidence | Clean-checkout demonstration, fair discovery benchmark, maintenance overhead, and reproducible results report | Planned |

At each milestone, update implemented/tested/planned status, run the full available suite and required CI gates, and record commands, environment, outcomes, and limitations. Blocked integration tests do not satisfy exit criteria.

**Core completion:** A new user can reproduce upload -> evaluate -> archive -> restore -> verify, recover from specified injected failures, and run a modest-scale benchmark.

## Development and Checks

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
source .venv/bin/activate

ruff check .
ruff format --check .
pytest

# Requires the configured PostgreSQL instance.
alembic upgrade head
```

Current tests cover configuration, enums/state transitions, and health behavior. They do not establish end-to-end lifecycle correctness.

The existing [CI workflow](.github/workflows/ci.yml) configures lint, format checks, migration upgrade, and tests with coverage on pull requests and pushes to `main` or `feature/**`. This describes configured checks, not a claim that the latest run passed. Real-service lifecycle integration tests, failure injection, and dependency/container scanning remain planned gates.

## Evidence and Limitations

The evaluation will compare indexed queries with a catalog baseline without the candidate index and with equivalent namespace enumeration at the same physical population. Enumeration must obtain equivalent business metadata, not merely list keys. Report request counts, selectivity, cache conditions, repeated latency measurements, and query plans alongside ingestion, verification, and reconciliation overhead.

Begin with 100K logical catalog rows and a separately declared practical population of real small objects. Never present logical row counts as physically stored or processed capacity. No performance or recovery results are claimed here yet.

Two MinIO buckets demonstrate lifecycle orchestration, not Glacier retrieval behavior or actual archival pricing. Optional economic scenarios must include retained copies, requests, transitions, retrieval, and minimum-duration assumptions, and must be labeled as modeled projections.

Deferred work includes Grafana, rich policy administration, bulk folder operations, cost estimation, larger logical experiments, multi-worker scaling, real AWS integration, enterprise identity, and separately justified recommendation-only ML. Kubernetes, a custom frontend, and multi-region replication are outside the core scope.

Use synthetic/public material only. Owner metadata is not authorization, and the service must not be exposed to untrusted users without authentication and object-level access controls. Neither production readiness nor cross-system atomicity is claimed.

## License

[MIT](LICENSE)