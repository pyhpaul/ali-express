# Captcha Diagnostics Design

**Date:** 2026-05-14

**Goal:** Add lightweight, persistent diagnostics that explain why captcha handling succeeded or failed during `preflight` and `detail` flows, without changing scrape control-flow semantics.

## Scope

This design only adds small, structured diagnostics around the existing captcha solver integration. It does **not**:

- change scrape state-machine outcomes
- add new business statuses
- add a standalone trace artifact
- broaden captcha coverage to new captcha types

## Why

The current solver integration is now functional, but post-run analysis still requires manual digging through:

- `run_state.json`
- `run_summary.json`
- `products.csv`
- ad-hoc local probes

The missing piece is a compact explanation of:

- where the captcha happened
- whether the solver actually attempted recovery
- whether the slider became ready
- why the attempt failed

This is meant to shorten future debugging loops without making the runtime noisier or more complex.

## Recommended Approach

### Option A: State files only

Write the latest captcha diagnostics into `run_state.json` and `run_summary.json`.

**Pros**
- smallest surface area
- persistent evidence in existing run artifacts

**Cons**
- terminal feedback remains opaque

### Option B: State files plus one CLI summary line **(recommended)**

Write the same diagnostics into state/summary and print one compact CLI line at the end of a run.

**Pros**
- keeps artifacts authoritative
- improves first-look operator feedback
- still small and non-invasive

**Cons**
- one more line in CLI output

### Option C: Separate `captcha_trace.jsonl`

Emit per-attempt events to a dedicated trace file.

**Pros**
- richest debugging evidence

**Cons**
- new artifact to maintain
- higher complexity than currently justified

## Chosen Design

Use **Option B**.

## Data Model

Add one optional diagnostic payload that captures the most recent captcha handling attempt.

### New state shape

Add a new optional dict field to `RunState`:

- `captcha_diagnostic: dict[str, Any]`

When absent or empty, no captcha diagnostic is available.

### Diagnostic fields

The payload stores only the latest meaningful captcha attempt and uses a stable small schema:

- `stage`: `preflight | detail`
- `solver_attempted`: `true | false`
- `slider_detected`: `true | false`
- `waited_for_ready`: `true | false`
- `ready_wait_ms`: integer milliseconds
- `result`: `solved | failed | skipped`
- `fail_reason`: optional string
- `page_url`: optional string

### Allowed fail reasons

Initial failure reasons are intentionally small and explicit:

- `slider_not_ready`
- `distance_not_ready`
- `drag_failed`
- `gate_not_cleared`
- `not_slider_gate`
- `exception`

These reason codes are descriptive enough for operator use, but narrow enough to keep behavior stable.

## Capture Points

### In captcha solver

The solver should internally determine the core attempt outcome:

- whether it waited for slider readiness
- whether slider DOM was ever detected
- whether the solve path was attempted
- why it stopped when returning `False`

This does **not** require changing the public scrape semantics. The solver can expose a small structured result internally, while existing orchestration can still derive boolean success/failure.

### In browser detail flow

When detail enrichment hits captcha, record:

- `stage = detail`
- the solver attempt outcome
- the blocked detail URL when relevant

If the solver succeeds, the diagnostic should still show that a captcha occurred and was solved.

### In session preflight flow

When session preflight classifies the page as `captcha_blocked`, record:

- `stage = preflight`
- solver outcome
- the current page URL

If the solver succeeds and preflight later returns `ready`, the diagnostic remains available as evidence that recovery occurred.

## Persistence

### `run_state.json`

Persist the full latest `captcha_diagnostic` payload in `RunState`.

### `run_summary.json`

Persist the same payload in condensed form under:

- `captcha_diagnostic`

This keeps the summary immediately useful without requiring the operator to open the larger state file.

## CLI Output

At the end of `ali_mvp scrape` and `ali_mvp resume`, print at most one extra line when a captcha diagnostic is present.

Example style:

```text
Captcha diagnostic: stage=detail result=failed reason=gate_not_cleared slider_detected=true waited_for_ready=true ready_wait_ms=900
```

Rules:

- print nothing if no diagnostic exists
- print exactly one line
- keep it flat and grep-friendly

## Behavior Constraints

This change must preserve all current behavioral guarantees:

- no new exit codes
- no new scrape statuses
- no changes to accepted product filtering
- no changes to cooldown logic
- no changes to resume semantics

This is observability only.

## Testing

Add tests in three layers.

### Solver tests

Verify diagnostics distinguish:

- waiting for slider readiness before solving
- failing because slider never became ready
- failing because distance never became usable
- failing after drag because gate was not cleared

### State/summary tests

Verify:

- `RunState` round-trips `captcha_diagnostic`
- `run_summary.json` includes the diagnostic payload

### CLI tests

Verify:

- a final captcha diagnostic line is printed when available
- no line is printed when absent

## Risks

### Risk: diagnostics drift from actual behavior

Mitigation:

- derive diagnostics directly from the solver/browser/session path that already determines outcomes
- avoid parallel ad-hoc logging logic

### Risk: too much detail too early

Mitigation:

- keep only one latest payload
- keep reason codes bounded
- do not add a separate trace file in this phase

## Success Criteria

This design is complete when:

1. a run that hits captcha leaves an explicit latest diagnostic in `run_state.json`
2. the same run exposes a compact diagnostic in `run_summary.json`
3. CLI prints one concise diagnostic line when available
4. no scrape control-flow semantics change
5. tests cover the new diagnostic contract
