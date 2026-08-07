# Resumable / chunked matching -- design scoping (v42)

Status: **scoping only, not implemented.** Founder asked to start this
after v42 found the corpus has outgrown a single Vercel function
invocation, and that the plan doesn't even grant the 800s v41 assumed
(actual ceiling: 300s, confirmed empirically this session -- see v42
handover). This doc lays out the problem, the constraints, a proposed
design, and the specific decisions the founder needs to make before
anyone implements it.

## 1. The problem, stated precisely

`run_matching_for_track()` (matching_service.py) is a single unbroken
Python loop over every job in the `jobs` table, run inline inside one
Vercel serverless invocation via BackgroundTasks. It was never written
to stop and resume -- there's no cursor, no chunk boundary, nothing.

Measured cost: 6,901 jobs took **880s locally** (~7.8 jobs/sec, uv/
local Python, v41 §1g) and an estimated **~530s** at "current
throughput" against Vercel per v41's own maxDuration reasoning. Either
number is well past the function's actual 300s ceiling (v42). The
corpus has grown 3,221 -> 6,901 jobs in about three weeks (2 -> 73
connector sources); whatever number is true today will be higher
again by the next ingestion pass. This is not a one-time problem to
patch around -- it's a scaling curve the current architecture can't
follow.

The stale-run reaper (matching/repository.py, added v41/fixed v42)
means a function that gets SIGTERM'd mid-run no longer blocks the
track forever -- but it also doesn't make progress. Retrying the same
unbroken loop just times out again at the same point. Today, a
full-corpus run **cannot complete** through the real API for any
track, full stop -- only the founder's local `uv run
scripts/run_matching.py` workaround (bypasses matching_runs tracking
entirely) actually finishes.

## 2. What "chunked and resumable" needs to mean

Two independent properties, both required:

- **Chunked**: one invocation processes a bounded slice of the job
  list, not all of it, and stops itself well before the platform would
  kill it.
- **Resumable**: the next invocation picks up exactly where the last
  one left off, without reprocessing already-scored jobs or missing
  any.

## 3. Proposed architecture

### 3a. Deterministic ordering (prerequisite, currently missing)

`JobRepository.list_all()` has no `order` param -- PostgREST's row
order without one is not guaranteed stable across separate paginated
calls, and even less so across function invocations that run minutes
or hours apart while ingestion may be adding new rows concurrently.
**Any chunking design is unsound until this is fixed.** Needs an
explicit `order=created_at.asc,id.asc` (tie-break on id since
created_at isn't unique) so:
- Chunk N+1 always starts exactly where chunk N stopped.
- A job ingested mid-run lands after the run's current position and
  either gets picked up by a later chunk (fine) or missed entirely if
  the run finishes first (acceptable -- same as today, where a run
  only ever sees the corpus as of when list_all() was called).

### 3b. Cursor + chunk state on `matching_runs`

Two new columns:
- `resume_cursor` (uuid, nullable) -- the last job_id fully processed.
  `NULL` means "not started" / "start from the beginning."
- `chunks_completed` (int, default 0) -- purely observational, for
  debugging/support visibility into how many hops a run took.

`jobs_processed`/`jobs_total` (already exist) keep meaning what they
mean today -- no change to the polling contract
(`GET /tracks/{id}/match-status/{run_id}`) that the frontend already
relies on.

### 3c. Time-boxed chunk loop

`run_matching_for_track()` gains a `resume_from: UUID | None` param
and a `deadline: datetime` param. The loop:
- Fetches jobs with `id > resume_from` (given 3a's ordering) instead
  of always fetching everything.
- After each job, checks `datetime.now(timezone.utc) >= deadline`. If
  so, stops (not a crash -- a deliberate, clean pause), returns how
  far it got.
- The tracked wrapper (`run_matching_for_track_tracked`) persists
  `resume_cursor` at the stopping point and sets status to a **new**
  value, `'paused'` (not `'completed'`, not `'failed'`) -- so
  `get_running_run_for_track`'s 409-conflict check needs to also
  treat `'paused'` as "don't start a competing run," and the stale-run
  reaper needs to reap an old `'paused'` row too (a paused run that
  never got resumed is just as dead as an orphaned `'running'` one).
- `deadline` is set conservatively below the 300s cap -- proposed
  **240s**, leaving ~60s margin for the last job's embedding call,
  the two DB round-trips in `upsert_match()`, and function cold-start
  variance. This number should be tuned against a real measurement,
  not assumed (see open question 5b).

### 3d. What resumes a paused run

This is the one genuinely open architectural fork -- three real
options, not a fake choice:

**Option A -- Vercel Cron.** A new endpoint (e.g. internal-only
`POST /internal/matching/resume-sweep`), scheduled via `vercel.json`'s
`crons` array, runs every N minutes, queries `matching_runs` for
`status = 'paused'`, and re-invokes `run_matching_for_track_tracked`
with each one's `resume_cursor`. Secured via `CRON_SECRET` env var +
`Authorization` header check (Vercel's own documented pattern -- see
"Secure Cron Jobs" in their docs). Simple, no new infra, matches how
this project already treats scheduled/background work conceptually
(BackgroundTasks). **Caveat found while scoping, not yet confirmed**:
Vercel Cron's minimum interval depends on the plan -- this project
just learned the hard way (v42) that its actual plan entitlements
don't match what was assumed for `maxDuration`, so the schedule
granularity needs to be checked the same way, not assumed. If the
plan only allows once-daily crons, this option doesn't give an
acceptable resume latency for a run that needs several hops to finish
in one sitting.

**Option B -- self-continuation.** The chunk, right before it returns,
fires an unawaited outbound POST to its own resume endpoint (fire-
and-forget, similar in spirit to how BackgroundTasks already works
here). No cron needed, resumes almost immediately. Downside: more
moving parts to get right (needs its own retry/backoff if the POST
itself fails, and self-calling patterns on serverless platforms can
be fragile -- e.g. if the platform ever rate-limits or blocks a
function calling its own production URL).

**Option C -- Vercel Workflows.** Vercel's own long-running-workflow
primitive (supports `sleep()` and resumable steps natively, found
while scoping via their docs). Would remove the need to hand-roll any
of 3a-3c at all -- but the documented examples are TypeScript/Nitro-
flavored, and it's unconfirmed whether it supports this project's
Python/FastAPI runtime at all. Worth a short spike to check before
ruling in or out, since if it works it's strictly less code to
maintain than A or B.

Recommendation for the founder to weigh in on: **spike Option C
first** (cheap to rule out), fall back to **Option A** if it's
Python-incompatible (matches the project's existing "scheduled
background work" mental model best), and treat **Option B** as the
fallback if A's cron granularity turns out to be too coarse for the
plan tier.

### 3e. `auto_apply` interaction

`maybe_auto_apply()` is called per-job today, best-effort, already
tolerant of partial runs (an exception on one job doesn't stop the
rest). Chunking doesn't change this -- a paused-and-resumed run just
means auto-apply for jobs in later chunks happens minutes/hours later
than jobs in the first chunk, which is already true of any single
long-running run today, just compressed into one invocation. No new
correctness risk here, flagging only so the founder can confirm this
timing gap is acceptable.

## 4. What this does NOT change

- The `POST /tracks/{id}/match` -> `202` -> poll
  `GET /tracks/{id}/match-status/{run_id}` contract stays identical
  from the frontend's point of view. `'paused'` is a new intermediate
  status the frontend would need to render as "still working" (same
  as `'running'`) rather than a new terminal state -- one small
  frontend change, not a redesign.
- `scripts/run_matching.py` (the founder's local CLI) is unaffected --
  it already runs the whole corpus inline with no time limit, since
  it's not bound by Vercel's function duration. No urgency to touch
  it, though it could optionally gain the same resumability for
  consistency later.

## 5. Open questions -- need founder decisions, not assumptions

a. **Which resume mechanism (3d)** -- spike Option C, or go straight to Option A?
b. **What's this project's actual Vercel plan/entitlements?** Needed
   for: cron minimum interval (3d Option A), and to sanity-check
   whether 300s is actually the ceiling everywhere or just what got
   accepted this one time -- no tool in this session can read plan
   details directly (confirmed while chasing the maxDuration failure
   in v42); this needs to come from the Vercel dashboard billing page
   directly.
c. **Chunk deadline value** -- 240s is a proposal, not a measurement.
   Needs one real timed chunk against production data to confirm the
   per-job cost assumption before this ships.
d. **Should `scripts/run_matching.py` (local, unbounded) keep existing
   as-is indefinitely**, or is the intent to retire it once the API
   path can reliably finish a full run on its own?

## 6. Suggested implementation order (once 5a/5b are answered)

1. Fix `JobRepository.list_all()` ordering (3a) -- small, safe,
   unblocks everything else, no behavior change for any existing
   caller since nothing currently depends on a particular order.
2. Add `resume_cursor`/`chunks_completed` columns (migration) and
   `'paused'` to whatever enum/check-constraint backs
   `matching_runs.status`.
3. Time-box `run_matching_for_track()` + wire `'paused'` into
   `get_running_run_for_track()`'s conflict check and the stale-run
   reaper.
4. Build the chosen resume mechanism from 3d.
5. Frontend: treat `'paused'` as a non-terminal status in whatever
   component polls match-status today.
6. Real end-to-end test against the full production corpus, the same
   verification discipline as v41's Jane track check (real DB query
   of the finished top-15, not just a green test suite).
