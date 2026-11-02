# Automation acceptance — 2026-10-15

## Workspace and prior implementation

Target: `C:\Users\lenin126\Documents\ChatGPT\флоп\flop-testnet-agent`.
Git root is its parent `флоп`, branch `master`; HEAD does not exist (unborn repository).
The three root directories were already untracked. No staging, commit, push, new
repository, credentials, global configuration, cron or other project was changed.
No applicable AGENTS.md was found in the target or checked ancestor directories.
README, modules, tests and recent mission/comparison results were inspected.

| Requirement | Already present | Added / remaining |
|---|---|---|
| Discovery | A/B/C, official-source intake, historical replay, cache | Atomic bookmarks; server-provided pagination; retention-gap indication |
| External actions | ops.Operator write-ahead SENDING, grants, reconciliation | Preserved unchanged; generic new live APIs not introduced |
| Useful local work | invoice_totals_v1, mission read/measure/write, independent quote checks | Durable task wrapper and copied-state crash demonstration |
| Persistence | SQLite events/operations/metadata; mission JSON artifacts | Additive automation_schema=1 migration, tasks/actions/reservations/outbox/health |
| Notifications | Source notice journal | Separate result outbox; sandbox delivery and reconciliation; no live sender |
| Budgets | Existing zero real-money budget and per-run limits | Atomic task-wide and UTC-day reservations, including unresolved requests |

