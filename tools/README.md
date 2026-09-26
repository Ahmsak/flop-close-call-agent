# Offline tools

Run from the repository root with Python 3.10+:

```powershell
python tools/simulate_strategy.py tools/example_scenario.json
python -m tools.research_scenarios
python -m unittest discover -s local_tests -v
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

The client observes a saved local snapshot, not a refreshed live service. `find_counterparties()` returns unknown/empty because an authenticated, complete offer archive is absent. No transport is activated. Local validation requires an existing Fold plus prospective sweep/reference/close; it cannot know the future close or reserve counterparties' funds.

To repeat public signature verification on already saved exports:

```powershell
.\.venv\Scripts\python.exe tools/verify_public_snapshot.py
```

This reads local exports and validates `room|nonce|text` with PyNaCl VerifyKey, plus tampering negative controls; it never signs. `.venv` is ignored. Raw live exports are intentionally not in commits, so signature replay on another machine requires copying these local evidence files or separately fetching the documented read endpoints. Do not interpret a cryptographically valid DID signature as proof of contest-authorized identity.
