# EMS v1.1: automatic offline replay contract

Base: PR #26, `f9362f53932594fa37800f1939405d47c9a6365f`. No production activation.

## Admission and trust

The existing writer commits its original solution/state/report before publishing
`genetic-evidence/<event-version>.zip` through an exclusive, fsynced hard link,
while holding `sync.lock` exclusively. The worker takes the **existing** lock
shared/nonblocking, reads only allowlisted original artifacts, and releases it
before native work. It never creates or repairs a source lock or archive.

Admission requires the final archive, stable file identities, exact archived
solution bytes, identical persisted selected claim, successful original event,
and `historical.validate`: accepted `event-evidence-v2`, complete
`solver-input-binding-v1`, all Doctor checks. A later waiting report does not
replace archived inputs. A contradictory current selected event rejects admission.
Missing/in-progress input is retried finitely; invalid complete evidence fails closed.

Automatic admission starts at a persisted activation watermark. Earlier dates,
including 30 October, require explicit selection and still cannot bypass checks.
An independently validated imported sidecar proves only native reproducibility;
it never upgrades an original execution claim.

## Execution boundary

One isolated non-root container: no network/socket/devices/secrets/config mount,
read-only root and original archive, all capabilities dropped, no-new-privileges,
CPU/memory/PID/tmpfs limits, nice priority, no optimizer entrypoint. The worker
writes only its private workspace. A shared worker lock is inherited by the
native subprocess so an interrupted parent cannot allow a second native job.
Native jobs also have their own wall/CPU/address-space limits. Logs contain
allowlisted reason codes and hashes only; native stdout/stderr are suppressed.

`replay_export.create_plan` and the original replay validator remain unchanged:
two fixed simulations, original controls and inputs, original result equality,
instrumentation equality, pinned source fingerprints and internal gross-energy
balances. No baseline, current forecasts, HTTP or optimizer search.

## Publication and recovery

Immutable per-source-hash sidecars use the unchanged native-flow-replay-v1
format. Immutable receipts bind original bytes, archive bytes, manifest,
artifact hashes, claim, EOS revision, sidecar file hash and runtime metrics.
Publication is exclusive and durable. Interrupted completed candidates are
validated before recovery; successful original versions are never recalculated.

The sole mutable reader input `catalog.json` is one atomically replaced,
self-sealed native-flow-replay-v1 document. Its additional `worker_catalog`
field has contract `eos-pv-helper/replay-worker-catalog-v1` and binds the embedded
plans to immutable sidecar/receipt file digests. The worker checks the entire
previous generation before adding an entry; corrupt state is not silently repaired.
The existing dashboard reader validates each plan independently against the
original source bytes and ignores the supplemental metadata. No helper-image
change is needed.

The host HTML adapter snapshots one opened catalog inode into a private temporary
file before calling the unchanged publisher with `--replays`. A rename during
snapshot therefore produces one complete generation. Invalid catalog data leaves
the reader's last valid display and visible error handling intact. HTML refresh
never calls the worker. Existing history ownership/EFC algorithms stay unchanged.

Mutable, atomically written status is a separate operational record containing
`pending`, `running`, `verified`, `rejected`, `retry_later`, hashes, duration,
revision, retry deadline and a fixed reason code. Hash seals establish private
consistency, not authentication or proof of historical device execution.
