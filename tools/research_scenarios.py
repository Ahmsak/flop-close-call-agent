"""Deterministic offline illustrations, no forecasts or generated owner keys."""
import json
from pathlib import Path
from tools.simulate_strategy import simulate

ROOT=Path(__file__).resolve().parents[1]


def fill(tid, side, px, qty='40', owner='agent', counterparty='counterparty'):
    return dict(id=tid,owner=owner,counterparty=counterparty,side=side,quantity=qty,entry_price=px)


def sweep(n, ref, close, trades, register=None):
    return dict(n=n,reference_price=ref,close_price=close,trades=trades,register=register or [])


def one(side,n=1,px='200.00',close=None):
    return dict(owners=['agent','counterparty'],seed_price='200.00',final_price='210.00',
                sweeps=[sweep(n,px,close or px,[fill('entry',side,px)],['agent','counterparty'])])


def scenarios():
    s={'A_one_shot_long':one('long'),'B_one_shot_short':one('short'),
       'C_late_long':one('long',2554,'206.00'),'D_late_short':one('short',2554,'206.00')}
    repeated=one('long')
    repeated['sweeps'] += [sweep(100,'206.00','206.00',[fill('exit1','short','206.00')]),
                           sweep(200,'204.00','204.00',[fill('entry2','long','204.00')]),
                           sweep(300,'208.00','208.00',[fill('exit2','short','208.00')])]
    s['E_repeated']=repeated
    mm=one('long',px='198.00',close='200.00')
    mm['sweeps'][0]['reference_price']='200.00'
    mm['sweeps'].append(sweep(2,'200.00','200.00',[fill('ask','short','202.00')]))
    s['F_market_making']=mm
    s['G_momentum']=one('long',100,'206.00')
    s['H_contrarian']=one('short',100,'206.00')
    s['I_no_trade']=one('long');s['I_no_trade']['sweeps'][0]['trades']=[]
    s['J_independent_owners']=dict(owners=['long_agent','short_agent','baseline','external_seller','external_buyer'],
            seed_price='200.00',final_price='210.00',
            sweeps=[sweep(1,'200.00','200.00',
                [fill('independent_long','long','200.00',owner='long_agent',counterparty='external_seller'),
                 fill('independent_short','short','200.00',owner='short_agent',counterparty='external_buyer')],
                ['long_agent','short_agent','baseline','external_seller','external_buyer'])])
    return s


def main():
    sc=scenarios(); rows=[]
    for name,base in sc.items():
        for final in ['180.00','200.00','210.00','220.00','400.00']:
            case={**base,'final_price':final}
            result=simulate(case)
            rows.append(dict(strategy=name,final_price=final,accounts=result['accounts'],zero_sum=result['final']['zero_sum'],
                             settled=sum(t['outcome']=='settled' for s in result['sweeps'] for t in s['trades'])))
    (ROOT/'data/strategy_scenarios.json').write_text(json.dumps(sc,indent=2)+'\n',encoding='utf-8')
    (ROOT/'data/strategy_results.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    (ROOT/'tools/example_scenario.json').write_text(json.dumps(sc['A_one_shot_long'],indent=2)+'\n',encoding='utf-8')
    print(f'{len(rows)} official-Fold scenarios completed')


if __name__=='__main__':main()
