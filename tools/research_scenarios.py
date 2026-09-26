"""Deterministic offline illustrations, no forecasts or generated owner keys."""
import json
import argparse
import copy
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


def final_scenarios():
    cases={'control':one('long'),'long':one('long'),'short':one('short')}
    cases['control']['sweeps'][0]['trades']=[]
    for side in ('long','short'):
        case=one(side,n=2554,px='206.00',close='207.20')
        case['sweeps'][0]['register']=[]
        case['sweeps'][0]['reference_price']='205.00'
        case['sweeps'].insert(0,sweep(1,'200.00','200.00',[],['agent','counterparty']))
        cases['late_confirmed_'+side]=case
    cases['no_counterparty']=one('long')
    cases['no_counterparty']['sweeps'][0]['trades'][0]['counterparty_available']=False
    cases['delay_clawback']=one('long',n=20,close='211.00')
    cases['delay_clawback']['sweeps'][0]['reference_price']='210.00'
    cases['delay_limits_void']=one('long',n=20,close='212.00')
    cases['delay_limits_void']['sweeps'][0]['reference_price']='212.00'
    cases['expired']=copy.deepcopy(cases['late_confirmed_long'])
    cases['expired']['sweeps'][-1]['trades'][0]['until']=2553
    cases['insufficient_reserve']=one('long',close='206.00')
    cases['insufficient_reserve']['sweeps'][0]['trades'][0]['quantity']='49.50'
    cases['invalid_quantity_step']=one('long')
    cases['invalid_quantity_step']['sweeps'][0]['trades'][0]['quantity']='40.001'
    cases['invalid_price_step']=one('long')
    cases['invalid_price_step']['sweeps'][0]['trades'][0]['entry_price']='200.001'
    return cases


def compare_finals(snapshot=None):
    rows=[]
    for name,base in final_scenarios().items():
        for s in ['180.00','200.00','210.00','220.00']:
            result=simulate({**base,'final_price':s})
            account=result['accounts'][0]
            rows.append({'strategy':name,'S':s,'score':account['contest_score'],'fees':account['fees'],
                'live_score':result['history'][-2]['live_score'],
                'prices':result['price_roles'],'outcomes':[t for sweep in result['sweeps'] for t in sweep['trades']],
                'not_submitted':result['not_submitted'],'conditional_place':None,'competitor_final_scores':None})
    overlap=0
    if snapshot:
        positions=dict(snapshot.get('open_positions_summary',{}).get('top',[]))
        overlap=sum(k in positions for k,_ in snapshot.get('leaderboard',[]))
    output={'assumptions':['Counterparties explicitly modeled, fills conditional',
            'Competitors do not trade after the snapshot',
            'Displayed rounded scores are not exact Fold scores or exact ties',
            'Scenario counts do not estimate profitability or top-3 probability'],
        'competitor_data_status':'INSUFFICIENT_EXACT_ACCOUNT_STATE',
        'observed_position_score_overlap':overlap,
        'global_rank_prediction':False,'rows':rows}
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final-comparison',action='store_true')
    parser.add_argument('--snapshot',type=Path)
    args=parser.parse_args()
    if args.final_comparison:
        snapshot=json.loads(args.snapshot.read_text(encoding='utf-8')) if args.snapshot else None
        result=compare_finals(snapshot)
        destination=ROOT/'data/stage2/final_scenarios.json';destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'scenarios':len(result['rows']),'competitor_data_status':result['competitor_data_status'],
                          'observed_position_score_overlap':result['observed_position_score_overlap']}));return
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
