"""Durable reservation/lease boundary around the existing mission loop."""
import json
from pathlib import Path
from durable import Durable
from ops import canonical, digest, strict_json

def guarded_run(docs,directory,store,policy,provider_factory=None,*,allow_model=True):
    from mission import run, CodexDecision, MODEL
    directory=Path(directory); statefile=directory/'state.json'
    queue=Durable(store)
    spec={'goal':'Bounded evidence-linked useful mission','input':docs,'criterion':'Existing check_brief passes',
          'artifact':str(directory/'result.html'),'stop':'Six decisions or 360 seconds','max_attempts':3,'max_units':6}
    try:
        key=queue.enqueue(spec,policy); owner='mission-'+digest(str(directory))[:16]
        completed=statefile.exists() and strict_json(statefile.read_text(encoding='utf-8'))['status']=='LOCAL_COMPLETE'
        if queue.task(key)['state']=='CONFIRMED':
            if not completed:
                return {'status':'ARTIFACT_MISSING_OR_CHANGED','task_id':key,'reason':'COMPLETED_CHECKPOINT_MISSING_NO_REEXECUTION'}
            return {**run(docs,directory,provider_factory or CodexDecision),'task_id':key}
        p=policy.read()
        reason=None
        if not completed:
            if not allow_model: reason='LLM_DISABLED: evidence synthesis requires model; invoice_totals_v1 worker does not implement this task'
            elif p.get('automation_model')!=MODEL or p.get('automation_daily_units',{}).get('model',0)<1:
                reason='MODEL_DAILY_BUDGET_NOT_AUTHORIZED'
        if reason:
            nid=queue.block(key,reason)
            return {'status':queue.task(key)['state'],'reason':reason,'task_id':key,'outbox_id':nid,'delivery':'DELIVERY_NOT_TESTED'}
        fence=queue.claim(key,owner,120)
        if fence is None: return {'status':queue.task(key)['state'],'task_id':key,'reason':'LEASE_OR_RECONCILIATION_REQUIRED'}
        # A durable successful model response can repair a crash before JSON checkpoint.
        if statefile.exists():
            state=strict_json(statefile.read_text(encoding='utf-8'))
            if state['steps'] and state['steps'][-1].get('outcome')=='IN_FLIGHT':
                aid=digest([key,'model-'+str(len(state['steps']))])
                action=queue.db.execute('SELECT state FROM automation_actions WHERE id=?',(aid,)).fetchone()
                if action and action[0]=='CONFIRMED':
                    state['steps'].pop(); state['status']='RUNNING'
                    statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        class Guarded:
            def __init__(self,path): self.path=path; self.provider=None
            def decide(self,context,step,remaining):
                with queue.tx():
                    queue.owned(key,owner,fence)
                    queue.db.execute('UPDATE automation_tasks SET lease=? WHERE id=?',(queue.clock()+min(120,remaining+5),key))
                intent=queue.reserve(key,owner,fence,'model-'+str(step),'model',1,policy,model=MODEL)
                if intent['state']=='CONFIRMED':
                    receipt=strict_json(intent['receipt']); return receipt['decision'],receipt['usage']
                if intent['state']!='NEW_INTENT': raise RuntimeError('RECONCILIATION_REQUIRED')
                try:
                    if self.provider is None: self.provider=(provider_factory or CodexDecision)(self.path)
                    decision,usage=self.provider.decide(context,step,remaining)
                    queue.action_result(intent['id'],receipt={'decision':decision,'usage':usage,'cost':None})
                    queue.mark('model','RESPONSE_RECEIVED')
                    return decision,usage
                except Exception:
                    queue.action_result(intent['id'],reason='MODEL_RESPONSE_UNKNOWN_NO_FALLBACK'); raise
        result=run(docs,directory,Guarded)
        if result['status']=='LOCAL_COMPLETE':
            queue.complete(key,owner,fence,{'TASK_OUTPUT_VALID':result['quality']['passed'],'usage':result['usage']},directory/'result.html')
        elif queue.task(key)['state']!='UNKNOWN':
            queue.block(key,result['status'],owner,fence)
        return {**result,'task_id':key}
    except (PermissionError,ValueError,RuntimeError,OSError) as error:
        return {'status':'BLOCKED','reason':str(error),'fallback':'DISABLED'}
