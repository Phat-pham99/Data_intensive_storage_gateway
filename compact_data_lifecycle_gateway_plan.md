# EDISS Portfolio Project: Explainable Data Lifecycle Control Plane

**Author:** Phạm Hồng Phát  
**Purpose:** Portfolio artifact demonstrating Data-Intensive Intelligent Software Systems engineering.  
**Classification:** Clean-room, public-safe, non-confidential.

---

## 1. Executive Summary & EDISS Alignment

This project is a compact, production-grade **Data Lifecycle Control Plane**. It manages the lifecycle of objects stored in AWS S3, moving beyond simple CRUD operations to demonstrate asynchronous state management, explainable decision-making, and scalable batch orchestration.

### EDISS Theme Alignment
| EDISS Theme | Implementation in this Project |
| :--- | :--- |
| **Data-Intensive** | Manages object metadata, access patterns, storage tiers, and bulk folder operations. Decouples control plane from data plane to handle terabyte-scale concepts without payload bottlenecks. |
| **Intelligent Systems** | Features an explainable policy engine that scores object coldness, size, and access risk to recommend tiering, including a "what-if" simulation endpoint. |
| **Dependable Systems** | Enforces strict state machines, idempotency keys, bounded retries, checksum verification, and audit logging for all asynchronous operations. |
| **Software Engineering** | Built with FastAPI, Celery, PostgreSQL, Redis, and AWS S3. Includes Docker Compose, CI/CD, structured logging, and comprehensive testing. |

---

## 2. Clean-Room Declaration

This project is an independent public demonstration inspired by general production experience with enterprise storage and data-lifecycle systems. 
* **Strictly Prohibited:** Proprietary employer code, employer names in the repo, internal service names, real bucket names, business metrics, or production data.
* **Allowed Wording:** "Inspired by general production experience operating enterprise data-lifecycle systems."

---

## 3. Architecture & Technology Stack

### 3.1 High-Level Architecture
The system enforces a strict **Control Plane / Data Plane separation**. The FastAPI service never streams large object payloads. It handles metadata, policy decisions, and job orchestration. Actual data movement is handled via AWS S3 server-side operations or presigned client transfers.

