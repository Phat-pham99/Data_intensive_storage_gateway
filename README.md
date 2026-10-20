# Smart Data Control Plane

A production-inspired reference project for application-aware object lifecycle governance. The target system uses PostgreSQL to store searchable business metadata and durable intent, executes archive and restore operations against S3-compatible storage, and reconciles catalog state with actual object bytes.

**The control plane decides. Object storage executes. The reconciler verifies.**

**Storage direction:** The MVP is designed to use MinIO for local development, integration tests, and demonstrations. A future production-ready version should use **Amazon S3 for globally accessed, terabyte-scale object data**.

**Current status: foundation only.** The repository contains infrastructure, models, migrations, a Celery bootstrap, and foundation tests. Upload, policy evaluation, archive/restore, reconciliation, and benchmarks are planned, not demonstrated capabilities. This is not a production-ready service.

The broader scope and exit criteria are in [PLAN.md](PLAN.md). The Redis Pub/Sub design below supersedes that document's older broker-specific messaging descriptions; the plan and runtime implementation have not yet been migrated to this revision.

## Animated Workflow

![Fourteen-step planned workflow showing verified ingestion, policy evaluation, durable database intent, Redis Pub/Sub notifications with database polling, archive, duplicate notification handling, restore, drift detection, and safe repair.](docs/assets/lifecycle-workflow.gif)

This 49-second looping illustration shows the **planned design**, not a recording of implemented behavior. Blue paths carry control and metadata; green paths carry object bytes. The state strip distinguishes desired placement from the last verified observed placement.

