"""Bounded paired evaluation and audit of existing provider token logs."""
import argparse
import json
from pathlib import Path
import time

from mission import ROOT, MODEL, CodexDecision, run, corpus, check_brief, render
from ops import Store, strict_json, digest
from source_discovery import journal, Page

TASK = ('Подготовь одну практическую памятку для оператора агента: что именно считается '
        'зачётной активностью агента в testnet и чем будущая аллокация отличается от доступных денег. '
        'Раскрой: settled sessions; faucet/holding; common-control demand; предварительный статус '
        'правил и дат; доступность onboarding; заморозку и разблокировку аллокации агента. '
        'Используй только два предоставленных исторических источника, не утверждай текущую '
        'доступность интерфейсов. Для каждого из шести пунктов дай отдельный вывод с точной цитатой. '
        'Сформулируй полезный следующий шаг без подписей, расходов и публикаций.')
RUBRIC = {
    'settled_sessions':['compute purchased in settled sessions'],
    'faucet_not_allocation':['a faucet grant creates no allocation by itself'],
    'independent_demand':['independent demand only'],
    'provisional':['dates and rules are provisional','these terms are a draft'],
    'onboarding':['onboarding documentation for each role is published when the testnet opens'],
    'locked_allocation':['every 3 $flop','agents nothing liquid'],
}

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def audit(directory):
    rows=[]
    for file in sorted(Path(directory).glob('provider-*.jsonl')):
        events=[strict_json(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip()]
        completed=[e['usage'] for e in events if e.get('type')=='turn.completed']
        if len(completed)!=1: raise ValueError('UNEXPECTED_COMPLETION_COUNT: '+file.name)
        rows.append({'file':file.name, 'thread_ids':[e['thread_id'] for e in events if e.get('type')=='thread.started'],
                     **completed[0]})
    keys=('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens')
    result={'calls':len(rows),'per_call':rows,'totals':{k:sum(r.get(k,0) for r in rows) for k in keys},
            'note':'Provider counters, not unique corpus size or a price invoice. Auxiliary reasoning/cache counters are not added to input/output totals.'}
    state=Path(directory)/'state.json'
    if state.exists():
        stored=strict_json(state.read_text(encoding='utf-8')).get('usage',[])
        result['state_totals_match']=all(sum(u.get(k,0) for u in stored)==result['totals'][k] for k in keys)
    return result

def score(brief,docs):
    check=check_brief(brief,docs,list(docs))
    quotes=' '.join(c.get('quote','') for c in brief.get('claims',[])).casefold()
    coverage={key:any(phrase in quotes for phrase in alternatives) for key,alternatives in RUBRIC.items()}
    return {'structural_and_quote_check':check, 'quoted_topic_coverage':coverage,
            'covered_topics':sum(coverage.values()), 'semantic_correctness':'REQUIRES_SEPARATE_REVIEW'}

def prepare(target):
    target.mkdir(parents=True,exist_ok=True)
    contract=target/'contract.json'
    if contract.exists(): return strict_json((target/'inputs.json').read_text(encoding='utf-8'))
    store=Store(ROOT/'runtime/state.sqlite')
    try:
        docs={k:v for k,v in corpus(store).items() if k in ('https://flop.finance/testnet/','https://flop.finance/airdrop/')}
        extraction=[]
        for row in journal(store,'source_snapshot'):
            if row['url'] in docs:
                old=Page(); old.feed(row['body']); old_text=' '.join(' '.join(old.text).split())[:24000]
                extraction.append({'url':row['url'],'old_chars':len(old_text),'old_font_face_mentions':old_text.count('@font-face'),
                                   'new_chars':len(docs[row['url']]['text']), 'new_font_face_mentions':docs[row['url']]['text'].count('@font-face'),
                                   'truncated':docs[row['url']]['truncated']})
    finally: store.close()
    write(target/'inputs.json',docs)
    write(contract,{'task':TASK,'model':MODEL,'provider':'Existing Codex ChatGPT login','reasoning_effort':'low',
                    'source_hash':digest(docs),'rubric':RUBRIC,'application_calls_max':3,'baseline_calls_max':1,
                    'comparison':'One paired trial; baseline gets all text inline; app retrieves identical text via read. Same model/schema/provider instructions. Not a statistical superiority test.',
                    'created_at':time.time()})
    write(target/'extraction.json',extraction)
    write(target/'prior-token-audit.json',{name:audit(ROOT/'runtime'/name) for name in ('mission-live','mission-control')})
    return docs

def compare(target):
    # Historical paired trial predates durable reservations and its grant is closed.
    # Keep accounting/quality readers, but do not expose an unbudgeted model path.
    raise PermissionError('LEGACY_COMPARISON_CLOSED_USE_DURABLE_MISSION')

if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(); parser.add_argument('--run',action='store_true'); args=parser.parse_args()
    target=ROOT/'runtime'/'comparison-20261015'
    if args.run:
        result=compare(target)
        print(json.dumps({k:{'calls':v['usage']['calls'],'tokens':v['usage']['totals'],'topics':v['score']['covered_topics'] if v['score'] else None} for k,v in result.items() if k in ('application','baseline')},indent=2))
    else:
        prepare(target); print(str(target/'contract.json'))
