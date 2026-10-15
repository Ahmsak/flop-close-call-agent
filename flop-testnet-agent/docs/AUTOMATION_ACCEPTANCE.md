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
