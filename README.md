# Smart Data Control Plane

A production-inspired reference project for application-aware object lifecycle governance. The target system uses PostgreSQL to store searchable business metadata and durable intent, executes archive and restore operations against S3-compatible storage, and reconciles catalog state with actual object bytes.

**The control plane decides. Object storage executes. The reconciler verifies.**

**Storage direction:** The MVP is designed to use MinIO for local development, integration tests, and demonstrations. A future production-ready version should use **Amazon S3 for globally accessed, terabyte-scale object data**.

**Current status: verified catalog ingestion, locally tested.** Upload initiation/completion, streamed SHA-256 verification, metadata discovery, download, access recording, and restart persistence work against PostgreSQL and MinIO. CI/CD gates and gated container publication are configured. Policy evaluation, archive/restore, reconciliation, and benchmarks remain planned. This is not a production-ready service.

The broader scope and exit criteria are in [PLAN.md](PLAN.md). Commands, local verification evidence, and remaining limitations are recorded in [docs/milestone-1.md](docs/milestone-1.md).

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

| Area | Implemented now | Core-release target |
| --- | --- | --- |
| API | Verified upload/download, cursor-paginated discovery, access and health endpoints | Lifecycle requests and operation status |
| Persistence | Immutable content identity, metadata, desired/observed ingestion state, audit; two migrations | Durable operations, outbox, policy versions and findings |
| Messaging | Celery with Redis; health task | Redis Pub/Sub wake-ups, independent PostgreSQL polling, idempotent execution, bounded database-scheduled retries |
| Storage | Real MinIO staging/private active buckets, scoped API user, bounded presigned POST, destination verification | Archive/restore and safe staging maintenance |
| Policies | Model foundation | One seeded, deterministic, versioned policy with acceptance/rejection reasons |
| Recovery | No lifecycle recovery workflow yet | Bounded reconciliation and documented failure-injection results |
| Evidence | Real PostgreSQL/MinIO ingestion, concurrency, corruption, interrupted-commit and restart checks | Lifecycle failure matrix and reproducible discovery benchmark |

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

