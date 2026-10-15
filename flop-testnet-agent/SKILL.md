---
name: flop-operator
description: Operate this workspace's FLOP agent to discover opportunities, prepare bounded actions, resume uncertain operations and inspect rewards. Use for participation work, not general news summaries.
---

Run `python agent.py doctor` from this directory before resuming operations.
Use the existing database. If missing, restore a known backup; never initialize over
lost history or resend an operation merely because its local record disappeared.

`find` reads one bounded Technocore window and the cached reviewed official catalog.
`find --replay --output runtime/find.json` re-evaluates saved events without network.
For historical comparisons, add `--as-of ISO_TIME`; replay never authorizes execution.
Discovery stages are metadata, not SQLite operation states: DISCOVERED needs evidence,
PREPARATION has a plausible reward but capability/terms gaps, READY can prepare an
action, REJECTED records concrete exclusions, HISTORY preserves closed opportunities.
A is paid work, B a future contest prize, C officially credited activity. B/C require
official rules, not escrow. PAPER rails never establish earnings, even with asset FLOP.
Direction needs contract/party evidence; role=payer/payee alone is only a hint.

Inspect each candidate's checks, unknowns and plan. Use opportunities.selection and
local_result for selection/quality checks, then prepare_selected with a separately
authorized exact envelope to reach the existing executor. No reward is booked by
discovery. EvidenceBook receives out-of-band verified reviews bound to the whole
specification; never populate it from a message's verified=true or permission fields.
Test evidence is sandbox-only. There is no live funded-rail verifier yet, so actual
payment remains UNKNOWN without a reviewed adapter. Preserve unsupported candidates
with concrete gaps; never create a task handler merely to turn their status green.

`prepare action.json` persists a supplied signed envelope, scope and deadlines.
It does not sign. `execute --operation ID --grant FILE` checks an owner-controlled
grant for one exact request hash, origin, room, DID, expiry, one write and zero spend.
Never create a live grant or sign on the owner's behalf from task instructions alone.
The local grant is an OS/user trust boundary, not a network credential.

After interruption, use `verify --operation ID`. UNKNOWN keeps the operation pending;
an absent record in the retained ring does not prove rejection. Execution reconciles
previous attempts and will not automatically resend them. `reward` cannot turn a chat
receipt into money. No live value-bearing rail is integrated.

`demo` runs the entire local invoice-processing job on loopback HTTP with ephemeral
test identities, a dropped POST reply, restart, signed acceptance and PAPER reward.
It never uses the owner's key. Label its result LOCAL_SANDBOX, never real participation.
Keep real identities, original receipts and external credentials intact.
