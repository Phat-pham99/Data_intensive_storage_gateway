# Explainable Data Lifecycle Control Plane

A compact, production-grade **Data Lifecycle Control Plane** that manages the lifecycle of objects stored in AWS S3. It demonstrates asynchronous state management, explainable decision-making, and scalable batch orchestration — with a strict **control plane / data plane separation** so no object payload ever traverses the API.

> Clean-room, public-safe, non-confidential. Inspired by general production experience operating enterprise data-lifecycle systems.

---

## Features

- **Data-Intensive** — Manages object metadata, access patterns, storage tiers, and bulk folder operations. Decouples control plane from data plane.
- **Intelligent Systems** — An explainable, cost-aware policy engine that scores object coldness, size, access risk, and retrieval-cost penalties; what-if simulation; optional scheduled enforcement.
- **Dependable Systems** — Strict state machine, request- and task-level idempotency, bounded retries, checksum verification, audit logging, and a single-writer storage-class ownership model.
- **Software Engineering** — FastAPI, Celery (+ beat), PostgreSQL, Redis, AWS S3, Docker Compose, Alembic, pytest, Ruff, GitHub Actions — delivered in phases with explicit exit criteria.

---

## Technology Stack

| Layer | Tools |
| :--- | :--- |
| API & Logic | Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic |
| Async Processing | Celery worker + beat, Redis broker |
| Database | PostgreSQL |
| Storage | AWS S3 via boto3 (additional checksums) |
| Infra / Quality | Docker Compose, pytest, Ruff, GitHub Actions, moto/LocalStack |

---

## Project Structure

```text
.
├── alembic/                  # Migrations (0001_initial_schema)
│   ├── env.py
│   └── versions/
├── app/
│   ├── main.py               # FastAPI app + health/readiness endpoints
│   ├── config.py             # pydantic-settings configuration
│   ├── celery_app.py         # Celery application factory
│   ├── enums.py              # Storage/lifecycle/job enums + state machine
│   ├── db/                   # Engine, session, declarative base
│   ├── models/               # StorageObject, Job, FolderJob, Policy, AuditEvent
│   ├── tasks/                # Celery tasks (health.ping, archive, restore, ...)
│   └── wait_for_deps.py      # Postgres/Redis readiness gate
├── docker/
│   └── entrypoint.sh         # Migration + dependency-wait bootstrap
├── tests/                    # Unit + integration tests
├── docker-compose.yml        # api, worker, postgres, redis
├── Dockerfile
├── pyproject.toml
└── PLAN.md                   # Authoritative phased specification
```

---

## Getting Started

### Prerequisites

- Docker + Docker Compose
- (Optional) `uv` for local development

### Run the full stack

```bash
cp .env.example .env
docker compose up --build
```

This starts:

- `postgres:16` (port 5432)
- `redis:7` (port 6379)
- `api` (port 8000) — runs migrations on startup
- `worker` — Celery worker consuming archive/restore jobs

### Verify

```bash
curl http://localhost:8000/health          # liveness
curl http://localhost:8000/health/ready    # readiness (DB + Redis)
```

OpenAPI docs are served at `http://localhost:8000/docs`.

---

## Configuration

All configuration is via environment variables — see `.env.example`.

| Variable | Description |
| :--- | :--- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL |
| `REDIS_URL` | Redis broker/backend URL |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Optional Redis overrides |
| `S3_REGION` / `S3_BUCKET` | S3 target |
| `S3_ENDPOINT_URL` | Override for LocalStack/minio |
| `ADMIN_API_KEY` | Static key required for `/v1/admin/*` |
| `ENFORCEMENT_MODE` | `worker` (default) or `aws_lifecycle` |

---

## API Overview

### Public (data operations)

- `POST /v1/uploads/initiate` — creates a `CREATED` object, returns a presigned PUT URL.
- `POST /v1/uploads/{object_id}/complete` — verifies checksum/size, transitions to `ACTIVE`.
- `GET /v1/objects/{object_id}/download` — presigned GET (or `409` for archived objects).
- `POST /v1/objects/{object_id}/archive` · `restore` — create async job, return `202`.
- `GET /v1/jobs/{job_id}` — poll job status.
- `POST /v1/jobs/{job_id}/retry` — re-drive a `FAILED` job.

### Batch & admin (require `X-Admin-Key`)

- `POST /v1/folders/archive` — prefix-scoped chunked fan-out.
- `PUT /v1/admin/policies` — update versioned scoring policy.
- `POST /v1/admin/policies/simulate` — what-if evaluation (no writes).
- `POST /v1/admin/policies/apply` — project or apply S3 lifecycle configuration.

See `PLAN.md` §5 for full endpoint semantics and `PLAN.md` §6 for the explainable scoring model.

---

## Development

```bash
# create a virtualenv and install dev dependencies
uv venv --python 3.12
uv pip install -e ".[dev]"

# lint + format
ruff check .
ruff format .

# run tests
pytest

# run migrations against a local database
alembic upgrade head
```

CI runs lint, format check, migrations, and tests on every push.

---

## Testing

- **Unit** — state machine (including GLACIER_IR fast path, expiry sweeps, denied transitions), policy determinism, idempotency conflicts, cost model.
- **Integration (moto/LocalStack)** — presigned initiate→complete→download round trip; archive/restore happy paths; duplicate commands; injected transient failures.
- **CI** — Ruff, tests, migrations up/down, secret scan.

---

## Phased Delivery Plan

The project is delivered in five sequential phases. Each is independently testable and is complete only when its exit criteria are met.

| Phase | Deliverable | Status |
| :--- | :--- | :--- |
| **1 — Foundation** | Containerized stack, schema, migrations, CI | **Complete** |
| **2 — Control Plane** | Presigned upload/download, checksum verification, sweeps | Planned |
| **3 — Async Core** | Archive/restore jobs, state machine, idempotency, IR fast path, slow path | Planned |
| **4 — Intelligence** | Policy engine, simulation, synthetic seeder | Planned |
| **5 — Scale & Admin** | Folder fan-out, enforcement modes, beat tasks, admin auth, metrics | Planned |

Full detail, deliverables, and exit criteria live in `PLAN.md`.

---

## Observability (minimal)

Metrics: `operations_total`, `operation_retries_total`, `checksum_failures_total`, `policy_recommendations_total`, `folder_job_objects_total`, `restore_verified_total`, `storage_class_transitions_total`.
Structured logs: `service, object_id, job_id, correlation_id, state, event, attempt, error`.

---

## Definition of Success

See `PLAN.md` §13. Highlights:

- [ ] Compose stack healthy; readiness reports DB + Redis ok.
- [ ] Presigned uploads with checksum conditions; zero payload through API.
- [ ] Server-side transitions; zero payload through worker.
- [ ] GLACIER_IR objects downloadable while archived and restorable in seconds.
- [ ] Idempotency via unique index; replays safe.
- [ ] Policy engine explains every recommendation; simulation writes nothing.
- [ ] Folder fan-out recomputes aggregates; partial failure tolerated.
- [ ] Enforcement modes enforce single-writer ownership.
- [ ] Tests and CI green.

---

## License

[MIT](LICENSE)
