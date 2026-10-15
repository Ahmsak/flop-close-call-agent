"""Safe acceptance session: existing invoice worker + copied SQLite + fake delivery.
No model, signatures, live network, credentials or paid actions.
"""
import argparse
from decimal import Decimal
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from durable import Durable, Policy
from jobs import solve
from ops import Store, canonical, strict_json

ROOT=Path(__file__).resolve().parent

class DeliveryFixture:
    environment='sandbox'
    def __init__(self,path): self.path=Path(path)
    def send(self,key,destination,result):
        records=strict_json(self.path.read_text()) if self.path.exists() else {}
        records[key]={'accepted':True,'service_id':'SIMULATED-'+key,'send_count':records.get(key,{}).get('send_count',0)+1}
        self.path.write_text(canonical(records),encoding='utf-8')
        raise OSError('SIMULATED: response lost after acceptance')
    def lookup(self,key):
        return strict_json(self.path.read_text()).get(key) if self.path.exists() else None

def validate_invoice(job,result):
    rows=list(csv.DictReader(io.StringIO(job['input'])))
    expected={sku:sum((Decimal(row['quantity'])*Decimal(row['unit_price']) for row in rows if row['sku']==sku),Decimal(0)) for sku in {r['sku'] for r in rows}}
    return set(result)==set(expected) and all(Decimal(result[key])==value for key,value in expected.items())

def worker(folder,now,crash=False):
    store=Store(folder/'state.sqlite'); queue=Durable(store,clock=lambda:now); policy=Policy(folder/'policy.json')
    try:
        queue.mark('heartbeat','ALIVE')
        job=strict_json((ROOT/'examples/job.json').read_text())
        # Existing deterministic worker selection, not an LLM or paid offer claim.
        spec={'goal':'Produce per-SKU invoice totals for local reconciliation','input':job,
              'criterion':'Independent Decimal row-group sums agree for every SKU',
              'artifact':'invoice-result.json','stop':'One checked result or bounded failure',
              'max_attempts':3,'max_units':2}
        key=queue.enqueue(spec,policy)
        fence=queue.claim(key,'demo-worker')
        if fence is not None:
            intent=queue.reserve(key,'demo-worker',fence,'invoice-calculation','local',1,policy)
            if intent['state']=='NEW_INTENT':
                result=solve(job)
                if not validate_invoice(job,result): raise ValueError('INDEPENDENT_QUALITY_FAILURE')
                (folder/'invoice-result.json').write_text(json.dumps({'environment':'LOCAL_SANDBOX','totals':result,'input':job},indent=2),encoding='utf-8')
                queue.action_result(intent['id'],receipt={'result':result,'calculation_count':1})
                if crash: os._exit(17)  # durable receipt exists; completion/outbox not yet committed
            else:
                saved=queue.db.execute('SELECT receipt FROM automation_actions WHERE id=?',(intent['id'],)).fetchone()
                result=strict_json(saved[0])['result']
            queue.complete(key,'demo-worker',fence,{'TASK_OUTPUT_VALID':validate_invoice(job,result),'totals':result},folder/'invoice-result.json')
        notice=queue.db.execute('SELECT id FROM automation_outbox WHERE task_id=?',(key,)).fetchone()
        if notice:
            fixture=DeliveryFixture(folder/'fake-service.json')
            queue.deliver(notice[0],fixture,policy)
        output={'task_id':key,'task':queue.task(key),'health':queue.health()}
        (folder/'worker-result.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    finally: store.close()

def demo(folder):
    folder.mkdir(parents=True,exist_ok=False)
    source=Store(ROOT/'runtime/state.sqlite')
    before=source.diagnose()
    old_events=[tuple(r) for r in source.db.execute('SELECT seq,hash FROM events ORDER BY seq')]
    old_operations=[tuple(r) for r in source.db.execute('SELECT * FROM operations ORDER BY id')]
    try: source.backup(folder/'state.sqlite')
    finally: source.close()
    policy={'execution':'EXECUTION_DISABLED','owner_did':'fixture-only-no-DID-created','real_money_budget':'0',
            'automation_daily_units':{'local':2,'model':0,'flop':0,'infrastructure':0,'paper':0},'automation_sandbox_delivery':True}
    (folder/'policy.json').write_text(canonical(policy),encoding='utf-8')
    now=time.time()
    command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(folder),'--now']
    crash=subprocess.run(command+[str(now),'--crash'],capture_output=True,text=True)
    if crash.returncode!=17: raise RuntimeError('FAULT_NOT_REACHED: '+crash.stderr)
    resumed=subprocess.run(command+[str(now+31)],capture_output=True,text=True)
    if resumed.returncode: raise RuntimeError(resumed.stderr)
    store=Store(folder/'state.sqlite'); q=Durable(store,clock=lambda:now+32)
    try:
        notice=dict(q.db.execute('SELECT * FROM automation_outbox').fetchone())
        before_delivery=notice['state']
        q.reconcile_notice(notice['id'],DeliveryFixture(folder/'fake-service.json'))
        task=q.task(notice['task_id'])
        service=DeliveryFixture(folder/'fake-service.json').lookup(notice['id'])
        summary={'environment':'LOCAL_SANDBOX','LLM':'NOT_USED; existing deterministic worker',
                 'migration_preserved_old_events':[tuple(r) for r in store.db.execute('SELECT seq,hash FROM events ORDER BY seq')][:len(old_events)]==old_events,
                 'migration_preserved_operations':[tuple(r) for r in store.db.execute('SELECT * FROM operations ORDER BY id')]==old_operations,
                 'task_goal':strict_json(task['spec'])['goal'],'fault':'process exit 17 after calculation receipt, before completion',
                 'task_state':task['state'],'result':strict_json(task['result']),
                 'calculation_actions':q.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],
                 'delivery_before_reconcile':before_delivery,'delivery_after_reconcile':q.db.execute('SELECT state FROM automation_outbox').fetchone()[0],
                 'simulated_send_count':service['send_count'],'user_read':'UNKNOWN','health':q.health()}
        (folder/'acceptance.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(summary,indent=2))
    finally: store.close()

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',type=Path); parser.add_argument('--now',type=float)
    parser.add_argument('--crash',action='store_true'); parser.add_argument('--output',type=Path)
    parser.add_argument('--health',type=Path)
    args=parser.parse_args()
    if args.health:
        store=Store(args.health)
        try: print(json.dumps(Durable(store).health(),indent=2))
        finally:store.close()
    elif args.worker: worker(args.worker,args.now,args.crash)
    else: demo(args.output or ROOT/'runtime'/('automation-demo-'+str(time.time_ns())))
