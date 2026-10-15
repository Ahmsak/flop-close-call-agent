# Release audit — 2026-10-15

Decision: **GO for the reviewed integration into the actual default branch**, subject
to the final GitHub head/base and checks comparison. This is a source release, not
a declaration of live-testnet readiness or an operational deployment.

## Candidate and preservation

Repository: `Ahmsak/flop-close-call-agent`. GitHub reports default branch
`local/read-only-tooling`, base `c5d287e6d8a3b28ff496c52b777fe67f6bef139d`.
Starting integration head: `ae37080a7c214c8da955e6f8e886daa032b3fdbc`.
The candidate is that head plus the fixes and tests in the commit containing this
report. Final commit and merge IDs are reported separately; this document is not
rewritten merely to insert its own SHA.

The default base is an ancestor of integration. Audit ran in a detached isolated
worktree of the existing nested clone. Its Git metadata belongs to
`flop-close-call-agent/.git`; the parent `флоп/.git` was not used or changed.
No upstream update, Fold rewrite, rule change or history reset was performed.

The original clone remains on its prior integration HEAD with its dirty files:
`tools/README.md`, `tools/verify_public_snapshot.py`, and the local acceptance-note
append. Their bytes are preserved. The two tools changes are a local cryptography
substitution and associated instructions; neither is needed or included here.
The clean candidate continues to test the committed PyNaCl verifier.
Only the anonymized user-confirmation section was incorporated from the dirty
acceptance document, without copying private evidence or overwriting that file.

At comparison time the publication copy alone had `config.example.json`,
`docs/PUBLICATION_HANDOFF.md`, and the SUPERSEDED delivery guard/regression.
`durable.py`, `tests/test_delivery_once.py`, and acceptance documentation differed
from the operational sibling. All new audit fixes are publication-only. No runtime,
database, operational configuration or permission was copied or modified.

## Coverage and limits

| Area | Files and scenarios reviewed | Conclusion / boundary |
| --- | --- | --- |
| Mission | `mission.py`, `mission_guard.py`, `page_text.py`, `evaluation.py`, `verify_mission.py`; checkpoint completion, authorized resume, unknown response, exact quotes, corpus extraction, token accounting | Normal CLI uses `guarded_run` → enqueue/claim/reserve → `run` → action receipt → complete/outbox. Completed work returns its artifact; unknown calls are not replayed. Quotes and structural checks are independent code checks, not a proof of semantic accuracy. Legacy comparison bypass closed. |
| Persistence | `ops.Store`, `durable.py`; additive schema, source cursor CAS, event hashes, two workers, shared daily caps, lease fencing, failed completion transaction, restart | Existing SQLite and executor reused. Transactions preserve events/bookmarks and task/result/outbox consistency. SQLite errors propagate, not success. Tests use fresh synthetic databases, not the private operational database. |
| Discovery | `source_discovery.py`, `opportunities.py`, `jobs.py`, `agent.py`, source catalog and fixtures; unseen contest, mirror, changed deadline, outage, retained-window gap, server-provided next links | Catalog is supplemented by bounded intake. UNKNOWN remains visible; PAPER is not money; A/B/C rules remain separate. An announcement survives a rulebook outage. Separate registration/identity/submission/voting/trading/claim date claims retained. Coverage remains PARTIAL/HISTORY_LOST where appropriate, not a whole-market claim. |
| Execution | `ops.Operator`, `Technocore`, `sandbox.py`; exact envelope/grant, environment binding, pre-send reconciliation, lost reply and reward lookup | No owner key custody. Explicit grants bind request, environment and zero-spend scope. Only sandbox reward convention exists; no invented live settlement interface. Synthetic Ed25519 signatures and localhost HTTP are test fixtures, not FLOP actions. |
| Delivery | `durable.py`, `deliver_once.py`, `telegram_bridge.py`; exact owner, one-shot permission, wire marker, artifact hash, unknown reply, SUPERSEDED, safe receipt | Local state and delivery state separate. No real send or getMe during this audit. Future response capture tested with synthetic API fields and SQLite reopening; installed Hermes private APIs remain an integration dependency. |
| Entry/security | CLI paths, policy parsing, input-as-data, model command restrictions, HTML rendering, import side effects; all owned Python modules and examples | External text cannot choose an arbitrary shell tool, grant or filesystem path. CLI input/output paths are trusted owner arguments, not hostile multi-user interfaces. Imports of 23 modules made no network/process calls under guards. No paid fallback. Local filesystem tampering by another process with the same OS permissions is outside this threat model. |
| Close Call | `tools/contest_client/{observer,validation,__init__}.py`, `verify_public_snapshot.py`, `simulate_strategy.py`, `research_scenarios.py`, `audit_history.py`, `local_tests/` | Rollback, same-sweep conflicts, malformed time, exhausted iterators and after-final records covered. Authority/completeness stay UNCONFIRMED/PARTIAL; no promotion to VERIFIED. Full authoritative archives still absent from this checkout. |
| Frozen/upstream | `close_call_fold.py`, rules, scripts/build.py, scripts/verify.py, upstream tests, `sim/close_call_sim.py`, LICENSE/NOTICE | Frozen files and upstream history preserved. Simulation is upstream design evidence using synthetic prices; full expensive Monte Carlo suite was not rerun and is not a profitability forecast. Official Fold tests and own deterministic scenarios were run. |

