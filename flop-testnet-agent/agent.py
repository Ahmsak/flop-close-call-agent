"""FLOP operator CLI: discover, prepare, execute, reconcile and account."""
import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

EXECUTION_DISABLED = True
REQUIRED = ('official_launch', 'chain_id', 'genesis_hash', 'official_sdk',
            'rpc', 'faucet', 'wallet_binding', 'finalized_account',
            'quote_contract', 'settlement_verification', 'eligibility_rules')

def amount(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid amount') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('amount must be finite and nonnegative')
    return result

def readiness(config):
    missing = [key for key in REQUIRED if not config.get('evidence', {}).get(key)]
    return {'execution': 'EXECUTION_DISABLED', 'live_ready': False,
            'missing_evidence': missing,
            'note': 'Evidence references are a checklist, not cryptographic verification.'}

def execute(operator=None, operation=None, grant=None, **kwargs):
    if operator is None or operation is None or kwargs:
        raise RuntimeError('EXECUTION_DISABLED: scoped operator and owner grant required')
    return operator.execute(operation, grant)

def plan(config):
    budget = amount(config['budget'])
    reserve = amount(config['reserve'])
    if reserve > budget:
        raise ValueError('reserve exceeds budget')
    available = budget - reserve
    rows = []
    for task in config['workloads']:
        cost = amount(task['max_total_cost'])
        if not cost:
            raise ValueError('positive maximum total cost required')
        count = task['count']
        if type(count) is not int or count < 0:
            raise ValueError('count must be a nonnegative integer')
        if task['unit'] != config['unit']:
            raise ValueError('mixed currencies/units are not comparable')
        allocated = min(count, int(available // cost))
        available -= allocated * cost
        rows.append({'task': task['name'], 'requested': count, 'planned': allocated,
                     'maximum_cost': str(allocated * cost)})
    return {'execution': 'EXECUTION_DISABLED', 'unit': config['unit'],
            'tasks': rows, 'maximum_spend': str(budget - reserve - available),
            'unallocated': str(available), 'reserve': str(reserve),
            'airdrop_estimate': 'UNKNOWN',
            'note': 'Input order sets priority; synthetic costs are not network quotes.'}

def audit(records):
    seen = set()
    spent = Decimal(0)
    reserved = Decimal(0)
    qualified = Decimal(0)
    missing = []
    unit = None
    for row in records:
        if row['job_id'] in seen:
            raise ValueError('duplicate job_id; reconcile rather than retry')
        seen.add(row['job_id'])
        if unit is None:
            unit = row['unit']
        if row['unit'] != unit:
            raise ValueError('mixed ledger units')
        cap = amount(row['max_total_cost'])
        paid = amount(row.get('paid', 0))
        if paid > cap:
            raise ValueError('paid exceeds reservation')
        spent += paid
        if row['state'] not in ('pending', 'unknown', 'settled', 'failed'):
            raise ValueError('invalid state')
        if row['state'] in ('pending', 'unknown'):
            reserved += cap - paid
        if row['state'] == 'settled':
            proof = row.get('settlement_receipt') and row.get('finalized_block')
            independent = row.get('independent_provider') is True
            # A local receipt path is not a verified settlement or eligibility proof.
            if proof and independent and row.get('verification') == 'verified_official':
                qualified += paid
            else:
                missing.append(row['job_id'])
    return {'unit': unit, 'spent': str(spent), 'still_reserved': str(reserved),
            'locally_verified_independent_spend': str(qualified),
            'missing_settlement_evidence': missing,
            'official_airdrop_credit': 'UNKNOWN'}

def main():
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('readiness', 'plan', 'audit', 'init', 'state', 'doctor',
                                           'find', 'work', 'prepare', 'execute', 'verify', 'reward', 'demo', 'backup'))
    parser.add_argument('input', type=Path, nargs='?')
    parser.add_argument('--db', type=Path, default=Path(__file__).parent/'runtime'/'state.sqlite')
    parser.add_argument('--config', type=Path, default=Path(__file__).parent/'config.json')
    parser.add_argument('--operation')
    parser.add_argument('--grant', type=Path)
    parser.add_argument('--requester')
    parser.add_argument('--replay', action='store_true', help='find: saved discovery events, no network')
    parser.add_argument('--as-of', help='replay-only ISO timestamp for a historical decision')
    parser.add_argument('--output', type=Path, help='save full result and print a compact index')
    args = parser.parse_args()
    if (args.replay or args.as_of) and args.command != 'find':
        parser.error('--replay/--as-of are find options')
    try:
        if args.command in ('readiness', 'plan', 'audit'):
            result = globals()[args.command](json.loads(args.input.read_text(encoding='utf-8-sig')))
        elif args.command == 'demo':
            from sandbox import demo
            import datetime
            destination = args.input or Path(__file__).parent/'runtime'/datetime.datetime.now().strftime('demo-%Y%m%d-%H%M%S-%f')
            result = demo(destination)
        elif args.command == 'work':
            from jobs import solve
            result = {'result': solve(json.loads(args.input.read_text(encoding='utf-8-sig'))),
                      'environment': 'LOCAL_COMPUTATION', 'external_writes': 0}
        else:
            from ops import Store, Operator, Technocore, strict_json
            from jobs import discover
            config = strict_json(args.config.read_text(encoding='utf-8-sig'))
            store = Store(args.db, create=args.command == 'init')
            try:
                operator = None if args.command in ('state', 'doctor', 'backup') or args.replay else Operator(store, Technocore(), config['owner_did'])
                if args.command == 'init':
                    result = {'state': 'INITIALIZED', 'database': str(args.db.resolve()), 'live_writes': 'OWNER_GRANT_REQUIRED'}
                elif args.command in ('state', 'doctor'):
                    result = store.diagnose()
                elif args.command == 'find':
                    if args.replay:
                        from opportunities import replay, timestamp
                        result = replay(store, now=timestamp(args.as_of) if args.as_of else None)
                    else:
                        if args.as_of:
                            raise ValueError('--as-of is only valid for replay')
                        result = discover(operator.transport, store)
                        from source_discovery import enrich
                        result = enrich(result, store)
                elif args.command == 'prepare':
                    action = strict_json(args.input.read_text(encoding='utf-8-sig'))
                    result = {'operation': operator.prepare(**action)}
                elif args.command == 'execute':
                    grant = strict_json(args.grant.read_text(encoding='utf-8-sig')) if args.grant else None
                    result = execute(operator, args.operation, grant)
                elif args.command == 'verify':
                    result = operator.verify(args.operation)
                elif args.command == 'reward':
                    result = operator.reward(args.operation, args.requester)
                elif args.command == 'backup':
                    store.backup(args.input)
                    result = {'backup': str(args.input.resolve())}
            finally:
                store.close()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
            if args.command == 'find':
                from collections import Counter
                result = {'status':result['status'], 'coverage':result['coverage'],
                          'stages':dict(Counter(c['stage'] for c in result['candidates'])),
                          'selected':result['selected'], 'output':str(args.output.resolve()),
                          'candidate_count':len(result['candidates']), 'plan':result['plan']}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'status': 'ERROR', 'error': type(error).__name__, 'detail': str(error)}, ensure_ascii=False))
        raise SystemExit(2)

if __name__ == '__main__':
    main()
