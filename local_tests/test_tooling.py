import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path
from close_call_fold import Fold
from tools.simulate_strategy import simulate, fixture_ids
from tools.contest_client import ContestClient, EXECUTION_DISABLED


def scenario(side='long', final='110.00', close='100.00', quantity='10', n=1):
    return {'owners':['agent','counterparty'],'seed_price':'100.00','final_price':final,
            'sweeps':[{'n':n,'reference_price':'100.00','close_price':close,'register':['agent','counterparty'],
                       'trades':[{'id':'first','owner':'agent','counterparty':'counterparty','side':side,
                                  'quantity':quantity,'entry_price':'100.00'}]}]}


class ToolingTests(unittest.TestCase):
    def test_long_short_conservation(self):
        r=simulate(scenario())
        self.assertEqual(Decimal(r['accounts'][0]['contest_score']),90)
        self.assertEqual(Decimal(r['accounts'][1]['contest_score']),-110)
        self.assertEqual(Decimal(r['final']['zero_sum']),0)
    def test_short_negative_balance(self):
        r=simulate(scenario('short','250.00',quantity='99'))
        self.assertLess(Decimal(r['accounts'][0]['final_balance']),0)
    def test_clawback(self):
        r=simulate(scenario(final='110.00',close='106.00'))
        self.assertEqual(Decimal(r['accounts'][0]['fees']),60)
        self.assertEqual(Decimal(r['accounts'][0]['contest_score']),40)
    def test_insufficient_counterparty_funds(self):
        r=simulate(scenario(quantity='100'))
        self.assertEqual(r['sweeps'][0]['trades'][0]['reason'],'funds')
    def test_last_sweep_mints_before_trades(self):
        r=simulate(scenario(n=2556))
        self.assertEqual(r['sweeps'][0]['trades'][0]['outcome'],'settled')
    def test_after_lock_rejected(self):
        with self.assertRaises(ValueError): simulate(scenario(n=2557))
    def test_unregistered_counterparty(self):
        s=scenario();s['sweeps'][0]['register']=['agent']
        self.assertEqual(simulate(s)['sweeps'][0]['trades'][0]['reason'],'not_owner')
    def test_multiple_trades_realized_unrealized(self):
        s=scenario(final='120.00')
        s['sweeps'].append({'n':2,'reference_price':'110.00','close_price':'110.00',
                            'trades':[{'id':'exit','owner':'agent','counterparty':'counterparty','side':'short','quantity':'4','entry_price':'110.00'}]})
        a=simulate(s)['accounts'][0]
        self.assertEqual(Decimal(a['realized_pnl']),40)
        self.assertEqual(Decimal(a['unrealized_pnl']),120)
        self.assertEqual(Decimal(a['collateral']),600)
        self.assertEqual(Decimal(a['contest_score']),Decimal('145.6'))
    def test_custom_start_and_fees(self):
        s=scenario();s.update(starting_polf='20000',fee_rate='0.02')
        r=simulate(s);self.assertTrue(r['counterfactual_parameters'])
        self.assertEqual(Decimal(r['accounts'][0]['contest_score']),80)
    def test_no_trade_ties(self):
        s=scenario();s['sweeps'][0]['trades']=[]
        r=simulate(s)
        self.assertEqual([Decimal(a['contest_score']) for a in r['accounts']],[0,0])
        self.assertTrue(all(row['sharing']==2 for row in r['final']['standings']))
    def test_self_trade_disabled(self):
        s=scenario();s['sweeps'][0]['trades'][0]['counterparty']='agent'
        with self.assertRaises(ValueError):simulate(s)
    def test_client_execution_flag_never_enables(self):
        c=ContestClient(execute=True)
        for name in ('construct_trade','sign','register','submit_trade','claim','transfer'):
            self.assertEqual(getattr(c,name)(),EXECUTION_DISABLED)
        self.assertTrue(c.read_only)
    def test_validation_does_not_mutate(self):
        f=Fold();f.seed('100');a,b=fixture_ids()[:2];f.sweep(1,'100','100',[a,b],[])
        before=copy.deepcopy(f.__dict__)
        t=dict(id='v',maker=a,taker=b,countersigner=b,side='buy',qty='1',px='100',until=2)
        self.assertTrue(ContestClient().validate_trade_locally(f,t,sweep=2,reference_price='100',close_price='100')['valid'])
        self.assertEqual(f.__dict__,before)
    def test_official_7_digit_amount_limit(self):
        s=scenario();s['sweeps'][0]['trades'][0]['entry_price']='10000000'
        self.assertEqual(simulate(s)['sweeps'][0]['trades'][0]['reason'],'shape')
    def test_validator_rejects_invalid_closing_reference(self):
        f=Fold();f.seed('100')
        result=ContestClient().validate_trade_locally(f,{},sweep=1,reference_price='100',close_price='-1')
        self.assertEqual(result,{'valid':False,'reason':'price_shape'})


class UpstreamAuditObservations(unittest.TestCase):
    """Characterize upstream gaps without modifying its rules or expecting fixes."""
    def test_upstream_accepts_after_final_and_result_is_stale(self):
        a,b=fixture_ids()[:2];f=Fold();f.seed('100');f.sweep(1,'100','100',[a,b],[])
        result=f.final('100')
        trade=dict(id='late',maker=a,taker=b,countersigner=b,side='buy',qty='1',px='100',until=2)
        f.sweep(2,'100','100',[],[trade])
        self.assertEqual(Decimal(result['standings'][0]['score']),0)
        self.assertEqual(f.accounts[a].value_at(Decimal(100))-f.mint,-1)
    def test_upstream_accepts_extra_trade_fields(self):
        a,b=fixture_ids()[:2];f=Fold();f.seed('100')
        t=dict(id='extra',maker=a,taker=b,countersigner=b,side='buy',qty='1',px='100',until=1,unexpected=True)
        r=f.sweep(1,'100','100',[a,b],[t])
        self.assertEqual(r['trades'][0]['outcome'],'settled')


if __name__=='__main__':unittest.main()
