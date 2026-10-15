# Components and deployment boundary

- [Close Call rules](../close-call-game.md), generated Fold, manifest, examples and
  upstream tests remain in their original locations. The root README belongs to
  the frozen package and is intentionally unchanged.
- [Read-only Close Call tooling](../tools/README.md) provides observation,
  signature checks and offline scenario research; it cannot trade or claim prizes.
- [FLOP agent](../flop-testnet-agent/README.md) contains discovery, deterministic
  work, durable mission reservations and scoped outbox delivery.
- [Release audit](RELEASE_AUDIT.md) records the reviewed candidate and limitations.
- [Automation acceptance](../flop-testnet-agent/docs/AUTOMATION_ACCEPTANCE.md)
  distinguishes historical live evidence from offline tests.

The operational installation remains the sibling `флоп/flop-testnet-agent` with
its existing private configuration and runtime. The component in
`флоп/flop-close-call-agent/flop-testnet-agent` is the publication copy.
The separate `флоп/flop-release-audit` worktree is for release verification only.
Merging this repository does not update the operational installation, migrate its
database, open permissions, start another mission or enable cron. Apply a separately
authorized deployment before treating the fixes as operational. Avoid independent
feature development in both copies: integrate changes into this repository and
deploy them deliberately, preserving the existing operational state.