Worker timeout alone does not establish exclusive ownership. The core assumes controlled single-worker restart, settled in-flight requests, and bounded storage timeouts. Database polling must not blindly reclaim running work after a timeout; uncertain ownership requires controlled recovery. See the [reliability contract](PLAN.md#4-reliability-contract).

## Run the Ingestion MVP

Prerequisites: Docker with Docker Compose and GitHub access to build the pinned MinIO/mc sources. First build takes several minutes. Development and test commands use Python 3.12 and `uv` 0.12.3.

```bash
cp .env.example .env
docker compose up --build
```

Compose starts PostgreSQL 16, Redis 7, MinIO, bucket/user initialization, and the non-root FastAPI image. The API waits for PostgreSQL before applying migrations. The obsolete Celery health worker is opt-in through the `legacy-worker` profile; it is not the planned Pub/Sub subscriber/poller.

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

OpenAPI documentation: <http://localhost:8000/docs>. MinIO console: <http://localhost:9001>. Readiness requires PostgreSQL and the staging/active buckets; Redis is diagnostic, so its outage reports HTTP 200 with `status=degraded`. Liveness is not readiness or proof of lifecycle correctness.

All published ports bind to loopback. If port 8000 is occupied, use `API_PORT=58000 docker compose up --build` and open port 58000 instead. On an SSH host, forward the API and MinIO ports to the browser machine; signed storage URLs must be reachable there.

Treat this as a trusted local development environment only. There is no authentication or tenant authorization. The API storage user has scoped staging/active rights, not MinIO administration or deletion rights. Staging bytes persist until explicitly maintained; URL expiry does not delete them.

MinIO and mc are AGPL-3.0 dependencies built from pinned upstream sources in [docker/minio.Dockerfile](docker/minio.Dockerfile), with their licenses retained in the images. This does not change the application's MIT license. Review the [source and distribution notes](docs/milestone-1.md#storage-dependencies) before redistributing those images; these local builds are not a production support or security commitment.

### Current configuration

See [.env.example](.env.example) and [app/config.py](app/config.py). Keep real secrets outside Git.

| Variable | Current purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection URL |
| `REDIS_URL` | Diagnostic readiness check and legacy Celery defaults |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Optional legacy Celery overrides |
| `S3_REGION`, `S3_BUCKET`, `S3_STAGING_BUCKET`, `S3_ENDPOINT_URL` | Internal verified-ingestion storage settings |
| `S3_PUBLIC_ENDPOINT_URL` | Endpoint clients can reach for signed transfers |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Scoped storage credentials; synthetic local resources only |
| `MAX_UPLOAD_BYTES`, `SIGNED_URL_SECONDS` | Host application defaults: 10 MiB uploads and 300-second signed transfers |
| `ADMIN_API_KEY` | Configuration field only; no admin endpoint enforcement is implemented |

Do not interpret configuration fields as evidence that their associated features exist.

## API Status

Currently implemented:

```text
GET /                 Service metadata
GET /health           Process liveness
GET /health/ready     PostgreSQL/storage readiness; diagnostic Redis
POST /v1/uploads/initiate               Metadata + Idempotency-Key -> bounded upload form
POST /v1/uploads/{object_id}/complete   Stream-verify, promote, verify -> ACTIVE
GET  /v1/objects                       Filtered cursor-paginated metadata
GET  /v1/objects/{object_id}            Catalog lookup
GET  /v1/objects/{object_id}/download   Short-lived URL for verified active bytes
POST /v1/objects/{object_id}/access     Explicit application-access record
```

Initiation requires owner/dataset, logical key, size, SHA-256 and an aware retention deadline. Upload the returned `upload.fields` and file as multipart POST to `upload.url`, then complete. New content uses a new `content_version`; conflicting key reuse returns 409. Active completion retries do not copy again. API responses do not disclose private storage keys.

Discovery supports owner/dataset/workflow/lifecycle, desired/observed class, `created_before`, `created_after`, `last_access_before`, and `limit`/`cursor`. Timestamp filters require a timezone. The executable [synthetic round-trip script](scripts/verify_restart.py) and OpenAPI schema show the request contract.

Archive/restore requests, job status, an admin retry endpoint, and metrics remain planned in [PLAN.md](PLAN.md#6-deterministic-policy-and-minimal-interfaces).

Policy evaluation, outbox notification publication, reconciliation, and finding inspection will start as bounded CLI commands rather than a large admin API. The execution adapter will continuously subscribe and independently poll eligible database operations and due retries.

## Delivery Milestones

Milestone 1 has local exit evidence; the remaining milestones are planned. Remote Actions execution is still required after pushing the branch.

| Milestone | Required exit evidence | Status |
| --- | --- | --- |
| 1. Verified catalog round trip | PostgreSQL/MinIO upload, checksum verification, query, download, duplicates, and restart persistence | Locally verified; see evidence |
| 2. One complete lifecycle | Explainable policy -> archive -> restore; Pub/Sub wake-ups with database polling, missed-notification recovery, safe duplicates, concurrency guards, persisted retry/failure evidence | Planned |
| 3. Recovery and demonstration | Bounded reconciliation, findings, minimal metrics, and documented outcomes for every failure-matrix case | Planned |
| 4. Evaluation and public evidence | Clean-checkout demonstration, fair discovery benchmark, maintenance overhead, and reproducible results report | Planned |

At each milestone, update implemented/tested/planned status, run the full available suite and required CI gates, and record commands, environment, outcomes, and limitations. Blocked integration tests do not satisfy exit criteria.

**Core completion:** A new user can reproduce upload -> evaluate -> archive -> restore -> verify, recover from specified injected failures, and run a modest-scale benchmark.

## Development and Checks

```bash
uv sync --frozen --extra dev

uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -m 'not integration'

# Requires the configured PostgreSQL and initialized MinIO services.
uv run --frozen alembic upgrade head
RUN_INTEGRATION=1 uv run --frozen pytest --cov=app --cov-fail-under=75
```

Integration tests skip unless explicitly enabled. Use only an isolated synthetic test database: migration downgrade tests remove its schema. See [the evidence and reproduction commands](docs/milestone-1.md) for the isolated CI port setup and restart verification.

The [Checks and Delivery workflow](.github/workflows/checks.yml) runs on pull requests and pushes to `main` or `feature/**`: frozen dependency installation, lint/format, workflow/shell/Compose checks, unit tests, runtime dependency audit, migration upgrade/downgrade/drift, real-service integration with 75% minimum coverage, container readiness/restart verification, and an image vulnerability scan. Fixable HIGH/CRITICAL image findings block delivery; runtime dependency advisories fail the audit. Do not bypass findings silently. Rebuild/update affected dependencies and record any separately reviewed exception policy before accepting exceptions.

Only a successful `main` push promotes the exact tested/scanned API image to GHCR with `sha-<commit>` and `latest` tags. Feature branches and pull requests never publish. Repository packages permissions must permit the scoped `GITHUB_TOKEN`. This is continuous delivery, not an automatic production deployment. No cloud infrastructure or remote rollout is configured.

Configure GitHub branch protection/rulesets on `main` to require **Lint and Unit Tests**, **Dependency Audit**, and **Real Services and Container**, plus PR review and no direct bypass. Workflow files cannot enforce repository settings. Weekly [Dependabot updates](.github/dependabot.yml) cover Python, Actions and Docker dependencies. Local checks do not prove a remote workflow or GHCR publication has run.

## Evidence and Limitations

The evaluation will compare indexed queries with a catalog baseline without the candidate index and with equivalent namespace enumeration at the same physical population. Enumeration must obtain equivalent business metadata, not merely list keys. Report request counts, selectivity, cache conditions, repeated latency measurements, and query plans alongside ingestion, verification, and reconciliation overhead.

Begin with 100K logical catalog rows and a separately declared practical population of real small objects. Never present logical row counts as physically stored or processed capacity. No performance or recovery results are claimed here yet.

Two MinIO buckets demonstrate lifecycle orchestration, not Glacier retrieval behavior or actual archival pricing. Optional economic scenarios must include retained copies, requests, transitions, retrieval, and minimum-duration assumptions, and must be labeled as modeled projections.

Deferred work includes Grafana, rich policy administration, bulk folder operations, cost estimation, larger logical experiments, multi-worker scaling, the production Amazon S3 deployment, enterprise identity, and separately justified recommendation-only ML. Kubernetes, a custom frontend, and multi-region replication are outside the core scope. Terabyte-scale storage and global access are production design targets, not measured capabilities of this MVP.

Use synthetic/public material only. Owner metadata is not authorization, and the service must not be exposed to untrusted users without authentication and object-level access controls. Neither production readiness nor cross-system atomicity is claimed.

## License

[MIT](LICENSE)