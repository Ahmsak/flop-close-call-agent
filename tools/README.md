# Read-only research tools

Stage 2 setup, trust boundaries and current repository status: [Hermes handoff](../docs/HERMES_HANDOFF.md).

Run from the repository root with Python 3.10+:

```powershell
python tools/simulate_strategy.py tools/example_scenario.json
python -m tools.research_scenarios
.\.venv\Scripts\python.exe -m unittest discover -s local_tests -v
```

`simulate_strategy.py` imports the unchanged `close_call_fold.Fold`. No network, signing, new DID or private key is involved. Owner labels reuse the six public IDs in the upstream sample; maximum six accounts per scenario. All participants, including counterparties, have the selected starting POLF. A void is reported, never silently treated as a fill.

Scenario fields: `owners`, `starting_polf` (default10000), `fee_rate` (default0.01), `seed_price`, `final_price`, `sweeps`. Each sweep has `n`, `reference_price`, `close_price`, `register` labels and `trades`. A trade needs `id`, `owner`, `counterparty`, `side` (`long`/`short` or `buy`/`sell`), decimal-string `quantity`, decimal-string `entry_price`, optional `until`. Opposite trades close FIFO lots, and may flip. To model clawback vary `close_price`; disabling it is deliberately unsupported by the official Fold. Nondefault mint/fee is labeled counterfactual.

Results include free cash, collateral before settlement, cumulative fees including clawback, gross realized/unrealized PnL, final balance, score, trade outcomes, history and upstream final standings. There is no extra final settlement fee in the inspected rules. Early final valuation in a scenario is a hypothetical experiment, not an accepted real contest final event.

```python
from tools.contest_client import ContestClient
client = ContestClient('data/live_snapshot.json')
print(client.observe())
print(client.get_leaderboard())
print(client.get_reference_price())
assert client.construct_trade() == 'EXECUTION_DISABLED'
```

`observe()` reads a saved snapshot and recomputes its age. `refresh_once()` explicitly fetches the six fixed public export endpoints, verifies signatures and package continuity, and atomically saves a PARTIAL snapshot. It never upgrades referee authority or claims full ledger replay. `find_counterparties()` returns unknown/empty because a complete verified offer archive is absent. Local validation requires an existing Fold plus prospective sweep/reference/close; it cannot know the future close or reserve counterparties' funds.

```powershell
.\.venv\Scripts\python.exe -m tools.contest_client.observer
python -m tools.research_scenarios --final-comparison --snapshot data/observer/latest.json
```

The observer uses GET only, no credentials, no redirects, a 15-second socket timeout, 12 MiB response cap and at most three attempts (1s/2s backoff). Raw UTF-8 bytes, source URLs, retrieval times, SHA-256, room generation and per-record signature/sequence checks stay under ignored `data/observer/`. This is one refresh, not a background service. Refresh exit 0 permits PARTIAL evidence; consult all trust flags. A rejected refresh saves evidence but does not replace `latest.json`.

`validated_replay()` requires a complete seed/sweeps/final sequence before invoking the unchanged Fold. It is an ordering guard, not signature authentication or a downloaded-archive verifier. Full archive retrieval is currently unavailable; no live full-replay claim is made.

To repeat public signature verification on already saved exports:

```powershell
.\.venv\Scripts\python.exe tools/verify_public_snapshot.py
```

This reads local exports and validates `room|nonce|text` with PyNaCl VerifyKey, plus tampering negative controls; it never signs. `.venv` is ignored. Raw live exports are intentionally not in commits, so signature replay on another machine requires copying these local evidence files or separately fetching the documented read endpoints. Do not interpret a cryptographically valid DID signature as proof of contest-authorized identity.
