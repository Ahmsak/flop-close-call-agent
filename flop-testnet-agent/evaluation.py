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
    docs=prepare(target)
    contract=strict_json((target/'contract.json').read_text(encoding='utf-8'))
    if contract['source_hash']!=digest(docs) or contract['task']!=TASK: raise ValueError('CONTRACT_CHANGED')
    class TaskDecision(CodexDecision):
        def decide(self,context,step,remaining):
            if step>3: raise RuntimeError('COMPARISON_MODEL_CALL_CAP')
            context={**context,'assigned_task':TASK,'instruction':'This assigned task replaces the general choice of mission. Maximum 3 decisions: read only what you need, then write.'}
            return super().decide(context,step,remaining)
    app=run(docs,target/'application',TaskDecision)
    baseline=target/'baseline'; baseline.mkdir(exist_ok=True)
    if not (baseline/'attempt.json').exists():
        write(baseline/'attempt.json',{'status':'IN_FLIGHT','started_at':time.time()})
        start=time.monotonic()
        try:
            provider=CodexDecision(baseline)
            # Inline sources give baseline all information without application tool roundtrips.
            context={'assigned_task':TASK,'instruction':'Single direct answer, all source documents are provided below. Return write with the finished brief, or stop. No follow-up calls.',
                     'documents':docs,'history':[], 'steps_remaining':1}
            decision,usage=provider.decide(context,1,90)
            write(baseline/'decision.json',decision)
            brief=strict_json(decision['arguments'])
            if decision['tool']=='write':
                write(baseline/'brief.json',brief)
                (baseline/'result.html').write_text(render(brief,docs),encoding='utf-8')
            write(baseline/'attempt.json',{'status':'RETURNED','usage':usage,'seconds':time.monotonic()-start})
        except Exception as error:
            write(baseline/'attempt.json',{'status':'FAILED_NO_RETRY','error':str(error),'seconds':time.monotonic()-start})
    result={'contract':contract,'application_status':app['status']}
    for label in ('application','baseline'):
        folder=target/label
        brief=folder/'brief.json'
        result[label]={'usage':audit(folder),'score':score(strict_json(brief.read_text(encoding='utf-8')),docs) if brief.exists() else None}
    write(target/'comparison.json',result)
    return result

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
