# Publication handoff

This directory publishes the existing FLOP agent; it is not a second running agent.
The repository's Close Call files remain at their existing paths. Owner instructions
explicitly authorize this co-location for publication despite the older AGENTS.md
preference for a separate operator repository. No contest rules or package manifest
are changed.

## Operational location

The active working copy remains the sibling `../flop-testnet-agent/`, relative to
the root of `flop-close-call-agent`. Its operational state remains in that sibling's
`runtime/` directory, including `runtime/state.sqlite`; its configuration and existing
identities remain there. This publication does not alter scheduled tasks or paths.

The published source copy is `flop-close-call-agent/flop-testnet-agent/`.
Do not launch mission here, initialize replacement operational state, or develop the
two copies independently. Until an explicitly authorized migration, continue agent
development in the operational sibling and publish reviewed changes to this directory.
Publication-only instructions and config.example.json are maintained here.

## Included and excluded

Included: source modules, tests, synthetic fixtures, dependency declarations,
instructions, public source snapshots and historical acceptance report. Historical
acceptance results are not claims about this publication test run.

Excluded: operational config.json, environment files, credentials, operational keys,
SQLite, runtime journals, virtual environments, caches, archives and nested Git data.
config.example.json is a disabled placeholder, not an identity or permission grant.
Known public synthetic signing vectors in tests are not operational credentials.

## Isolated tests

Run from this published directory: `python -m unittest discover -s tests -q`.
Tests use temporary local data and loopback sandbox servers, not live submissions.
The 34-offer historical regression test skips when the intentionally excluded private
SQLite database is absent. Do not copy that database here to satisfy the test.
Live model, delivery and testnet remain unverified.

### This publication verification

Fresh run in this published directory: 80 tests discovered, 79 passed, one skipped,
zero failures (`OK (skipped=1)`, 14.973 seconds). The skip is the private historical
34-offer regression described above. No operational runtime directory or configuration
was created. Sandbox tests used temporary stores and loopback endpoints.

Parent Close Call verification: generated files current; 15 manifest artifacts verified;
18 tests passed. Pre-existing uncommitted changes in tools/README.md and
tools/verify_public_snapshot.py remain local and are excluded from this publication.

Integration base: c5d287e6d8a3b28ff496c52b777fe67f6bef139d, verified against origin before
creating integration/testnet-agent. No existing branch or upstream was changed.

### Follow-up publication: saved-task resume

Synchronized the completed task-scoped resume changes from the operational sibling:
durable.py, mission.py, mission_guard.py, its integration regression test and the
acceptance report. Current publication test result: 80 PASS, 0 FAIL, 1 SKIP out
of 81 discovered; the private-history regression remains excluded as described above.
No mission or live model call was run here. Operational location and closed model
allowance are unchanged. Publication-only config.example.json and this handoff remain
preserved; runtime and the real model-generated artifact are not published.

### Delivery publication

The completed one-shot delivery adapter and tests are published with anonymized
acceptance evidence. A new SUPERSEDED guard for obsolete BLOCKED notices was added
and tested only in this clone. The operational sibling was intentionally untouched
in this publication task; it does not yet contain this new guard. Do not assume that
publishing this branch deploys it, and do not run a second operational installation.
Latest clone tests: 88 PASS, 0 FAIL, 1 private-history SKIP. No model or Telegram call.