Studied [Building effective agent automations](https://claude.dev/blog/building-effective-agent-automations/).
Applied the separation of owner policy from mutable state, source bookmarks and
explicit uncertain delivery. Read checkpoints commit independently of delivery so a
messaging outage cannot lose read events. No deployment instructions were executed.
Unlike the article's simplified closed-item handling, closed opportunities remain
historical records; closure alone is not treated as resolution.

## Code changes

- `durable.py`: additive transactional migration in the existing Store; source page
  plus cursor in one transaction, versioned event deduplication, leased tasks and
  fencing, pre-call reservations, uncertain actions, atomic completion plus outbox,
  bounded notification retries for **definitely not sent** responses, lookup recovery.
- `mission_guard.py`, `mission.py`: ordinary mission CLI uses the durable boundary.
  Successful model responses are recorded before the JSON checkpoint. An unresolved
  intent blocks re-execution; a saved response can repair an interrupted checkpoint.
  Existing completed missions continue to reuse their immutable inputs/results.
- `source_discovery.py`, `jobs.py`: real-source snapshots/bookmarks commit together;
  GitHub follows only supplied `rel=next` links within existing request/size limits.
  Pending pages are resumed with root overlap. Technocore retains its existing
  documented 200-message window: missing sequence ranges or changed generation are
  `HISTORY_LOST`, not evidence that no activity occurred. A bounded room window stays
  PARTIAL even if every attempted HTTP request succeeded. Deadline categories and
  explicit season identifiers are retained when present; absent fields stay unknown.
- `automation_demo.py`, `run.ps1`: copied-state safe demonstration and local health.
- `tests/test_durable.py`, `tests/test_automation_integration.py`: fault injection
  using actual Store, task machinery, mission loop, discovery and worker modules.

No production policy limits were raised. `config.json` has no separately authorized
daily model allowance. New guarded model missions therefore return BLOCKED until an
owner supplies a policy; no permissive daily default is inferred from old trials.
The demonstration uses a **fixture policy only in its isolated directory**, with
2 local units/day and zero model/infrastructure/FLOP/PAPER units. No free-model label
is interpreted as a monetary authorization. Unknown cost remains null.

## Acceptance results

Full target-project suite: **77 tests PASS**, 0 FAIL, 0 ERROR, 0 SKIP.
No tests or changes were made to the other project during this stage.

| Failure / requirement | Result | Evidence |
|---|---|---|
| Repeated source outage, preserved cursor, recovered/lost history | PASS | test_source_outages_recovery_and_retention_loss; test_technocore_retention_loss_is_explicit_and_snapshot_committed |
| Contest announcement retained while rulebook unavailable | PASS | test_announcement_preserved_while_rulebook_down_and_closed_history |
| Crash between page receipt and cursor commit | PASS | test_atomic_page_cursor_crash_and_overlap, transaction rollback |
| Lost external response, reconciliation without second spend | PASS | test_lost_action_reply_reconciles_without_second_send; existing ops loss/restart tests |
| Notification lost, task result retained | PASS | test_notification_loss_keeps_work_and_does_not_repeat and demonstration |
| Two workers claim one task | PASS | test_two_workers_atomic_claim; fencing test |
| Restart after completed calculation before task completion | PASS | separate process exits 17; next process reuses confirmed action receipt |
| Model mismatch / auth error, no fallback | PASS | policy/model test; guarded mission auth-failure test (model double) |
| Source instruction cannot change budget/provider or send secrets | PASS | injected input has no authority; executable tool allowlist and policy checks |
| Local output distinct from settlement/reward | PASS | test_local_quality_is_not_network_settlement_or_health |
| Daily cap across retries/new processes/concurrent reservations | PASS | budget shared-connection test and parallel reservation test |
| Expired opportunity retained for later result/claim review | PASS | closed-history integration test; existing dated Sonnet/Close Call regressions |
| Independent life/read/model/work/delivery marks | PASS | health marks test and demonstration output |
| Migration on copied existing state | PASS | exact old event (seq,hash) prefix and operations unchanged; SQLite/hash-chain checks pass |
| Live testnet participation / real Telegram delivery | SKIP (not authorized/implemented) | No external operation attempted |

The SKIP entries above are acceptance activities, not skipped unittest cases.
Historical contest fixtures do not prove timely detection in the past.

## Actual useful session and recovery

Evidence directory: `runtime/automation-acceptance-final-20261015/`.
The session selects the preconfigured existing invoice workload. Input is the existing
`examples/job.json` sample, **not a real paid customer order**. Purpose: produce a
per-SKU invoice reconciliation artifact. LLM is NOT USED, not silently simulated as
an intelligent live agent. `jobs.solve` performs the calculation; a separate grouping
of CSV rows using Decimal verifies each SKU and the exact SKU set.

Observed output:

```text
environment: LOCAL_SANDBOX
migration_preserved_old_events: true
migration_preserved_operations: true
fault: process exit 17 after calculation receipt, before completion
task_state: CONFIRMED
totals: A=9.00, B=4
TASK_OUTPUT_VALID: true
calculation_actions: 1
delivery_before_reconcile: UNKNOWN
delivery_after_reconcile: SERVICE_ACCEPTED
simulated_send_count: 1
user_read: UNKNOWN
NETWORK_SUBMISSION_CONFIRMED: NOT_ATTEMPTED
NETWORK_SETTLEMENT_CONFIRMED: UNKNOWN
REWARD_ELIGIBILITY_CONFIRMED: UNKNOWN
```

The calculation receipt survives the intentional process exit. After the simulated
lease expires, another process reuses that receipt, verifies quality, and commits
completion and a pending notification atomically. The fixture delivery service writes
its receipt and then loses the response. A lookup confirms service acceptance without
another send or another calculation. This is not a Telegram receipt or FLOP settlement.

Artifacts: `invoice-result.json`, `acceptance.json`, copied `state.sqlite`, fixture
`fake-service.json`. One reserved local unit of the fixture daily limit of two;
zero model requests, purchases, registrations, signatures or live messages.
Local CPU/storage cost is not priced; monetary cost remains unknown/null, not a
fabricated financial zero. No exactly-once claim is made for external services.

## Reproducible commands

From the target project directory (the existing PowerShell launcher finds Python):

```powershell
.\run.ps1 automation-demo
& "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" -m unittest discover -s tests -v
& "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" automation_demo.py --health runtime/automation-acceptance-final-20261015/state.sqlite
```

The demo creates a fresh isolated directory each invocation and refuses to replace an
explicit existing output directory. It starts finite child processes only; no daemon.
Health is independent of LLM and reports separate marks. A health check on the same
laptop cannot detect that laptop being powered off. No external monitor is deployed.

## Readiness and remaining boundaries

| Status | Value | Evidence / limits |
|---|---|---|
| DISCOVERY_READY | PARTIAL | Bounded official intake, cursor transactions, late overlap and explicit gaps tested. Technocore history cannot be reconstructed beyond retention; complete rulebook/issue-closure adapters remain absent. |
| DURABLE_EXECUTION_READY | PARTIAL | Local worker and existing ops recovery tested; ordinary mission CLI guarded. New paid/provider APIs have no authorized adapters; task elapsed-time enforcement still relies partly on existing mission wall-time/process timeout rather than a complete cross-process time ledger. |
| USEFUL_WORK_LOCAL_READY | YES | Existing invoice worker produces independently checked artifact and survives real process exit; scope is local sample data. |
| NOTIFICATION_RECOVERY_READY | PARTIAL | Durable outbox, backoff and lost-response lookup pass with fixture. No real channel permission, credentials or delivery API. |
| LIVE_TESTNET_READY | NO | No new official live API, onboarding, settlement or reward eligibility validated. No live operation permitted in this stage. |

Additional explicit limits:

- A closed issue needs a dedicated evidence review to distinguish resolved, duplicate,
  rejected or unexplained closure; an issue/PR crawler was not invented here. Existing
  unknown-format records stay visible. Result/claim tracking is a review flag, not a
  claim that a complete live claim scanner exists.
- Discovered candidates still require a reviewed task contract/worker; arbitrary
  announcements are not automatically converted into executable tasks.
- UTC is used for stored clocks and daily counters. No new scheduler/timezone setting
  or chat delivery formatter was installed. Unix timestamps in raw evidence remain UTC.
- The owner policy file is separate from task/source memory, but the same OS user can
  edit both code and policy. This is a trusted-owner boundary, not OS isolation against
  a malicious local administrator. The model cannot change policy through these tools.
  Existing Codex CLI hardening is not claimed to be a secret-isolating container.
- Source metadata may lack publication time or separate deadlines; null is preserved.
  Repository list pages can change during pagination; a stable exhaustive snapshot is
  not promised. Root overlap and persistent candidates reduce, not eliminate, gaps.

## Git

`git diff --stat` is empty because the repository has no HEAD and all project files
are untracked. `git status --short` at the root still lists:

```text
?? close1-evidence-20261004/
?? flop-close-call-agent/
?? flop-testnet-agent/
```

Pre-change copies of target top-level modules are retained in
`runtime/automation-before/` for a no-index comparison. Empty tracked diff does not
mean no files changed. No commit or push was made.


## Ordinary mission acceptance — 2026-10-15

This stage used ordinary `run.ps1 mission --read-only`, not automation-demo.
`mission.main` calls existing `jobs.discover(Technocore)` then `source_discovery.enrich` /
`collect`. Raw responses, source bookmarks and event versions are stored by
`Durable.page` in the existing runtime/state.sqlite. `mission.corpus` extracts source
text, and `mission_guard.guarded_run` enqueues the normal evidence-synthesis task.
`Durable.block` atomically retains BLOCKED and a PENDING local outbox entry.
The normal permitted model path uses `claim` -> guarded `decide` -> `reserve` ->
`action_result` -> `mission.run` quality check -> `complete` (result and outbox atomically).
Both normal mission and automation-demo share Durable/Store, leases, intents, budget
reservation and outbox. Their content workers differ. No second executor/database.

Fixed: authorization check previously preceded enqueue, losing blocked tasks; JSON
LOCAL_COMPLETE previously bypassed SQLite completion/outbox repair. Completed SQLite
work now refuses execution if its completed checkpoint is missing. No model fallback.

Live read at 2026-10-15T03:37:20.279505Z:
- Technocore tclk-offers: one 200-message window, seq 22572848..22573047, PARTIAL.
- GitHub flop-labs repository listing: 7 repositories (limit 100), no next-page link.
- flop.finance /, /testnet/, /airdrop/ and Close Call / Sonnet GitHub READMEs: READ.
- Six official HTTP reads plus one Technocore read. Existing limits: 8 public reads,
  40-second dispatch budget, 512 KiB per public response; room 2 MiB / 8 seconds.
- No unavailable source in these reads. No email/X connector used. Not all FLOP markets.
- Three MATERIAL_UPDATE notices for the three finance pages; no NEW contest notice.
  This proves changed extracted materials, not a newly opened remunerated opportunity.
- Stages: 13 DISCOVERED, 2 HISTORY, 1 PREPARATION, 8 REJECTED. Closed contests stayed HISTORY.
- Selected preparation candidate flop-testnet-agents requires settled_inference worker,
  published onboarding, verified eligibility/result contract/cost bound. No executable
  paid task or confirmed allocation/payment was established.

Task: 8ce2960265e22fcdaac119cd472323ea4ce756f041c374e4de16910e81a26adc
Outbox: 02743b9b33f8f29b546e95316a7d0c3125d067c4ae5549cc1be76a587bea10a9
Result BLOCKED: LLM_DISABLED; evidence synthesis requires a model. Existing
invoice_totals_v1 worker cannot perform synthesis. No model content was fabricated.
Action IDs: none (zero reservations/executions). Task attempts: 0. Outbox PENDING,
attempts 0, DELIVERY_NOT_TESTED; no SERVICE_ACCEPTED claim.

Second invocation was a new OS process at 03:37:42.925198Z. It fetched another room
window and used the six cached HTTP sources (zero additional public-page reads).
No new material notices. Durable events grew 206 -> 238 with new room messages;
tasks 1 -> 1, actions 0 -> 0, outbox 1 -> 1. IDs above unchanged. Immutable mission
inputs are pinned per directory; later fetched data is saved separately and is not
claimed analyzed by the old task. A new mission over later inputs needs a new directory.
Raw intake files and sanitized review-summary.json are in runtime/mission-readonly-20261015.

Tests: 80 passed, including no-model repeat with database reopen, retained zero-budget
task/outbox, completed JSON -> SQLite repair without model, and existing completed-task
no-repeat, leases, action ambiguity, source failure last_success and atomicity tests.
These successful completion cases are SANDBOX/SCRIPTED, not live model execution.
Real-34 regression uses private local history; review archive intentionally lacks the
DB, so this one test explicitly skips there. Remaining tests remain available.

Readiness remains PARTIAL. Live model, live delivery and live testnet are NOT TESTED.
A blocked task has not produced a validated useful artifact. Budget/permission changes
need owner authorization; blocked tasks are retained, not automatically reauthorized.
Model calls, delivery, signatures, registrations, spend, cron and external writes were
not used and still require their separate permissions.

Git root: parent флоп; .git is parent флоп/.git, not inside this project. HEAD absent.
No parent/neighbour modifications, staging, commit or push. The review ZIP contains
only allowlisted project code/tests/instructions plus sanitized acceptance summaries.
It excludes operational config, environment files, SQLite, private logs, caches and
neighbours. It is NOT a full working-state backup. Manifest lists SHA-256 for all
payload members; a sidecar hashes the ZIP. Public synthetic test vectors are test
fixtures, not owner credentials. No operational identity/key material is exported.

Repeat from the project directory:
`./run.ps1 mission --read-only --run runtime/mission-readonly-20261015`

## Authorized saved-task model execution — 2026-10-15

Owner explicitly requested model analysis of the saved task. Added explicit
--resume-blocked with a task-scoped owner policy allowlist and a regression test.
The saved task
resumed from BLOCKED and is now CONFIRMED. Existing ChatGPT login / gpt-6.1-sol
performed two real calls in 33.578 seconds. Provider reports 30,556 input tokens,
1,042 output tokens and a reasoning_output_tokens field totaling 27. No price inferred.

Result: runtime/mission-readonly-20261015/result.html and brief.json; six claims
with exact quotes pass the existing validator. This historical evidence brief is
not proof of current eligibility, settlement or semantic correctness.

A separate process restart returned LOCAL_COMPLETE without new calls: task attempts
remain 1, both action IDs remain CONFIRMED and provider log hashes are unchanged.
Evidence: runtime/mission-readonly-20261015/model-restart-verification.json.
Two local outbox records remain PENDING with zero attempts (previous blocked notice
and completion notice). No delivery. Temporary model allowance restored to the
previous zero-budget configuration after execution. 81 tests passed before live run.

The completed changes are now synchronized for publication in integration/testnet-agent.
This publication does not run mission or extend model authorization. Runtime evidence
and the generated brief remain only in the original operational installation.

### Publication verification of this update

Fresh tests in the publication copy: 81 discovered, 80 PASS, 0 FAIL, 1 SKIP
(15.291 seconds). The skipped test needs the private saved 34-offer SQLite history;
that history was not copied, and its replay was not verified in this run.
Model responses in tests are scripted fixtures; no live LLM calls, mission launches,
live delivery or FLOP operations were performed during publication. Existing model
allowance remains closed; neither configuration nor limits were copied or changed.
Close Call checks: 18 PASS, generated files current, 15 manifest artifacts verified.
Only reviewed component changes are staged; prior tools/ changes remain local.


## Telegram delivery preflight — 2026-10-15

One delivery was authorized subject to confirmed private owner binding. Existing
completed task and completion outbox were found; the older BLOCKED notice was left
untouched. Artifact digest matched the stored result. At this initial preflight stage
the executor was sandbox-only; no live outbox extension had yet been activated.

Existing Hermes configuration contained an allowed numeric home chat. Read-only
Telegram getChat confirmed a private chat, but its authoritative username differed
from the requested owner username and the local directory label. Delivery stopped:
NOT_SENT, zero send requests, no message_id, USER_READ UNKNOWN. An owner-confirmed
mapping for the configured numeric chat is required before any later authorization.
No bot, gateway, webhook, model allowance or schedule was changed.

At this initial stage telegram_bridge.py provided only a reusable read-only preflight.
Tests reject username/ID/allowlist mismatches, groups and display-name
matches alone. Private diagnostic evidence is only in operational runtime. One-time
delivery permission CLOSED; task remains CONFIRMED, both outbox entries unchanged.
No mission reexecution, new LLM calls, commit or push. These delivery-specific files
and this section are synchronized in both copies; the working installation stays
in the original sibling directory.

Delivery-stage local suite: 83 tests PASS. Separate process reread confirms task
CONFIRMED/attempts=1, completion outbox PENDING/attempts=0/receipt=null and
unchanged two prior model actions. No sender rerun or additional network send.


## Owner-confirmed Telegram delivery — 2026-10-15

Owner resolved the username mismatch and confirmed the configured private account.
Read-only getChat then verified numeric ID, private-chat type, allowlist and username.
Exactly one saved HTML document with a historical-material disclaimer was accepted
by Telegram with a message_id. Receipt, numeric recipient and grant remain private
in operational runtime/SQLite. USER_READ remains UNKNOWN; no exactly-once guarantee.

Existing Durable.deliver now supports a separate exact one-shot delivery grant bound
to task, completion notification, recipient, username, artifact path/hash, expiry
and one wire request. An atomic transaction claims SENDING and closes permission
before calling the installed Hermes adapter. A second SQLite wire claim prevents
repeat requests across processes. HTTP retries and redirects are disabled for sends;
all message sends except the scoped document are blocked at the request boundary.

First outbox invocation was NOT_SENT with requests=0: the installed Hermes caption
extension list excluded HTML and attempted a separate text message, blocked locally.
An isolated-process HTML-caption compatibility adjustment fixed this without editing
Hermes files or gateway settings. An explicit proven-NOT_SENT recovery preserved the
first receipt in the journal and used a new scoped grant; no automatic retry occurred.
Final outbox invocation count is 2, but actual Telegram send requests is exactly 1.
Unknown outcomes and any existing wire claim prohibit this local-block recovery.

A new process read the stored SERVICE_ACCEPTED receipt and invoked the sender path
with a transport that raises if called: no send occurred. Original task/result,
two previous model actions, config hash and old BLOCKED notice remained unchanged.
All one-shot permissions CLOSED. No LLM calls, mission reexecution or FLOP operations.
88 local tests PASS, including receipt persistence, lost reply, no resend, scope/hash
checks, and explicit local-only recovery. Both source copies are synchronized for
these delivery files; no commit/push or operational installation migration.

## Delivery publication and stale-notice regression

Published delivery support comprises durable.py, telegram_bridge.py, deliver_once.py,
synthetic delivery/owner-binding tests and this anonymized acceptance history.
No owner chat ID, token, operational grants, receipts, runtime or generated result
is included. The previous live check is historical evidence, not a new delivery.

The live completion-only gate already rejected blocked notifications. The shared
sandbox path lacked an explicit obsolete-notice guard. Durable.deliver now identifies
the exact pending BLOCKED notice by its stable key and CONFIRMED parent task, then
sets only that notice to SUPERSEDED inside the claim transaction. It retains the
original reason, receipt and attempt counter and records notification_superseded.
It never calls the transport for this notice. Already-sent or uncertain notices are
not rewritten; unrelated notifications and completion notices are untouched.

Regression: test_completed_task_block_notice_superseded_without_touching_others
creates a blocked task, completes it, rejects sending the stale notice, and reopens
SQLite to verify the guard persists across restart. It asserts all other notices
are unchanged and the superseded event appears once. No live network is used.

Fresh publication-copy suite: 89 discovered, 88 PASS, 0 FAIL, 1 SKIP (16.803 seconds).
Skip: private saved 34-offer regression, whose operational SQLite was deliberately
not copied. Close Call: 18 PASS; generated files current, 15 manifest artifacts
verified, Fold/manifest unchanged. New live LLM calls and Telegram sends: zero.

This new stale-notice guard was added only in the publication clone per scope.
The operational sibling installation and its database/configuration were not modified
or switched; deploying the new guard there is a separate synchronization step.
Model/delivery grants remain closed. Existing tools/ changes are outside this commit.


## User-confirmed delivery acceptance

The user subsequently confirmed that the previously delivered message is visible
in the Hermes Agent chat. Single-delivery end-to-end acceptance is CLOSED_BY_USER_CONFIRMATION,
limited to message visibility. Opening and reading the attached file remain UNKNOWN.
The earlier MESSAGE_NOT_SEEN report is retained as historically valid; the new
confirmation resolves it without deleting or rewriting the earlier evidence.
SERVICE_ACCEPTED and the service receipt are unchanged. Private confirmation and
receipt details remain only in operational runtime/SQLite.

Separate logging limitation remains open: the original Telegram response, result.from
and result.date were not retained. No missing historical fields were reconstructed.
No resend, model call, mission execution, cron, permanent delivery, commit or push.
One-time delivery and model permissions remain closed.


## Release-audit follow-up (offline only)

See [RELEASE_AUDIT](../../docs/RELEASE_AUDIT.md) for the fresh candidate tests.
Future Telegram attempts retain an allowlisted response excerpt, if present:
HTTP status, ok, message ID, sender ID/username, chat ID/type, service date and
file name/size. Missing optional metadata does not invalidate an otherwise
confirmed response. No historic receipt was repaired or recreated. The old
logging gap remains a limitation of the prior delivery.

Grant expiry is checked again at the wire claim. Malformed post-send responses
stay UNKNOWN. The completed-task SUPERSEDED regression remains in place.
Only explicitly authorized budget-blocked steps with no action intent may be
resumed; UNKNOWN actions are not replayed. The old standalone paired-evaluation
live path is closed because it predates durable permissions. Saved-log auditing
still works. These changes are published source only, not an operational upgrade.
User confirmation closed single-message visibility acceptance; file opening and
reading remain UNKNOWN. Model and delivery permissions remain closed.

## P0-B: public gateway discovery — 2026-11-02

Development worktree only: flop-testnet-agent-dev-f4a19e0, branch
codex/p0-a-f4a19e0, base f4a19e06808b4e92d3bbcae4ee2593f351b9d6d4.
No deployment or change to the operational sibling installation.

Added flop_gateway.py and the existing CLI's gateway-models command.
Only a fixed public GET https://api.flop.network/v1/models is available.
No method/URL/body/credential injection surface, proxy credentials, redirects,
automatic retries, signatures, wallet operations or inference. No SDK installed.
The devnet profile is not verified chain identity; testnet profile is blocked.
JSON/schema validation covers the discovery subset; extensions and prices are
discarded, and no receipt/settlement validation is claimed. Responses are capped
at 512 KiB; socket-operation timeout is 8 seconds, not a total DNS/stream deadline.
Failures retain safe local reason codes and HTTP status, not remote error bodies.
No pagination follow-up. Empty listing is not proof of absence of inference supply.

Default CLI path opens neither private configuration nor SQLite. Optional explicit
--gateway-journal uses an existing Store and records one evidence event; it never
initializes a database. Existing --output writes JSON when explicitly requested.
The smoke used only --output, not --gateway-journal.

Offline suite: 111 discovered, 110 PASS, 0 FAIL/ERROR, 1 SKIP, 19.463 seconds.
All previous 96 passing tests remain passing; 14 new tests cover transport scope,
errors, redirects, schema/size validation, profiles, CLI isolation and journal
persistence. Skip remains the private 34-offer replay; no private database copied.
The first run had a new test asserting an instance where build_opener accepts a
handler class. Corrected that test assertion; the full second run passed.
Synthetic temporary stores, loopback fixtures, inherited external-network and
non-Python-subprocess blocking, and bytecode-disabled execution were used.

One live adapter invocation, one request attempt, HTTP 200, one returned model:
qwen/qwen2.5-0.5b-instruct. No retry or redirect request.
Result: status=OK, network_profile=devnet, network_identity_verified=false,
testnet_ready=false, inference_available=UNKNOWN, execution=EXECUTION_DISABLED.
Response SHA-256:
454d3df1bc8ba44034f82a0aa47df5dcad5a57cfa5402a449a9b37e3ee4e2457
This proves catalog retrieval only, not inference access, metering or settlement.
Local evidence is outside Git under deployment-private/p0-b-20261102/
(gateway-smoke.json and offline-tests.txt); no operational receipt is published.

Git diff --check passed; changed code, tests and documentation were reviewed for
credentials/private identifiers. Existing P0-A AGENTS/RUNBOOK additions retained.
No operational SQLite access, model call, Telegram send, faucet, signed request,
transaction, permission change, scheduler, commit or push. No runtime/config
created in the development component. Stop after P0-B.

Next authorized stage needs network/account admission, scoped inference authority,
monetary/compute/fee caps, durable idempotency and correlation, live reconciliation,
and verified receipt/finalized settlement evidence. A 200 model list grants none.
## P0-C: provisional durable inference preparation (offline only)

Extended the existing Durable class and existing Store with additive
automation_inference storage. No second database, executor or network sender.
prepare_inference binds task/slot to immutable operation/idempotency identity,
session correlation, network, model and canonical-request fingerprint.
Same-slot changed input is rejected; a duplicate returns its original ID.

Local state: PREPARED -> AUTHORIZED -> SUBMITTED -> UNKNOWN or verified terminal
CONFIRMED/FAILED. The submission transition commits BEFORE any future wire call;
the current implementation performs no wire call. After an uncertain attempt,
restart cannot authorize a resend. Only trusted offline reconciliation can resolve
UNKNOWN, with identity, finality, closed escrow and bounded actual-cost checks.
Optional/provisional request/channel/transaction/receipt references are recorded
with terminal evidence; these are not asserted official FLOP API contracts.

Money is nonnegative arbitrary-precision integer units, stored as decimal TEXT.
Floats/bools/strings are rejected at monetary inputs. BEGIN IMMEDIATE covers shared
daily/session reservation and journal events atomically. Reservation conservatively
adds inference, escrow and fees. Outstanding holds survive day boundaries; settled
actual costs count on reconciliation day and across the lifetime of the session.
UNKNOWN never releases money. Confirmed cap breaches freeze new reservations in
the affected network/unit domain. Failed work may still have confirmed fees.
Terminal release plus actual spend and evidence event are one transaction.

Fresh final suite: 130 discovered, 129 PASS, 0 FAIL/ERROR, 1 SKIP (21.374 seconds).
All previous 110 passing tests remain passing; 19 inference tests added.
Skip remains the private 34-offer replay; no private database copied or opened.
Tests cover additive/repeated migration, identity collisions, exact large units,
component/day/session caps, concurrent connections, stale/future prices, scope,
unknown evidence, terminal release, rollback on event failure and real child
process os._exit before/after a synthetic external effect. Restart attempts are
blocked without repeating that effect. All data/identities are synthetic.
Inherited test audit hooks blocked external network and non-Python subprocesses;
loopback legacy tests remain allowed. Full log: deployment-private/p0-c-offline/tests.txt.

git diff --check passed; changes scanned for private identifiers/key/token patterns.
P0-A/B changes preserved. Only durable.py, tests/test_inference_durable.py, README.md
and this report changed for P0-C. No runtime/config was created in this worktree.
Working installation and private SQLite were not opened or changed. No real model,
Telegram, gateway POST, faucet, wallet, signature, transaction, SDK, cron, commit/push.

Limits: sandbox policy and trusted local reader only. No official quote verification,
live receipt verifier, live lookup, signer or send/replay implementation. Expired
unsubmitted authorization holds remain reserved; cancellation/repricing is not
implemented. No exactly-once delivery guarantee. Session IDs and unit domains must
come from trusted orchestration. Existing model missions do not route to this
provisional ledger. Deployment and any live execution require a separate stage.
Stop at P0-C; P0-D/P1 not started.

## P0-D: offline FLOP inference evidence (2026-11-02)

Implemented in flop_evidence.py and Durable.reconcile_evidence using the existing
Store metadata and journal transaction. No additional database, executor, operation
states or migration. Optional genesis is pinned in new operation specs and checked
against policy; legacy operations without genesis are UNVERIFIABLE, not upgraded.

Evidence levels are separate from operation states: GATEWAY_ACCEPTED and
INFERENCE_COMPLETED are GATEWAY_REPORTED observations. The operation remains UNKNOWN,
held reservation is unchanged, and confirmed spend is not inferred. SETTLEMENT_FINALIZED
is intentionally unreachable: independent cryptographic finality verification is
UNSUPPORTED. A claimed finalized=true, transaction hash or forged receipt never
releases money. The existing P0-C terminal reader remains a trusted sandbox test seam;
the offline reader cannot be used through that seam.

Official sources reviewed (bounded public documentation/package reads only):
- https://docs.flop.network/docs/sdk-references
- https://docs.flop.network/docs/send-to-specific-miner
- @flop-labs/contracts 0.1.1, package/dist/generated/types.d.ts:
  ChatCompletionResponse JSON text subset; object/id/model/created/choices/usage.
  Supported subset requires assistant text, stop/length and consistent integer token
  counts. Streams, tool calls and other variants are unsupported. cost_flop and
  gflops_used remain unverified reported numbers; no conversion to confirmed units.
- @flop-labs/client 0.2.1 README: structural validation does not verify signatures,
  payment, inclusion or finality. x_flop_receipt is an unverified extension, not
  accepted settlement proof.
- @flop-labs/sdk 0.4.0 direct-session and compute-channel declarations describe
  receipt signature/hash/accumulator/model checks, genesis/finalized channel context,
  and distinguish settlement posted from settled. This stage does NOT implement
  those cryptographic checks or a chain proof verifier. SDK was not installed/run.

flop-local-capture-v1 is explicitly a LOCAL capture envelope, not an official FLOP
wire format. HTTP 202 acceptance is a local observation convention, not a claim that
FLOP publishes a 202 receipt API. Local bindings include operation/idempotency/
correlation IDs, network/genesis, fingerprint, model and unit, plus optional channel,
transaction and receipt references. They establish consistency, NOT authenticity;
a fabricated matching completion cannot be distinguished cryptographically here.
Settlement claims require exact integer units but are always UNVERIFIABLE.

Same capture is idempotent after restart. Request/completion/receipt identifiers are
claimed atomically per genesis to reject cross-operation reuse. Conflicting bodies,
claims, or changed/disappearing references do not overwrite previous observations.
Malformed, missing or unavailable evidence does not release holds or establish failure.
Classification and ownership claims share a transaction with journal evidence; an
injected crash rolls back all of them. No raw completion text or receipt is journaled.

Final verification: 146 discovered, 145 PASS, 0 FAIL/ERROR, 1 SKIP.
All 129 P0-C passing tests remain passing; 16 synthetic offline evidence tests added.
The skip is the existing private 34-offer replay; private SQLite was not opened/copied.
Temporary databases cover repeated initialization/migration, atomic reservations,
process crash/recovery, rollback, replay, conflicting evidence and premature release.
Inherited test audit hooks block external sockets/DNS and non-Python subprocesses;
legacy loopback tests remain allowed. Log: deployment-private/p0-d-offline/tests.txt.

P0-D files: flop_evidence.py, durable.py, tests/test_flop_evidence.py,
tests/fixtures/flop_completion.json, README.md and this report. Existing P0-A/B/C
changes preserved. No operational installation/configuration/runtime/permissions,
EXECUTION_DISABLED or launcher changes. No model, Telegram, inference, signed request,
wallet, faucet, transaction, cron, commit/push. No gateway/RPC reads in this stage.

Remaining before real inference: independently trusted network/genesis/runtime and
channel state, authenticated request capture, official receipt verification with
trusted attestation/model/input/output bindings, finality and closed-escrow proof,
exact-cost reconciliation, and separately authorized transport/budget/signing.
Local captures alone cannot make a financial operation CONFIRMED. P1 not started.


## P1-E: Testnet launch readiness (2026-11-02)

Added local UNVERIFIED testnet profile, testnet-readiness CLI command, fixed public
source review and Day-1 supplement. Existing PublicReader/specification/Durable source
checkpoints and Store journal reused. No new executor/database, no changes to inference
states, budgets, outbox or evidence finality policy. Default private config/DB unopened.
Only explicitly selected existing --launch-journal receives local snapshot writes.
The live command read five official URLs, all HTTP 200, yet returned UNVERIFIED with
can_execute=false and EXECUTION_DISABLED. No independent launch artifact verifier is
implemented: even a fabricated complete local profile never yields OPEN/READY.
Unknown formats remain visible as discovery candidates; automatic parsing of future
onboarding/signature schemes is not claimed. No calendar-based activation.

Actual live results: docs/acceptance/p1e-live.json. Container release manifest is
available, but is not a Testnet launch artifact bound to genesis. Network page remains
planned/unreleased. FAQ participation wording requires interpretation alongside it.
No pre-launch DID cutoff found within reviewed pages/search; future changes unknown.

Full offline suite: 158 tests, 157 PASS, 0 FAIL/ERROR, 1 SKIP, 24.209s.
All previous 145 passing tests preserved, 12 new tests. Skip: private 34-offer replay.
External sockets/DNS blocked during suite; loopback legacy tests allowed. Tests cover
missing genesis, forged source, wrong network, incompatible release, closed faucet,
contradictory sources, future/stale data, single-GET/date false readiness, fabricated
VERIFIED profile, default private-state isolation, restart/dedup and last_success.
Log: docs/acceptance/p1e-tests.txt. No real secrets/SQLite copied.

Only development worktree changed. No wallet, faucet contact, enrollment, signature,
inference, real-money action, Telegram, cron, SDK installation, commit or push.
Remaining: independently authenticated Testnet artifacts, actual DID/account flow,
qualified runtime/client, scoped owner authorization, price/budget, live Durable
transport and finality verifier. No live execution readiness claimed.


## Local history checkpoint — 2026-11-02

Reviewed accumulated P0-A documentation and P0-B/C/D/P1-E source/test changes.
Fresh pre-commit offline suite: 158 tests, 157 PASS, 0 FAIL/ERROR, 1 SKIP, 23.822s.
External network and non-Python children blocked; legacy loopback fixtures allowed.
Private replay remains skipped. Included source snapshots are public documents; test
logs contain test names/results only. No private state, credentials or deployment
artifacts included. Added ignore rules for custody/tool/archive paths. This checkpoint
is local Git history only, not deployment, publication or authorization for Testnet.