## Findings and regressions

All line references below refer to this candidate (paths relative to repository root).
No open critical/high finding remains in the audited release scope.

| ID / severity | Location | Reproduction and consequence | Fix and regression |
| --- | --- | --- | --- |
| F01 HIGH | `flop-testnet-agent/evaluation.py:78` | Legacy `--run` called model providers directly without durable owner budget/reservations; historical permission closure did not gate this entry point. | Close `compare` before any preparation or model call. Historical log/quality readers retained. `test_legacy_comparison_cannot_bypass_durable_permission` asserts denial, no provider and no files. Future paired inference needs integration with the existing durable core, not re-enabling this bypass. |
| F02 MEDIUM | `flop-testnet-agent/mission_guard.py:38` | Exhaust budget after decision one; JSON contains an unissued IN_FLIGHT step and BLOCKED status. Task-scoped resume previously returned the old block forever. | Remove only an unissued step after explicit authorized resume, or repair from a durable CONFIRMED response. `test_budget_resume_only_unissued_step`; unknown-response resume regression confirms no repeat. |
| F03 MEDIUM | `tools/contest_client/observer.py:268` | Refresh an older sweep, or changed payload at the same sweep: prior latest observation was overwritten. | Serialize atomic promotion with an exclusive lock, compare sweep and canonical payload digest, preserve final records. `test_promotion_rollback_conflict_final_and_lock`; existing failed-refresh/atomic-write controls retained. Old same-sweep snapshots lacking a digest fail closed. A stale crash lock requires operator inspection; it is not silently broken. |
| F04 MEDIUM | `tools/contest_client/validation.py:9` | Pass a generator to validated replay: validation consumed it, leaving empty input to the Fold. | Materialize once, validate and replay identical events. `test_one_shot_iterator_matches_list`; existing after-final/gap/order controls pass. |
| F05 MEDIUM | `tools/contest_client/observer.py:34`, `tools/contest_client/__init__.py` | Numeric reference timestamp caused AttributeError instead of rejected/stale observation. | Reject non-string timestamps and fail stale in cached-client parsing. `test_numeric_reference_time_rejected_and_client_stale`. |
| F06 MEDIUM | `flop-testnet-agent/telegram_bridge.py:14` | Grant valid at outbox claim could expire during preflight and still reach the wire. | Recheck expiry in the wire transaction before marker/request. `test_grant_expiry_rechecked_at_wire_boundary` proves zero wire claim at expiry. Existing replay/scope/hash controls remain. |
| F07 MEDIUM | `flop-testnet-agent/telegram_bridge.py:31,60` | Prior success retained too little diagnostic evidence; malformed post-wire result could fall through an exception path reporting NOT_SENT. | Allowlist optional API evidence; malformed or missing response after a request remains UNKNOWN. `test_safe_response_and_optional_fields`, `test_safe_api_excerpt_persists_after_restart`, unknown/no-resend tests. Never retain raw body, token, headers, secret URL or document file_id. Missing optional sender/date/document fields do not reject otherwise confirmed success. No historical values reconstructed. |
| F08 MEDIUM | `flop-testnet-agent/mission.py:126` | Escaping a `javascript:` source URL did not prevent an active link in generated HTML. | Only HTTP(S) links without userinfo are active; all other source labels are escaped text. `test_render_does_not_activate_external_script_urls`. |
| F09 MEDIUM | `flop-testnet-agent/durable.py:36` | Malformed task allowlist string used substring membership instead of exact list entries; non-boolean sandbox flag was not rejected at policy read. | Validate list of nonempty strings and boolean flag, fail closed. `test_malformed_policy_cannot_grant_resume_or_delivery`. No operational config or limit changed. |
| F10 MEDIUM | `tools/requirements-verification.txt:1` | pip-audit flagged PyNaCl 1.6.0 twice for aliases of CVE-2025-69277 / GHSA-mrfv-m5wm-5w6w (bundled libsodium). | Pin only the indicated fixed PyNaCl 1.6.2. Re-run public-seed/tamper verification, all own tooling tests, and pip-audit. No unrelated dependency upgrade. No claim that the vulnerable custom point-validation function was invoked by this project. |

