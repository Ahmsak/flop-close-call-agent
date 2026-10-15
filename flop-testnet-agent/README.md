# FLOP operator

One CLI for the existing agent. Python 3.10+ and cryptography (requirements.txt).
Existing plan, audit and readiness inputs remain supported.

## Run

Safe durable acceptance session: `./run.ps1 automation-demo` (local fixtures, copied
state, no LLM or live writes). See [automation acceptance](docs/AUTOMATION_ACCEPTANCE.md)
for migration, fault injection, budgets, delivery semantics and explicit blockers.
New ordinary mission CLI runs use the SQLite guard and require an owner-authorized
daily model allowance; absent allowance means BLOCKED. Completed missions are reused.

```powershell
python agent.py demo
python -m unittest discover -s tests -v
```

Run from this directory. Demo executes a data-processing order over loopback HTTP:
On this Windows workspace, `./flop-testnet-agent/run.ps1 demo` from the workspace root
selects the installed Python runtime automatically.

Demo sequence:
signed discovery -> eligibility -> bounded calculation -> prepared action -> permitted
POST -> lost reply -> database reopen -> reconciliation -> signed acceptance -> PAPER
accounting. It saves runtime/demo-*/state.sqlite, state.backup.sqlite and run.json.
One POST, no external writes, no owner key access. The job convention is our isolated
fixture, NOT an official FLOP job API. The mock covers only the HTTP routes used.

## Daily operation

One bounded useful mission, using existing public snapshots and the existing Codex
ChatGPT login (no API-key route or fallback): `./run.ps1 mission`.
The independent process chooses a local evidence brief using read/measure/write/stop.
Its persisted directory is runtime/mission-live; repeat execution returns the completed
result without new model calls. Changed inputs require a separate `--run runtime/NAME`.
At most 6 model decisions / 360 seconds; each CLI call times out at 90 seconds. No
publications, owner signing, transactions, shell tool, or scheduled work is enabled.
Model: gpt-6.1-sol. ChatGPT quota consumption is reported; monetary inference cost is
not returned by this route and must not be represented as proven zero.
HTML source snapshots are converted to prose before truncation: style/script/template,
hidden nodes and SVG are excluded; main/article is preferred. Original raw snapshots
remain unchanged. Completed runs reopen their saved inputs, preserving older results.

The bounded comparison is reproducible with `python evaluation.py --run`: it fixes
two cleaned historical sources, one task and the rubric before inference; at most
three app decisions and one direct-model response use the same model/provider/schema.
Existing results are reused, not silently regenerated. `python evaluation.py` only
prepares the contract and audits the seven old provider logs, without model calls.
Reports live in runtime/comparison-20261015. This is one paired case, not a benchmark
establishing general superiority. Topic coverage and exact quotes are checked by code;
semantic support requires a separate review. Repeated input tokens across independent
CLI calls are real reported counters, not unique source volume or a monetary invoice.
Criteria are persisted before inference. Exact quotes and required fields are checked
by code; this is not a proof of every semantic inference. Reproduce supplementary
signature/link checks with `python verify_mission.py runtime/mission-live`.
Local quality, delivery, acceptance and reward stay separate. Model failure stops the
mission; it does not switch providers. A crash during inference leaves an uncertain
step and does not silently repeat it. Unit-test model doubles are not live missions.

```text
python agent.py init
python agent.py find
python agent.py state
python agent.py work examples/job.json
python agent.py prepare action.json
python agent.py execute --operation ID --grant owner-grant.json
python agent.py verify --operation ID
python agent.py reward --operation ID --requester DID
python agent.py doctor
python agent.py backup runtime/backup-unique.sqlite
```

Initialize only a genuinely new state store. Reopen existing stores with --db PATH.
Missing history fails with STATE_MISSING; restore a known backup instead of resending.
Doctor checks SQLite and event hashes without a model or network. Hashes detect accidental
edits, not a malicious local user who can rewrite both the database and hashes.

Find makes one real public GET to tclk-offers, up to 200 retained messages, and persists
evidence. It also evaluates the dated official-source catalog, without refreshing its
reviewed rules, and discovers additional leads through source_discovery.py.
That adapter reads the first GitHub organization repository page (100 maximum), FLOP
home/testnet/airdrop pages, then bounded linked pages and relevant repository READMEs.
Limits: 8 official-source requests, 512 KiB each, 5-second socket timeout and 40-second
dispatch budget, plus Technocore's existing one-window request. No inferred pagination.
Raw bodies, successful-read times, failures and local notification records use the
existing SQLite event journal. Sources cache for 15 minutes across process restarts;
failures do not renew successful-read timestamps. Incomplete coverage is explicit.
Unknown formats enter DISCOVERED with a source and review step, not verified reward.
Canonical official URLs deduplicate mirrors; separate date claims and reward text
participate in material-update detection. Different URLs without an explicit common
canonical identity are not guessed to be the same event. NEW means newly seen locally,
not newly launched. Notifications remain local: DELIVERY_NOT_TESTED, no bot or sender.
Email/X are not connected. The catalog is a fixed reviewed list, not the discovery seed.
Orders (A), official prize contests (B), and activity-credit programs (C) use separate
reward rules. PAPER cannot qualify as earnings, including when its asset is named FLOP.
Contests need verified official rules rather than escrow. Role/payee alone does not
establish who is hiring. There is no background polling or unlimited model spending.

