"""Offline strategy scenarios using the unchanged upstream Fold; never creates keys."""
from __future__ import annotations
import argparse
import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from close_call_fold import Fold, amount


def fixture_ids():
    """Reuse identifiers shipped in the upstream sample, without generating any DID/key."""
    owners = []
    for line in (ROOT / 'examples/sample-season.jsonl').read_text().splitlines():
        for owner in json.loads(line).get('owners', []):
            if owner not in owners:
                owners.append(owner)
    return owners


def simulate(scenario):
    """Owners are independent labels mapped to existing sample IDs (at most six).

    Every fill requires an explicitly modelled, funded counterparty. No automatic fills.
    sweep.close is the clawback reference; fee_rate overrides are counterfactual.
    PnL outputs are gross, fees are separately deducted in score/final_balance.
    """
    with localcontext() as ctx:
        ctx.prec = 60
        cfg = json.loads((ROOT / 'contest.json').read_text())
        start = str(scenario.get('starting_polf', cfg['mint']))
        fee = str(scenario.get('fee_rate', cfg['fee_rate']))
        if not Decimal(start).is_finite() or Decimal(start) <= 0:
            raise ValueError('starting_polf must be finite and positive')
        if not Decimal(fee).is_finite() or Decimal(fee) < 0:
            raise ValueError('fee_rate must be finite and nonnegative')
        labels = scenario['owners']
        if not isinstance(labels, list) or not 1 <= len(labels) <= len(fixture_ids()):
            raise ValueError('provide 1..6 owner labels; these reuse upstream sample IDs')
        if any(not isinstance(k, str) or not k for k in labels) or len(set(labels)) != len(labels):
            raise ValueError('owner labels must be distinct nonempty strings')
        ids = dict(zip(labels, fixture_ids()))
        cfg.update(mint=start, fee_rate=fee)
        fold = Fold(cfg)
        fold.seed(scenario['seed_price'])
        sweeps, history, prices, not_submitted = [], [], [], []
        final_px = scenario['final_price']
        if amount(final_px) is None:
            raise ValueError('invalid final_price')
        for sweep in scenario.get('sweeps', []):
            n = sweep['n']
            if type(n) is not int or not 1 <= n <= fold.lock:
                raise ValueError('sweep outside configured trading phase')
            trades = []
            for raw in sweep.get('trades', []):
                if raw.get('counterparty_available',True) is False:
                    not_submitted.append({'id':raw['id'],'sweep':n,'reason':'NO_COUNTERPARTY'})
                    continue
                if raw['side'] not in ('long', 'short', 'buy', 'sell'):
                    raise ValueError('side must be long/short/buy/sell')
                if raw['owner'] == raw['counterparty']:
                    raise ValueError('self-trades excluded from strategy tooling')
                side = 'buy' if raw['side'] in ('long', 'buy') else 'sell'
                trades.append(dict(id=raw['id'], maker=ids[raw['owner']], side=side,
                                   qty=raw['quantity'], px=raw['entry_price'],
                                   taker=ids[raw['counterparty']], until=raw.get('until', n),
                                   countersigner=ids[raw['counterparty']]))
            result = fold.sweep(n, sweep['reference_price'], sweep['close_price'],
                                [ids[k] for k in sweep.get('register', [])], trades)
            sweeps.append(result)
            prices.append({'sweep':n,'trade_prices':[t['px'] for t in trades],
                           'previous_reference_for_limits':sweep['reference_price'],
                           'closing_reference_for_fee':sweep['close_price'],
                           'global_price_for_live_board':str(fold.global_px),'hypothetical_final_S':final_px})
            for label, key in ids.items():
                if key in fold.accounts:
                    account = fold.accounts[key]
                    history.append({'sweep': n, 'owner': label, 'cash': str(account.cash),
                                    'collateral': str(sum((abs(q)*p for q,p in account.lots), Decimal(0))),
                                    'fees': str(account.fees), 'position': str(account.position)})
                    history[-1]['live_score']=str(account.value_at(fold.global_px)-fold.mint)
        final = fold.final(final_px)
        report = []
        s = Decimal(final_px)
        for label, key in ids.items():
            if key not in fold.accounts:
                report.append({'owner': label, 'registered': False})
                continue
            a = fold.accounts[key]
            collateral = sum((abs(q)*p for q,p in a.lots), Decimal(0))
            unrealized = sum((q*(s-p) for q,p in a.lots), Decimal(0))
            realized = a.cash + collateral + a.fees - fold.mint
            balance = a.value_at(s)
            report.append(dict(owner=label, registered=True, collateral=str(collateral),
                               cash_before_settlement=str(a.cash), fees=str(a.fees),
                               realized_pnl=str(realized), unrealized_pnl=str(unrealized),
                               final_balance=str(balance), contest_score=str(balance-fold.mint),
                               collateral_after_settlement='0', unrealized_after_settlement='0'))
        return {'status': 'LOCAL_SIMULATION_ONLY', 'authority': 'DRAFT/UNVERIFIED',
                'upstream_commit': '66c1da36538e4b1c685417d2f66922906b13fea0',
                'counterfactual_parameters': start != '10000' or fee != '0.01',
                'clawback': 'official max(base_fee, favorable_close_gap); never disabled',
                'accounts': report, 'history': history, 'sweeps': sweeps, 'final': final,
                'price_roles':prices,'not_submitted':not_submitted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = simulate(json.loads(args.scenario.read_text(encoding='utf-8')))
        text = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.write_text(text, encoding='utf-8')
        else:
            print(text, end='')
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'simulation: {error}\n')


if __name__ == '__main__':
    main()
