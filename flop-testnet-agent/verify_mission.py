"""Reproduce local quote checks and signed offer/accept/receipt joins, offline."""
import argparse
import json
from pathlib import Path
from ops import Store, strict_json, verify_record
from source_discovery import journal
from mission import ROOT, check_brief

def verify(directory, store):
    brief=strict_json((directory/'brief.json').read_text(encoding='utf-8'))
    docs=strict_json((directory/'inputs.json').read_text(encoding='utf-8'))
    state=strict_json((directory/'state.json').read_text(encoding='utf-8'))
    frames={}
    for event in journal(store,'discovery'):
        for row in event['snapshot']['messages']:
            if not any(claim['quote'] in row['text'] for claim in brief['claims']): continue
            verify_record('tclk-offers',row)
            frame=strict_json(row['text'].removeprefix('tclk1 '))
            frames[row['sig']]=frame
    chains=[]
    for receipt in frames.values():
        if receipt.get('type')!='receipt': continue
        for accept in frames.values():
            if accept.get('type')!='accept' or not accept.get('contract') or accept['contract']!=receipt.get('contract'): continue
            for offer in frames.values():
                if offer.get('type')=='offer' and offer.get('id')==accept.get('ref'):
                    chains.append({'offer':offer['id'],'contract':receipt['contract'],
                                   'asset':offer.get('asset'),'rail':receipt.get('rail'),'outcome':receipt.get('outcome')})
    return {'quotes':check_brief(brief,docs,state['read']), 'verified_signed_records':len(frames),
            'joined_chains':chains, 'scope':'Text/identifier/signature verification, not settlement or semantic proof'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('run',type=Path); args=parser.parse_args()
    store=Store(ROOT/'runtime/state.sqlite')
    try: result=verify(args.run,store)
    finally: store.close()
    print(json.dumps(result,ensure_ascii=False,indent=2))