For a non-animated description, see the [updated reliability guarantees](#planned-reliability-guarantees-and-limits) below and the storage [failure evidence](PLAN.md#7-reconciliation-and-failure-evidence). Redis Pub/Sub is only a wake-up mechanism; PostgreSQL polling recovers work when notifications are lost.


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
| Messaging | Celery with Redis; health task | Redis Pub/Sub wake-ups, independent PostgreSQL polling, idempotent execution, bounded database-scheduled retries |
| Storage | S3 configuration fields; no MinIO Compose service | MinIO staging namespace and private active/archive locations |
| Policies | Model foundation | One seeded, deterministic, versioned policy with acceptance/rejection reasons |
| Recovery | No lifecycle recovery workflow yet | Bounded reconciliation and documented failure-injection results |
| Evidence | Configuration, enum/state-transition, and health test files | Real-service integration tests, recovery matrix, reproducible discovery benchmark |

The target retains Redis and adds MinIO. Redis Pub/Sub carries ephemeral operation-ID notifications, while PostgreSQL stores durable work, attempts, retry deadlines, and failures. A subscriber and an independent bounded database poller feed one execution worker. This is a planned execution adapter, not Celery's existing Redis queue transport; the current Celery bootstrap does not implement it.

### Storage deployment roadmap

- **MVP:** MinIO provides a reproducible local S3-compatible environment with staging, active, and archive locations. The architecture chart and GIF illustrate this MVP layout.
- **Production target:** Amazon S3 provides the managed object-storage backend for globally distributed users and terabyte-scale datasets. S3 buckets are regional; region selection, data residency, cross-region replication, disaster recovery, and global access latency require explicit design. Replication is not automatic, and multi-region deployment remains outside the MVP.
- **Readiness gate:** Adopting S3 alone does not make the application production-ready. Require authentication and object-level authorization, least-privilege IAM, encryption, real-S3 integration and recovery tests, multipart transfer validation, operational monitoring, and measured control-plane throughput, recovery behavior, and storage/request/data-transfer costs. See the [production storage roadmap](PLAN.md#production-storage-roadmap-after-the-core-release).

## Target Architecture

```mermaid
flowchart TB
      client["Client / Demo CLI"]

      subgraph control["DECIDE | Control plane"]
            api["FastAPI<br/>Validate requests - discover objects - expose status"]
            policy["Policy evaluator<br/>Versioned rules - safety guards - reason codes"]
            catalog[("PostgreSQL<br/>Catalog + desired / observed state<br/>Operations + audit + outbox + findings")]
      end

      subgraph execution["EXECUTE | PostgreSQL-backed work"]
            publisher["Outbox publisher<br/>Best-effort operation-ID notifications"]
            pubsub["Redis Pub/Sub<br/>Ephemeral channel - no replay or acknowledgements"]
            worker["Subscriber + DB poller | one execution worker<br/>Lock - copy - verify - commit"]
            failures["Failure review<br/>Queryable PostgreSQL attempt / failure history"]
      end

      subgraph storage["STORE | MinIO object bytes"]
            staging[("Staging<br/>Bounded, short-lived uploads")]
            active[("Active<br/>Immutable verified versions")]
            archive[("Archive<br/>Retained after restore")]
      end

      reconciler["VERIFY | Reconciler<br/>Bounded inspection - findings - safe recovery"]

      client -->|HTTP requests| api
      client -->|Bounded evaluation command| policy
      api -->|Catalog reads / transactional intent| catalog
      policy -->|Decision + operation + audit + outbox| catalog
      catalog -->|Pending outbox notifications| publisher
      publisher -->|PUBLISH operation ID| pubsub
      pubsub -.->|Wake connected subscriber| worker
      worker -.->|Poll pending / due work even without Redis| catalog
      worker -->|Claim / attempts / outcome / failures| catalog
      catalog -->|Read persisted diagnostics| failures

      client ==>|Presigned upload| staging
      staging ==>|Verify and promote| active
      worker -->|Storage commands + checksum reads| active
      worker -->|Storage commands + checksum reads| archive
      active ==>|Archive: copy, verify, then delete source| archive
      archive ==>|Restore: copy, verify, retain archive| active

      reconciler -.->|Compare intent / record findings / initiate safe work| catalog
      reconciler -.->|Inspect expired or orphaned uploads| staging
      reconciler -.->|Inspect presence + integrity| active
      reconciler -.->|Inspect presence + integrity| archive

      classDef entry fill:#F1F5F7,stroke:#536973,color:#172C34
      classDef decide fill:#EAF3FB,stroke:#1767AB,color:#123D60
      classDef execute fill:#FFF4DC,stroke:#946B12,color:#59400B
      classDef bytes fill:#E8F6EF,stroke:#087C68,color:#125447
      classDef verify fill:#FCEDEB,stroke:#B74138,color:#782F29
      class client entry
      class api,policy,catalog decide
      class publisher,pubsub,worker execute
      class staging,active,archive bytes
      class reconciler,failures verify
      style control fill:#F4F8FC,stroke:#9BBEDA,color:#123D60
      style execution fill:#FFFBF2,stroke:#D6C69D,color:#59400B
      style storage fill:#EFF9F3,stroke:#9ACAB4,color:#125447
```

**Planned architecture, not the current Compose stack.** Solid arrows show control and metadata, thick arrows show object-byte movement, and dotted arrows show notification, polling, and reconciliation paths. The boxes describe logical responsibilities in one codebase, not a separate microservice for every component.

The database transaction ends before publication or storage I/O; there is no cross-system atomic transaction. A successful Redis `PUBLISH` or subscriber count does not prove that a worker received or processed a notification. The outbox records notification attempts, not acknowledged job delivery. Workers poll eligible database operations at startup and at a bounded interval regardless of notification delivery, including during Redis outages.

Storage-to-storage arrows summarize service-controlled transfers: destination bytes must be verified before success, and an archive source is deleted only after verification. Findings and failures stay durable in PostgreSQL; there is no broker-native dead-letter queue. Keep domain rules independent of infrastructure adapters.

### Planned reliability guarantees and limits

- Persist state changes, operation intent, audit events, and outbox notifications in one PostgreSQL transaction. Redis Pub/Sub is at-most-once and has no persistence, acknowledgement, replay, or automatic redelivery.
- Use notifications only to reduce pickup latency. Independently poll pending operations and due retries in bounded indexed batches, including on startup/reconnect. Lost notifications must not strand committed work, and a disconnected Redis subscriber must not block the database polling loop.
- Claim work in PostgreSQL before execution; notification and polling paths use the same per-object ownership and idempotency checks. Repeated publication or polling can rediscover the same operation; completed work is skipped without further storage mutations.
- Bind each operation to an immutable object version and checksum. Reject conflicting reuse of an idempotency key.
- Serialize mutations per object using database constraints and session advisory locks. Begin with one execution worker at concurrency 1; live takeover and distributed fencing are deferred.
- Verify actual destination size and SHA-256 before deleting an archive source or declaring success. Verification reads stored bytes; it is not a zero-payload-through-worker design.
- Restore returns the object to `ACTIVE` and intentionally retains the archive copy. Reconciliation must distinguish that replica from unexpected duplication.
- Persist attempts, bounded retry deadlines, and exhausted failures in PostgreSQL. Database polling, not Pub/Sub, schedules retries. Validate notification payloads, log/count malformed notifications without executing them, and use persisted failure history for admin review and explicit retry rather than assuming a dead-letter queue exists.
- Test subscriber disconnect/reconnect, publication before subscription, Redis restart/outage, duplicate publication, and a successful `PUBLISH` whose notification never reaches execution. Verify recovery from the database and measure the polling latency/load trade-off; fewer technologies does not establish lower cost by itself.
- Record discrepancies and repair only evidence-backed, authorized cases. Destructive ambiguity requires manual review.

Worker timeout alone does not establish exclusive ownership. The core assumes controlled single-worker restart, settled in-flight requests, and bounded storage timeouts. Database polling must not blindly reclaim running work after a timeout; uncertain ownership requires controlled recovery. The storage and ownership rules in the [reliability contract](PLAN.md#4-reliability-contract) still apply, but its older broker-confirmation and dead-letter provisions do not describe this Pub/Sub revision.

## Run the Existing Foundation

Prerequisites: Docker with Docker Compose. Local development additionally requires Python 3.12+; `uv` is optional.

```bash
cp .env.example .env
docker compose up --build
```

The current Compose configuration starts PostgreSQL 16, Redis 7, FastAPI, and a Celery worker with the health task registered. It does **not** provide MinIO, the planned Pub/Sub subscriber/database poller, or a working lifecycle demonstration. The API container applies migrations at startup.

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

Policy evaluation, outbox notification publication, reconciliation, and finding inspection will start as bounded CLI commands rather than a large admin API. The execution adapter will continuously subscribe and independently poll eligible database operations and due retries.

## Delivery Milestones

All four consolidated milestones remain planned. The existing foundation is a starting point, not a completed Milestone 1.

| Milestone | Required exit evidence | Status |
| --- | --- | --- |
| 1. Verified catalog round trip | Existing Redis/PostgreSQL plus MinIO; upload, checksum verification, query, download, duplicate handling, and restart persistence | Planned |
| 2. One complete lifecycle | Explainable policy -> archive -> restore; Pub/Sub wake-ups with database polling, missed-notification recovery, safe duplicates, concurrency guards, persisted retry/failure evidence | Planned |
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

Deferred work includes Grafana, rich policy administration, bulk folder operations, cost estimation, larger logical experiments, multi-worker scaling, the production Amazon S3 deployment, enterprise identity, and separately justified recommendation-only ML. Kubernetes, a custom frontend, and multi-region replication are outside the core scope. Terabyte-scale storage and global access are production design targets, not measured capabilities of this MVP.

Use synthetic/public material only. Owner metadata is not authorization, and the service must not be exposed to untrusted users without authentication and object-level access controls. Neither production readiness nor cross-system atomicity is claimed.

## License

[MIT](LICENSE)