## Fresh checks

Tests run using Python 3.12 in an isolated audit venv, with declared verifier
dependencies installed. Initial pre-install local-tests collection failed because
PyNaCl was absent; this was an environment prerequisite, then resolved. Results
below are the subsequent complete candidate runs, not historical counts.

| Command / directory | PASS | FAIL | ERROR | SKIP | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| `python -m unittest discover -s tests -v` in `flop-testnet-agent` | 96 | 0 | 0 | 1 | 0 |
| `python -m unittest discover -s local_tests -v` at root | 53 | 0 | 0 | 0 | 0 |
| `python -m unittest discover -s tests -v` at root | 18 | 0 | 0 | 0 | 0 |
| `python scripts/build.py --check` | current | | | | 0 |
| `python scripts/verify.py` | 15 artifacts | | | | 0 |

Total: **167 PASS, 0 FAIL, 0 ERROR, 1 SKIP** (168 discovered).
The skipped regression requires private saved 34-offer SQLite evidence. It was
not copied, and that historical replay is not claimed as performed. Synthetic
discovery/executor positive and negative cases are separate tests.

`test_release_flow.py` uses actual Store, Durable, deterministic invoice worker,
quality validator and outbox in fresh subprocesses. It persists a synthetic input
event, exits with injected code 17 after the calculation receipt, resumes after
lease expiry, reconciles a simulated lost delivery response, then restarts again.
Observed output:

```text
RELEASE_FLOW_OFFLINE: events=1 tasks=1 calculations=1 notices=1 fixture_sends=1 restart=preserved live_calls=0 user_read=UNKNOWN
```

The artificial event's input is checked against the task's input. Event, task,
action and notice remain unique across reopening. Fixture SERVICE_ACCEPTED is
explicitly simulated and does not update historical live acceptance.
Normal model-mission integration is separately exercised with a scripted provider,
not with another live model call. Import smoke: 23 modules, zero network/process
calls. `git diff --check` passes.

## Secrets and dependencies