```text
[ Client ] 
   | (1. Request Presigned URL)
   v
[ FastAPI Control Plane ] <--> [ PostgreSQL (Metadata, Jobs, Audit, Policy) ]
   | (2. Return Presigned URL)      ^
   v                                | (Enqueue/Update)
[ AWS S3 (Data Plane) ] <--> [ Redis ] <--> [ Celery Workers (Async Execution) ]

### 3.2 Technology Stack
API & Logic: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic.
Async Processing: Celery, Redis (Broker/Result Backend).
Database: PostgreSQL.
Storage: AWS S3 (boto3).
Infrastructure: Docker Compose.
Quality: pytest, Ruff, GitHub Actions.

## 4. Core Domain Model

### 4.1 Object
Tracks the metadata and state of a single S3 object.
id, bucket, key, filename, size_bytes, checksum_sha256, storage_class (STANDARD, STANDARD_IA, GLACIER_IR, GLACIER, DEEP_ARCHIVE). Note: GLACIER_IR is instantly retrievable; only GLACIER and DEEP_ARCHIVE require a restore transition.
lifecycle_state (ACTIVE, ARCHIVE_REQUESTED, ARCHIVING, ARCHIVED, RESTORE_REQUESTED, RESTORING, RESTORED, FAILED).
access_count, last_accessed_at, version (for optimistic locking).

### 4.2 Job & FolderJob
Tracks asynchronous operations.
Job: id, job_type, status, object_id, idempotency_key, celery_task_id, attempt_count, error_message.
FolderJob: id, prefix, status, total_objects, completed_objects, failed_objects (for aggregate batch tracking).

### 4.3 Policy & Audit
Policy: JSON configuration stored in DB (weights, thresholds, cost model). The cost model defines per-tier storage $/GB-month, retrieval $/GB, minimum storage duration (days), and request pricing, so scoring can account for retrieval fees and early-deletion penalties.
AuditEvent: Immutable log of every state transition (previous_state, new_state, reason, policy_version).

## 5. API Design (Control Plane)

### 5.1 Public Endpoints (Data Operations)
POST /v1/uploads/initiate
Validates request, creates CREATED object record.
Generates and returns an S3 Presigned PUT URL. (Zero payload touches the API).
POST /v1/uploads/{object_id}/complete
Verifies S3 ETag/Size against metadata.
Transitions state to ACTIVE.
Evaluates the Policy Engine and returns an immediate recommendation.
GET /v1/objects/{object_id}/download
If ACTIVE/RESTORED: Returns an S3 Presigned GET URL, increments access_count.
If ARCHIVED: Returns 409 Conflict.
POST /v1/objects/{object_id}/archive & /restore
Validates current state. Creates an async Job. Transitions to *_REQUESTED. Enqueues Celery task. Returns 202 Accepted.
GET /v1/jobs/{job_id}
Returns status, attempt count, and error details for polling.

### 5.2 Batch & Admin Endpoints
All /v1/admin/* endpoints require an admin API key (X-Admin-Key header) or a JWT with the `admin` scope; unauthenticated requests return 403.
POST /v1/folders/archive
Accepts a prefix. Uses S3 Pagination to enumerate objects.
Creates a FolderJob and fans out individual archive_object tasks via Celery group.
PUT /v1/admin/policies & POST /v1/admin/policies/simulate
Updates policy weights in DB.
Simulates policy against existing objects without applying it.
POST /v1/admin/policies/apply
Translates the internal JSON policy into an AWS S3 Lifecycle Configuration and applies it via boto3.put_bucket_lifecycle_configuration.

## 6. The "Intelligent" Layer: Explainable Policy Engine
Instead of hardcoded if/else rules, the system uses a transparent scoring function to evaluate tiering decisions.

### 6.1 Scoring Logic
score = (w_age * age_signal) + (w_cold * coldness_signal) + (w_size * size_signal) - (w_risk * access_risk) - (w_cost * retrieval_cost_penalty)

Retrieval cost penalty accounts for per-GB retrieval fees and minimum-storage-duration early-deletion charges for GLACIER/DEEP_ARCHIVE, so cold-but-frequently-restored objects are not over-tiered.

### 6.2 Explainable Output
Every evaluation returns a structured explanation, proving the system's reasoning:
{
  "recommended_tier": "STANDARD_IA",
  "score": 0.72,
  "components": { "age": 0.30, "coldness": 0.25, "size": 0.17, "risk_penalty": -0.00 },
  "reasons": [
    "Object has not been accessed for 45 days (Threshold: 30)",
    "Object size (50MB) exceeds minimum tiering threshold (128KB)",
    "Restore latency requirement is compatible with IA"
  ]
}

## 7. Data Plane Mechanics & Scalability

### 7.1 Server-Side Transitions
When archiving, the Celery worker does not download and re-upload the file. It uses the S3 CopyObject API to copy the object onto itself while changing the StorageClass header. This updates the metadata pointer instantly without moving the physical payload through the application server.

### 7.2 Folder Fan-Out (Replacing S3 Batch Operations)
To archive a folder of 10,000 files:
FastAPI uses boto3 paginators to list all keys matching the prefix.
A Coordinator Task chunks the enumerated keys into batches (e.g., 500 per chunk) and creates a Celery group of batch tasks, each processing its chunk with bounded retries. This avoids flooding the broker with 10,000 individual messages and keeps the chord callback payload small.
Workers process tasks concurrently with bounded retries and exponential backoff.
A Celery chord callback updates the parent FolderJob with aggregate progress (e.g., "8,432 / 10,000 completed").

## 8. Reliability & State Machine

### 8.1 Strict State Transitions
All transitions are validated against a strict mapping. Conflicting commands (e.g., restoring an object currently archiving) are rejected. Restore transitions are only valid for GLACIER and DEEP_ARCHIVE storage classes; GLACIER_IR objects are instantly retrievable and never enter RESTORE_* states. FAILED objects may be re-driven via POST /v1/jobs/{id}/retry, which transitions FAILED back to the prior requested state.
ALLOWED_TRANSITIONS = {
    "ACTIVE": {"ARCHIVE_REQUESTED"},
    "ARCHIVE_REQUESTED": {"ARCHIVING", "FAILED"},
    "ARCHIVING": {"ARCHIVED", "FAILED"},
    "ARCHIVED": {"RESTORE_REQUESTED"},
    "RESTORE_REQUESTED": {"RESTORING", "FAILED"},
    "RESTORING": {"RESTORED", "FAILED"},
    "RESTORED": {"ACTIVE"},
}

### 8.2 Failure Handling
Idempotency: The Idempotency-Key scopes the *API request*, not the Celery task. A duplicate request with the same key returns the existing Job and its status without enqueuing a new task. Celery tasks are themselves idempotent by (object_id, target_state), so replays are safe.
Retries: Celery tasks use max_retries with exponential backoff for transient S3 API throttling (503 Slow Down).
Dead Letters: After retry exhaustion, the job moves to FAILED state, preserving the error for manual inspection via POST /v1/jobs/{id}/retry.

## 9. Implementation Roadmap
Milestone 1: Foundation. Docker Compose, FastAPI, Postgres, Redis, DB migrations.
Milestone 2: Control Plane. Presigned URL uploads, metadata persistence, checksum verification, download endpoints.
Milestone 3: Async Core. Celery integration, Archive/Restore endpoints, strict state machine, idempotency.
Milestone 4: Intelligence. Policy engine scoring, explanation generation, What-If simulation endpoint.
Milestone 5: Scale & Admin. Folder prefix enumeration, Celery fan-out, dynamic S3 lifecycle API application, Prometheus metrics.

## 10. Definition of Success & CV Integration

### 10.1 Completion Checklist
Docker Compose spins up the full stack (API, Worker, DB, Redis).
Uploads use presigned URLs (zero payload through API).
Archive/Restore use server-side S3 CopyObject (zero payload through Worker).
Policy engine returns structured explanations, not just binary decisions.
Folder archive successfully fans out via Celery and tracks aggregate progress.
Duplicate commands are safely ignored via idempotency keys.
Unit and integration tests pass in CI.

### 10.2 Suggested CV Entry
Explainable Data Lifecycle Control Plane | Python, FastAPI, Celery, PostgreSQL, AWS S3
Architected a control-plane/data-plane separated storage lifecycle system. API handles metadata and policy orchestration via presigned URLs, while Celery workers execute server-side S3 CopyObject transitions, ensuring zero payload bottlenecks at scale.
Engineered an asynchronous fan-out architecture for folder-level operations, utilizing S3 pagination and Celery groups to replace heavy batch APIs, complete with aggregate state tracking and bounded retries.
Designed an explainable policy engine that scores object coldness, size, and access risk to recommend tiering decisions, providing transparent reasoning and "what-if" simulation for FinOps decision support.