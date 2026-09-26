"""Offline-first interface with explicit public GET refresh; execution stays disabled."""
from copy import deepcopy
from decimal import Decimal, localcontext
import json
import datetime as dt
from pathlib import Path
from tools.simulate_strategy import simulate
from close_call_fold import amount

EXECUTION_DISABLED = 'EXECUTION_DISABLED'
READ_ONLY = True


class ContestClient:
    def __init__(self, snapshot_path=None, *, execute=False):
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None
        self.read_only = True
        self.execution_requested = bool(execute)

    def observe(self):
        if self.snapshot_path is None:
            return {'status': 'NO_LOCAL_SNAPSHOT', 'read_only': True}
        snapshot=json.loads(self.snapshot_path.read_text(encoding='utf-8'))
        now=dt.datetime.now(dt.timezone.utc)
        try:
            times=[snapshot.get('sweep_timestamp',snapshot['timestamp']),snapshot['reference_price']['time']]
            ages=[(now-dt.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds() for t in times]
            snapshot['stale']=max(ages)>900 or min(ages)<-60
        except (KeyError,TypeError,ValueError):snapshot['stale']=True
        snapshot['read_at_utc']=now.isoformat()
        return snapshot

    def refresh_once(self, output=None):
        from .observer import refresh, ROOT
        destination=Path(output) if output else ROOT/'data/observer'
        snapshot=refresh(destination)
        if snapshot['status']!='REJECTED':self.snapshot_path=destination/'latest.json'
        return snapshot

    def get_leaderboard(self):
        s = self.observe()
        return {'top': s.get('leaderboard', []), 'timestamp': s.get('timestamp'),
                'authority': s.get('authority', 'UNVERIFIED'), 'complete': False,'stale':s.get('stale',True)}

    def get_reference_price(self):
        s = self.observe()
        return {'reference': s.get('reference_price'), 'timestamp': s.get('timestamp'),
                'status': 'SNAPSHOT_ONLY_NOT_EXECUTABLE','stale':s.get('stale',True)}

    def find_counterparties(self):
        return {'candidates': [], 'status': 'UNKNOWN_NO_VERIFIED_OFFER_ARCHIVE'}

    def construct_trade(self, **terms):
        return EXECUTION_DISABLED

    def validate_trade_locally(self, fold, trade, *, sweep, reference_price, close_price):
        if fold.final_px is not None or type(sweep) is not int or sweep <= fold.sweep_n:
            return {'valid': False, 'reason': 'phase'}
        if amount(reference_price) is None or amount(close_price) is None:
            return {'valid': False, 'reason': 'price_shape'}
        with localcontext() as ctx:
            ctx.prec = 60
            reason = deepcopy(fold).check(trade, sweep, Decimal(reference_price), Decimal(close_price))
        return {'valid': reason is None, 'reason': reason, 'scope': 'accounting_only_no_signature_or_stamp_check',
                'assumption': 'close_price must be supplied; not known before sweep closes'}

    def estimate_score(self, scenario):
        return simulate(scenario)

    def recommend_action(self):
        return {'action': 'HOLD_READ_ONLY', 'execution': EXECUTION_DISABLED,
                'reason': 'Research only; contest authority and execution not enabled'}

    def sign(self, *args, **kwargs): return EXECUTION_DISABLED
    def register(self, *args, **kwargs): return EXECUTION_DISABLED
    def submit_trade(self, *args, **kwargs): return EXECUTION_DISABLED
    def claim(self, *args, **kwargs): return EXECUTION_DISABLED
    def transfer(self, *args, **kwargs): return EXECUTION_DISABLED


_default = ContestClient()
observe = _default.observe
get_leaderboard = _default.get_leaderboard
get_reference_price = _default.get_reference_price
find_counterparties = _default.find_counterparties
construct_trade = _default.construct_trade
validate_trade_locally = _default.validate_trade_locally
estimate_score = _default.estimate_score
recommend_action = _default.recommend_action
