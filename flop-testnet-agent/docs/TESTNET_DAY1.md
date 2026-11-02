# P1-E: Testnet Day-1 procedure

Read RUNBOOK.md first. This is a launch-specific supplement, not execution permission.
Current implementation is a bounded document review, NOT a cryptographic launch verifier.

## Read-only command

From the development component, using the existing Python interpreter:

```powershell
& 'C:\Users\lenin126\Documents\ChatGPT\флоп\deployment-private\20261015T072900Z\env\Scripts\python.exe' -B agent.py testnet-readiness --output docs/acceptance/p1e-live.json
```

Reads five fixed public documents (network page, FAQ, SDK reference, testnet intro,
release manifest), at most 512 KiB each, socket timeout 5s each, no retries, redirects
or link following. Socket/DNS timing is not a hard total wall-clock deadline.
No faucet, RPC, gateway inference or secrets are accessed. Default private Store and
config are never loaded. Optional --launch-journal explicitly selects an EXISTING
Store: same Durable.page/source_failed and hash-linked journal, no second database.
Without it, --output saves observations and unknown-format discovery candidates only.
Repeated unchanged source events deduplicate; read failures preserve last_success.
The command's zero exit code means review completed, NOT network readiness.

sources/testnet-profile.json is a LOCAL profile, not an official API schema. All
unpublished genesis/chain spec/RPC/Gateway/faucet/releases/onboarding/identity binding
values remain null/UNVERIFIED. Never copy devnet defaults into these fields.
The check lists missing/stale/conflicting/untrusted inputs. Even a local VERIFIED flag
cannot activate execution. Independent artifact verification is UNSUPPORTED; complete
future artifacts require a reviewed verifier extension before any OPEN/READY result.
No source text becomes instructions. Synthetic trust never enters live configuration.

## Official evidence observed 2026-11-02

https://docs.flop.network/networks/testnet: planned / next unreleased; no verified
chain spec, genesis, RPC, Gateway, admission, model catalog or supported releases.
https://docs.flop.network/docs/testnet-and-timeline: Nov 3 is a target, not a trigger;
FAQ describes using the Technocore DID key for future faucet and signed inference.
https://flop.finance/testnet/: draft; onboarding at opening; DID and wallet stated.
Public client 0.2.1 uses bearer credentials; CLI 0.4.0 public enrollment uses sr25519.
No published mapping proves this is the future Testnet DID flow. Keep these distinct.
https://docs.flop.network/docs/sdk-references: published packages target development.
https://flop.network/releases.json: CLI container 0.1.220 (minimum 0.1.172), miner worker
0.1.238, backend 0.1.239 with image digests. Container version is NOT npm CLI version;
this manifest has no verified Testnet genesis/network binding or agent launch receipt.
Do not classify our npm 0.4.0 as current/stale by comparing these different version lines.

No pre-launch agent registration, DID snapshot cutoff or limited initial faucet window
was found among these pages and official-site search results. This is bounded coverage,
not proof no later rule can appear. FAQ leaves faucet periodicity undecided. End-of-
testnet finalized snapshot is not a pre-launch DID cutoff. Do not confuse mainnet claim
rules with testnet faucet windows. No authenticated X/email sources were used.

## Immediately upon an official launch announcement (read-only)

1. Run the check manually, save dated sources and hashes; do not schedule cron.
2. Read the actual agent onboarding and separate registration/identity/faucet/claim
   deadlines. Record exact timezone, eligibility, cutoff height/time and source.
3. Independently authenticate genesis and chain-spec hash from a reviewed release;
   compare RPC chain identity/runtime with that anchor. Two aliases of one server
   are not independent anchors. Confirm endpoints belong to TESTNET explicitly.
4. Match qualified SDK/CLI version and integrity to this network/runtime. Do not
   install/update automatically. Reconcile contradictory announcements first.
5. Verify how existing Technocore DID binds to chain identity/credential; never reuse
   or transform private keys by assumption. Preserve existing operations and receipts.
6. Read faucet TERMS only: identity limits, window, grant unit, supported network.
   No faucet contact or claim until permission. Read authenticated balances/scope
   only after separate permission to use an existing credential.
7. Prepare an exact owner approval request naming identity, network/genesis, endpoint,
   model, one action, test-only unit, spend/escrow/fee/session/day limits and expiry.

## Only after separate owner authorization

8. Create wallet only if the actual Testnet flow requires it, after outside-sandbox
   ACL verification. Obtain approved grant/enrollment/signature with bounded effects.
   Devnet agent credential is not a Testnet onboarding command.
9. Confirm finalized grant/account state and credential allowance independently; a
   successful faucet HTTP response is insufficient. Confirm no real-money source.
10. Pin fresh model identity and price with units, expiry and trustworthy UTC; reserve
    exact integer costs (inference + escrow + fees) atomically in existing Durable.
    max_tokens alone is not a monetary cap. Stop on unknown price or amount.
11. Prepare one short non-streaming request, stable operation/idempotency/correlation
    IDs and request fingerprint. Live transport is not implemented yet; add/review it
    separately, never relabel the sandbox executor as live. Owner policy remains closed
    until an explicit, scoped grant is implemented and approved.
12. Commit submit intent before send, then one request only. On timeout/crash/ambiguous
    result keep UNKNOWN and reservation; do not retry, change key or free funds.
13. Save response privately and sanitized IDs/hash in existing journal. Use flop_evidence
    for structural binding/replay checks. GATEWAY_ACCEPTED != INFERENCE_COMPLETED !=
    SETTLEMENT_FINALIZED. Settlement needs independent finality and closed escrow proof;
    current verifier is UNSUPPORTED. Gateway JSON cannot release reservation.
14. After restart retrieve saved result without repeating work. Verify reward/airdrop
    credit separately from compute completion and payment. No presumed earnings.

Stop on missing identity, unsupported release, stale/future price, closed faucet,
conflicting evidence, unavailable sources or insufficient permission. No automatic
wallet/enrollment/inference, delivery, background watcher or cron is created here.