Existing `tools/audit_history.py`: 12 reachable commits / 133 unique historical
blobs before this release, zero findings. Additional local scan checked all
reachable refs and candidate files for private-key blocks, GitHub/API/Telegram
tokens, authenticated URLs, private delivery identifiers and forbidden paths.
One deliberately synthetic `example.com` credential-URL test was manually
classified as a negative control. No operational state, token, receipt or private
material is included. This is a local pattern/path/manual review, not a formal
proof that arbitrary secrets cannot exist. No source code was sent to a scanner.

pip-audit 2.10.1 queried its public vulnerability service with package names and
versions only. First result: two aliases for the one PyNaCl advisory; after the
targeted fix: exit 0, no known vulnerabilities in the checked version set:

```text
PyNaCl 1.6.2; cffi 2.1.1; pycparser 3.0; cryptography 50.0.2; numpy 2.5.1;
httpx 0.28.1; httpcore 1.0.9; anyio 4.14.2; certifi 2026.7.22;
idna 3.18; python-telegram-bot 22.6
```

The audit used `--no-deps --disable-pip` on that explicit set, not the whole shared
environment. Requirements ranges, other possible resolved versions, Hermes itself,
Codex CLI and the complete operational transitive environment are **NOT CHECKED**
by this dependency scan. Installed Hermes adapter compatibility is not revalidated
live by passing unit tests. Dependency hashes are not yet locked for the component;
pinning the operational environment is a deployment follow-up, not grounds to
silently modify it during this release.

## Remaining limits and readiness

- Discovery remains bounded to published interfaces/windows, 8 reads / approximately
  40 seconds / 512 KiB per response and 16 visited URLs. It does not guarantee all
  opportunities; no email/X connection or complete archive is inferred. Pagination
  tests cover explicit server links, cursor transactions and overlap, not every
  adversarial multi-page API behavior.
- LOW backlog: legacy opportunity timestamps without a timezone are interpreted
  by Python's host-local timezone. New unreviewed date claims stay visible with
  reward/eligibility UNKNOWN and cannot alone make a candidate executable. Require
  explicit timezone normalization before authenticating a new live contract.
- LOW backlog: old `verify_public_snapshot.py` CLI expects local historical exports
  absent here. Its signature function and negative controls were tested; CLI full
  export aggregation is not claimed. The active observer has stronger phase guards.
- Deterministic quote matching and topic coverage cannot establish semantic truth.
  A result may need owner review; no self-rated model score is treated as settlement.
- Retained UNKNOWN operations require authoritative reconciliation, never blind retry.
  A corrupted/missing checkpoint or crash lock can require manual recovery; no
  destructive automatic repair is introduced.
- Prior real model and Telegram checks are historical only. The user subsequently
  confirmed message visibility; single-delivery END_TO_END_ACCEPTANCE is closed by
  that confirmation. MESSAGE_NOT_SEEN history is retained. File opening/reading
  remain UNKNOWN. Original sender/date/raw API evidence is still unavailable.
- All one-shot model/delivery permissions remain closed. This audit makes zero
  live model calls, Telegram sends or FLOP actions; no cron or permanent delivery.
- Working installation updated: **NO**. New code and SUPERSEDED guard require a
  separately authorized deployment preserving its existing private state.

## Merge gate and repeatability

GitHub currently reports no rulesets, no branch protection and no Actions workflows
for this repository. No setting was changed or bypassed and no runner was started.
Recheck exact head/base and check-runs immediately before the authorized normal
merge. Test the PR's resulting merge tree, preserve both ancestries, and compare
post-merge default-branch tree with that tested tree. A changed ref or failed required
check stops the merge; this report alone does not authorize untested future commits.

Reproduce core acceptance from `flop-testnet-agent/` with the declared dependencies:

```powershell
python -m unittest discover -s tests -v
```

This command uses synthetic databases/providers and localhost fixtures; it does
not run mission against operational state or send a real notification. See
[components](COMPONENTS.md) for the source/deployment boundary.