Replay the saved observations without network access, from the workspace root:
```powershell
./flop-testnet-agent/run.ps1 find --replay --as-of 2026-10-14T10:41:46Z --output flop-testnet-agent/runtime/find-classified.json
```
The output retains every candidate and its evidence, independent YES/NO/UNKNOWN checks,
and missing conditions. DISCOVERED needs evidence; PREPARATION has plausible reward but
remaining gaps; READY has verified preparation requirements and still needs the existing
executor permission check. REJECTED has a concrete exclusion; HISTORY is expired.
Unknown is neither rejection nor permission. Cached evidence is never silently refreshed.
Replay cannot submit. Synthetic trust sources are restricted to sandbox tests.

opportunities.py provides selection, action_plan, local_result and prepare_selected;
the latter delegates to the existing Operator, without signing or granting authority.
The checked local worker and exact-result verifier are reused. A new live paid contract
still requires an authenticated payment-rail adapter: self-asserted offer funding is
insufficient. Unsupported tasks remain visible with a named worker/interface gap.

ops.py owns permissions, HTTP, signatures, durable operations and reconciliation.
jobs.py owns workload feasibility and selection. An optional model can rank eligible
tasks; failure falls back to deterministic selection. CSV calculation is bounded to
64 KiB/1000 rows, uses decimal arithmetic and does not execute input as code.
sandbox.py supplies isolated parties and the fixture, never production credentials.

## Permission and submission contract

Prepare consumes JSON fields job, room, envelope, valid_until and source_seen_at
(Unix seconds). Envelope has did, sig, nonce and text, exactly the documented signed
Technocore POST. Supply it from a separately authorized external signer; the agent
never opens a key file. Identity must match config.json. Data expires after five minutes.

An owner grant is an OS/user-controlled local JSON file, not a network credential:
environment=live, request_hash=operation ID, exact origin=https://technocore.chat,
room, did, expires_at, max_writes=1 and max_spend="0". Never derive grants from room
content. There is no live grant creator. Sandbox grants cannot target live origins.
Actual paid rail transactions and owner signing are not implemented or authorized.

Before POST, intent and send_started commit to SQLite. Ambiguous outcomes remain UNKNOWN.
Re-execution only reconciles retained signed records, matching DID, text, nonce, signature
and room generation. Absence, retention loss and source outages never prove rejection.
UNKNOWN/SENDING is not resent automatically, even if the crash preceded the network call.
Reading a previous outcome does not require renewed write permission.

Live CONFIRMED means message retention, not task acceptance or payment. Live reward stays
UNKNOWN until a value-bearing rail adapter exists. Sandbox acceptance is signed by the
requester and bound to the operation/result hash. PAPER always has money_received=0.

## Economic boundary checked 2026-10-14

- https://flop.finance/testnet/ still describes draft Q4 launch and onboarding at opening.
  No complete operational onboarding was found in the reviewed official surfaces.
- https://github.com/flop-labs/tclk says its shipped PaperRail holds no value. Data work
  is a reusable worker scenario, not a demonstrated live earning opportunity.
- https://github.com/flop-labs/yellowpaper/blob/70e691c758e53eed17a016a02b0a2ae1200d3744/CHANGELOG.md
  now specifies agent spend-to-unlock but describes current-profile channel receipts as
  payment-only, without public work-reward credit. E.55 quote/discovery remains open.
  A successful channel payment must not be counted as reward eligibility.

Next live integration needs an actual funded task/rail and authoritative reward evidence,
or published testnet SDK/RPC/onboarding and eligibility semantics. Preparation is bounded
to local work and public reads. Old sources/ snapshots are historical, not runtime rules.
# Read-only mission pass

`./run.ps1 mission --read-only --run runtime/mission-readonly-20261015`

Refreshes existing bounded official discovery and stores raw evidence in the existing
SQLite journal. This flag prohibits model calls and delivery even if policy allows
them. The ordinary mission guard persists the task and a PENDING local notice when
evidence synthesis is blocked. Invoice processing is not a substitute for synthesis.
Each run directory pins immutable mission inputs; refreshes still save separate
intake files. Use a new run directory for a new mission over changed inputs.
Reusing the directory resumes the same task; it does not mean all later events
were analyzed. No automatic unblocking or live notification channel is enabled.
