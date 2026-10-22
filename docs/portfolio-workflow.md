# Portfolio Workflow: Source Notes and Text Alternative

## Scope

The [portfolio animation](assets/portfolio-workflow.gif) and [static poster](assets/portfolio-workflow.png) illustrate one job and the subsequent lifecycle of its artifacts. The matching [gateway zoom-in](assets/lifecycle-workflow.gif) and [poster](assets/lifecycle-workflow.png) continue the same job 017 / artifact v1 / 2 MiB after results return. They are original conceptual illustrations, not a recorded execution, integration test, performance result, or reproduction of an employer's production architecture.

The two public projects are independent. The conceptual export and upload client between them is not implemented. Preparing inputs and receiving results happens in a generic **User Environment**. The heterogeneous compute context is motivation only; the reviewed HTCondor demo uses local Docker resources, not demonstrated cloud, on-demand or interruptible capacity.

Reviewed on 2026-10-22. Source descriptions below are based on reading code, not rerunning either platform. The image always says **Conceptual workflow animation**. Source/scope notes remain visible throughout, and stage labels distinguish an HTCondor mechanism from a proposed handoff or gateway design.

## Reviewed Sources

### HTCondor

Source snapshot: [HTCondor_concept_MVP at 0ea3d2d](https://github.com/Phat-pham99/HTCondor_concept_MVP/tree/0ea3d2dabce1da3a26b5072ce05c260ec29f8034).

| Source | Verified description and illustration consequence |
| --- | --- |
| [Submission file](https://github.com/Phat-pham99/HTCondor_concept_MVP/blob/0ea3d2dabce1da3a26b5072ce05c260ec29f8034/workload_demo/job.sub) | Queues four serial Monte Carlo jobs. Enables file transfer, declares executable/input and result files, and selects output transfer on exit. The animation follows one representative job, not all four. |
| [Workload](https://github.com/Phat-pham99/HTCondor_concept_MVP/blob/0ea3d2dabce1da3a26b5072ce05c260ec29f8034/workload_demo/monte_carlo_pi.py) | Writes a small JSON result containing samples, seed, and pi. It does not produce the 2 MiB illustrative artifact used here. |
| [Manager configuration](https://github.com/Phat-pham99/HTCondor_concept_MVP/blob/0ea3d2dabce1da3a26b5072ce05c260ec29f8034/config/condor_config.manager) | Configures collector, negotiator, schedd and startd. The animation says selected execution slot, not that a job must execute on a particular added worker. |
| [Autoscaler](https://github.com/Phat-pham99/HTCondor_concept_MVP/blob/0ea3d2dabce1da3a26b5072ce05c260ec29f8034/autoscaler/condor_docker_autoscaler.py) | Polls HTCondor over SSH and creates/removes labeled workers through the Docker API. The implementation combines totals from `condor_q` and `condor_status`; a pool slot count is not automatically a running-job count. Capacity and idle-removal logic exist, but this source review does not establish scaling behavior, idle convergence, worker safety, or production elasticity. |
| [Compose configuration](https://github.com/Phat-pham99/HTCondor_concept_MVP/blob/0ea3d2dabce1da3a26b5072ce05c260ec29f8034/docker-compose.yml) and autoscaler | Set up the manager, autoscaler, worker image, local network and output volume. The autoscaler also mounts the output volume into workers. Configured HTCondor file transfer is shown, but the graphic does not claim that this particular demo establishes independence from all shared storage. |
| [Demo script](https://github.com/Phat-pham99/HTCondor_concept_MVP/blob/0ea3d2dabce1da3a26b5072ce05c260ec29f8034/run_demo.sh) | Submits the jobs, checks that expected output files are non-empty, lists output, then removes containers and volumes during cleanup. Those checks are not semantic JSON validation or checksum verification. Output export must happen before cleanup; no gateway connector is present. |

The visual separates a job-submission request from executable/input transfer, and execute-to-submit output transfer from the proposed export to the user. It deliberately does not draw an automatic submit-to-gateway connection.

### Storage Gateway

- The checked-out `main` baseline during review was `ac4e84e`. [app/main.py](../app/main.py) contains the foundation health/API surface, not a working archive/restore workflow. Its status remains unchanged by this documentation work.
- The separately committed `feature/verified-catalog-ingestion` work at `7f905e7` was inspected through Git without checking it out or merging it. Its `ObjectStorage.verify` reads actual bytes and compares size and SHA-256. Upload completion verifies staging, copies to a private active key with a source precondition, verifies the destination, then commits `ACTIVE`. Its ingestion tests/evidence are not end-to-end portfolio integration evidence.
- [PLAN.md](../PLAN.md) supplies immutable identity, verified-before-delete archive, retained-copy restore, policy metadata, controlled ownership and recovery requirements. The checked-out plan still contains older messaging language; the current [README reliability design](../README.md#planned-reliability-guarantees-and-limits) explicitly supersedes that part with **Redis Pub/Sub plus independent PostgreSQL polling**. The illustration follows that chosen design, not the older broker proposal.
- The archive rule requires workflow completion, inactivity of at least 180 days, remaining retention of at least 180 days, size of at least 1 MiB, no legal hold, known metadata and compatible placement/ownership. A tiny Monte Carlo JSON result alone fails the size condition. For the single-job story, the animation intentionally uses an illustrative 2 MiB scientific artifact and a labeled time jump. This does not change or measure the actual demo workload.
- Archive/restore and its execution adapter are planned behavior, not shown as deployed capabilities. A lost notification must not strand durable work; an archive source is removed only after verified destination bytes; restore retains the archive copy. A post-delete database failure needs controlled recovery, not a claim of cross-store atomicity.

## Text Alternative

Each scene lasts four seconds. The complete loop is 80 seconds; the 180-day policy jump is conceptual, not elapsed playback time. Paused text, flow labels and source notes are available below without animation.

| Step | Handoff or decision | Evidence boundary and state |
| --- | --- | --- |
| 01 | Prepare one scientific job and its expected output. | Illustrative job 017, artifact version 1, 2 MiB. Not an actual HTCondor job ID or measured result size. |
| 02 | Submit a job request to the schedd queue. | Control message, not file bytes. Collector/negotiator matchmaking chooses an available slot. |
| 03 | Observe demand and manage local worker capacity. | Code contains local Docker worker management. No cloud capacity, scaling performance or idle-convergence claim. |
| 04 | Transfer executable and inputs to the selected execution slot. | The submission file enables HTCondor transfer. Only one representative job is followed. |
| 05 | Execute and produce the declared result. | Actual demo produces small pi JSON; the graphic uses a synthetic scientific artifact to illustrate the broader lifecycle. |
| 06 | Return declared outputs to the submit-host output area on exit. | Do not confuse this with delivery to a user or registration in the gateway. |
| 07 | Export/preserve the output for the user before demo cleanup. | Proposed handoff. The present demo removes its output volume; neither project implements this connector. |
| 08 | Separate compute lifetime from artifact lifetime. | Releasing compute is safe for this story only after independent output preservation. That preservation remains proposed. |
| 09 | Initiate ingestion with owner/dataset, version, size and SHA-256. | Metadata/control request reserves catalog identity. Desired ACTIVE, observed UNKNOWN. |
| 10 | Upload the artifact bytes into staging with a bounded capability. | Different path from metadata. No direct client write to the verified active key. |
| 11 | Verify staging, promote, verify destination and commit ACTIVE. | Actual streamed size/hash comparison; ETag is not SHA-256. Staging/export copies are not silently deleted. |
| 12 | Jump forward at least 180 days and evaluate policy. | COMPLETE, no hold, sufficient inactivity/remaining retention and size. The original tiny JSON would not qualify. |
| 13 | Persist desired placement, operation, audit and outbox; claim work. | Desired ARCHIVE, observed ACTIVE. PostgreSQL polling is authoritative; a Redis hint is optional. |
| 14 | Copy immutable active bytes to archive. | Active retained. Destination still unverified, so observed serving placement remains ACTIVE. |
| 15 | Read and verify archive bytes; revalidate ownership and guards. | Keep active while verifying. Corruption/uncertainty blocks destructive progress. |
| 16 | Remove active only after successful verification; commit ARCHIVED. | Observed ARCHIVE. A failed final database commit requires controlled recovery from the surviving verified destination. Other staging/export copies may still exist. |
| 17 | Persist a restore request for the same immutable version. | Desired ACTIVE, observed ARCHIVE. No new content is created by restore. |
| 18 | Copy archive to active, or reuse a verified matching destination. | Archive retained throughout. No active success state before verification. |
| 19 | Verify active bytes, commit ACTIVE and record retained archive. | Active and archive are both verified in the conceptual path. The retained replica is intentional. |
| 20 | Discover the artifact and download verified active bytes again. | The compute job is complete; the catalog and artifact lifecycle continue. This is still not a demonstrated integrated platform. |

## Gateway Zoom-In Text Alternative

The refactored gateway animation replaces the former standalone 14-step loop. It uses the portfolio animation's fixed visual style, synthetic identity, 180-day policy jump, control/byte colors, state semantics, and four-second scene timing. Its 20 scenes last 80 seconds. The job remains `COMPLETE` throughout; artifact lifecycle and placement are separate from compute status.

The opening banner connects the stories explicitly: HTCondor returns results to its submit host; preservation before cleanup and transfer into the gateway remain proposed. The FastAPI label says validation/initiation/query rather than claiming authentication or tenant authorization. This zoom-in does not add a third project or a demonstrated integration.

| Step | Gateway detail | State and safety boundary |
| --- | --- | --- |
| 01 | Preserve returned results in the User Environment. | Proposed export before cleanup; not registered in the gateway. Same illustrative 2 MiB artifact, not the actual demo's tiny JSON. |
| 02 | Reserve ingestion and issue a bounded capability. | `INGESTING`; desired `ACTIVE`, observed `UNKNOWN`. Metadata identity is not the object bytes. |
| 03 | Upload to staging. | Source retained; staging capability expiry does not imply automatic deletion. |
| 04 | Read/verify staging, promote and verify destination. | Observed stays `UNKNOWN` until verified registration commits. ETag is not SHA-256. |
| 05 | Commit `ACTIVE` and audit evidence. | Active bytes verified; source/staging may still exist. Ingestion has separate feature-branch evidence, not portfolio integration evidence. |
| 06 | Jump forward at least 180 days and evaluate policy. | COMPLETE workflow, no hold, inactivity/remaining retention/size guards. Unknown metadata rejects; small demo JSON fails the size rule. |
| 07 | Atomically persist desired archive placement, operation, audit and outbox. | `ARCHIVE_REQUESTED`; desired `ARCHIVE`, observed `ACTIVE`. Intent is not movement. |
| 08 | Publish an optional Redis Pub/Sub hint. | Successful publication does not establish receipt; no Pub/Sub replay or acknowledgement. |
| 09 | Poll PostgreSQL independently and claim eligible work. | `ARCHIVING`; work remains discoverable with Redis down. One controlled executor; no timeout-based ownership assumption. |
| 10 | Copy immutable active bytes to archive. | Keep active; destination is not yet verified. No deletion or success from copy acknowledgement alone. |
| 11 | Stream-verify archive and revalidate safety/ownership. | Observed remains `ACTIVE`; corruption or uncertain ownership stops destructive progress. |
| 12 | Delete active only after verification; commit `ARCHIVED`. | Observed `ARCHIVE`. A failed post-delete DB commit needs controlled recovery; there is no cross-store atomicity. |
| 13 | Skip a duplicate notification for finished work. | Load persisted terminal operation; no extra copy/delete. Idempotent execution is not exactly-once delivery. |
| 14 | Persist a restore request for the same version. | `RESTORE_REQUESTED`; desired `ACTIVE`, observed `ARCHIVE`. Compute remains complete. |
| 15 | Copy verified archive to active or reuse verified matching bytes. | `RESTORING`; retain archive, do not trust a corrupt destination. |
| 16 | Verify and commit active placement with retained-archive evidence. | `ACTIVE`; observed `ACTIVE`. No separate `RESTORED` steady state; archive replica is intentional. |
| 17 | Discover and download active bytes again. | Artifact use continues without rerunning compute. A signed link is not a lease against later archival. |
| 18 | Illustrate detection of a missing active copy. | Planned reconciliation scenario: `DRIFTED`, desired `ACTIVE`, observed `UNKNOWN`; record a finding. |
| 19 | Inspect and verify the retained archive. | Still observed `UNKNOWN` for serving placement until repair; missing/corrupt/ambiguous alternatives require review. |
| 20 | Perform only an authorized, exclusively owned verified repair. | Copy, verify, commit resolution and retain archive/audit history. No destructive guess or adoption of unknown bytes. |

`NOT REGISTERED` is an explanatory pre-ingestion label, not a new application enum. `DRIFTED` and automated reconciliation describe later target behavior from the plan; this asset does not add those capabilities to the current service. The source/scope text stays visible so an intended state transition is not mistaken for an executed test.

## Visual Contract

- Use the same component names and user-above/compute-left/storage-right organization as the [Mermaid overview](../README.md#shared-architectural-context). Mermaid lays itself out; the GIF uses a fixed map so scene changes do not move components.
- Blue paths represent control/metadata; green paths represent bytes. Dashed paths identify proposed user/export adapters. Inactive paths are muted; only one path receives a moving token in a scene.
- The caption and placement strip advance together. Do not display an archive or restored serving state before the corresponding verification and commit scene.
- The amber compute-context note is not an animation of a production fleet. It deliberately does not reproduce a real deployment.
- The [gateway zoom-in GIF](assets/lifecycle-workflow.gif) continues the same artifact with matching component names and style, then expands the internal lifecycle/reconciliation design. Its three-column map is deliberately more detailed than the portfolio overview; it does not replay or claim compute execution.
- Full reconciliation, runtime failure replay and production recovery are not demonstrated by these frames. The safety notes explain the intended constraints, not evidence of executed tests.

## Regeneration and Validation

Sources: [scripts/generate_portfolio_workflow.py](../scripts/generate_portfolio_workflow.py) and [scripts/generate_lifecycle_workflow.py](../scripts/generate_lifecycle_workflow.py). The zoom-in reuses the portfolio text/edge renderer and verified GIF/poster writer, but keeps its own storyboard and map. Both render only images; neither starts containers, executes jobs, uploads artifacts, or modifies data services. Pillow is pinned through inline script metadata and installed into uv's isolated script environment, not the application's dependencies.

Requirements: Python 3.12+, uv, and Source Sans 3 regular/semibold OTF fonts. Linux font directories are detected; DejaVu Sans is a fallback. For consistent output across machines, pass `--font-dir` pointing to `SourceSans3-Regular.otf` and `SourceSans3-Semibold.otf`. Font files are not bundled.

```bash
# Check every scene without writing assets.
uv run --no-project scripts/generate_portfolio_workflow.py --check
uv run --no-project scripts/generate_lifecycle_workflow.py --check

# Regenerate both GIF/poster pairs and optional temporary review frames.
uv run --no-project scripts/generate_portfolio_workflow.py \
  --preview-dir /tmp/portfolio-workflow-review
uv run --no-project scripts/generate_lifecycle_workflow.py \
  --preview-dir /tmp/lifecycle-workflow-review
```

The default output directory is [docs/assets](assets). `--output-dir` can place generated assets elsewhere. The portfolio script writes `portfolio-workflow.gif/.png`; the gateway script writes `lifecycle-workflow.gif/.png`. Only GIFs and posters belong in the repository; individual review frames are temporary.

Each asset's checks include text bounds for every scene, node/edge references, one-path motion within the diagram, placement progression across copy/verification/commit boundaries, 1600 x 1080 dimensions, 240 frames, 80 seconds, infinite looping, decoded-frame equivalence (no disposal/compositing residue), and a 12 MiB maximum GIF size. The gateway storyboard also verifies constant completed-job identity and uncertainty during its missing-copy example. These are illustration checks, not application correctness tests. Representative first/handoff/archive/restore/drift scenes should also be visually inspected after changes.

Keep source review dates and references explicit. Recheck behavior when either repository changes; an animation must not silently turn a plan into a claim of implemented integration.