"""Transactional task, source and delivery records in the existing Store.

No live sender, signer or purchase API is implemented here. Existing ops.Operator
remains the authority for Technocore writes. UTC counters survive restarts.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import time
import hashlib

from ops import canonical, digest, strict_json

DDL = [
    'CREATE TABLE IF NOT EXISTS automation_sources(id TEXT PRIMARY KEY,cursor TEXT,status TEXT,last_success REAL,last_attempt REAL,evidence TEXT)',
    'CREATE TABLE IF NOT EXISTS automation_events(source_id TEXT,event_id TEXT,version TEXT,published REAL,discovered REAL,evidence TEXT,PRIMARY KEY(source_id,event_id,version))',
    'CREATE TABLE IF NOT EXISTS automation_tasks(id TEXT PRIMARY KEY,spec TEXT,policy_hash TEXT,state TEXT,owner TEXT,lease REAL DEFAULT 0,fence INTEGER DEFAULT 0,attempts INTEGER DEFAULT 0,result TEXT,reason TEXT)',
    'CREATE TABLE IF NOT EXISTS automation_actions(id TEXT PRIMARY KEY,task_id TEXT,bucket TEXT,day TEXT,units INTEGER,state TEXT,receipt TEXT,reason TEXT)',
    'CREATE TABLE IF NOT EXISTS automation_outbox(id TEXT PRIMARY KEY,task_id TEXT,destination TEXT,state TEXT,attempts INTEGER DEFAULT 0,next_attempt REAL DEFAULT 0,receipt TEXT,reason TEXT)',
    'CREATE TABLE IF NOT EXISTS automation_health(kind TEXT PRIMARY KEY,at REAL,status TEXT)',
]

class Policy:
    def __init__(self,path): self.path=Path(path)
    def read(self):
        policy=strict_json(self.path.read_text(encoding='utf-8'))
        if policy.get('execution')!='EXECUTION_DISABLED' or str(policy.get('real_money_budget'))!='0':
            raise PermissionError('LOCAL_AUTOMATION_POLICY_REQUIRED')
        if not isinstance(policy.get('owner_did'),str): raise PermissionError('POLICY_INVALID')
        # No newly inferred inference allowance. Missing budgets remain zero.
        caps=policy.get('automation_daily_units',{})
        if not isinstance(caps,dict) or any(type(v)!=int or v<0 for v in caps.values()):
            raise PermissionError('POLICY_BUDGET_INVALID')
        allowed=policy.get('automation_task_allowlist',[])
        if not isinstance(allowed,list) or any(not isinstance(x,str) or not x for x in allowed):
            raise PermissionError('POLICY_TASK_ALLOWLIST_INVALID')
        if type(policy.get('automation_sandbox_delivery',False)) is not bool:
            raise PermissionError('POLICY_SANDBOX_DELIVERY_INVALID')
        return policy

class Durable:
    def __init__(self,store,clock=time.time):
        self.store,self.db,self.clock=store,store.db,clock
        with self.tx():
            old=self.db.execute("SELECT value FROM metadata WHERE key='automation_schema'").fetchone()
            if old and old[0]!='1': raise RuntimeError('UNKNOWN_AUTOMATION_SCHEMA')
            for statement in DDL: self.db.execute(statement)
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('automation_schema','1')")

    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise

    def mark(self,kind,status):
        with self.tx(): self._mark(kind,status)

    def _mark(self,kind,status):
        self.db.execute('INSERT OR REPLACE INTO automation_health VALUES(?,?,?)',(kind,self.clock(),status))

    def source(self,key):
        row=self.db.execute('SELECT * FROM automation_sources WHERE id=?',(key,)).fetchone()
        return dict(row) if row else None

    def page(self,source,cursor,next_cursor,events,raw,*,status='COMPLETE',event_kind=None,fail=None):
        """Commit fetched data and next unread cursor together; CAS rejects stale readers."""
        with self.tx():
            old=self.source(source)
            if old and old['cursor']!=cursor: raise RuntimeError('STALE_SOURCE_CURSOR')
            for item in events:
                self.db.execute('INSERT OR IGNORE INTO automation_events VALUES(?,?,?,?,?,?)',
                    (source,item['id'],digest(item),item.get('published_at'),self.clock(),canonical(item)))
            if event_kind: self.store.event('',event_kind,raw)
            if fail: fail()  # fault injection rolls back events and cursor, including legacy journal
            self.db.execute('INSERT OR REPLACE INTO automation_sources VALUES(?,?,?,?,?,?)',
                (source,next_cursor,status,self.clock(),self.clock(),canonical(raw)))
            self._mark('sources',status)

    def source_failed(self,key,reason):
        with self.tx():
            old=self.source(key)
            self.db.execute('INSERT OR REPLACE INTO automation_sources VALUES(?,?,?,?,?,?)',
                (key,old['cursor'] if old else None,'UNAVAILABLE',old['last_success'] if old else None,
                 self.clock(),canonical({'error':reason})))
            self._mark('sources','UNAVAILABLE')

    def enqueue(self,spec,policy):
        p=policy.read()
        for field in ('goal','input','criterion','artifact','stop','max_attempts','max_units'):
            if field not in spec: raise ValueError('TASK_CONTRACT_MISSING:'+field)
        if type(spec['max_attempts'])!=int or not 1<=spec['max_attempts']<=6: raise ValueError('TASK_ATTEMPTS_INVALID')
        if type(spec['max_units'])!=int or not 1<=spec['max_units']<=6: raise ValueError('TASK_BUDGET_INVALID')
        key=digest(spec)
        with self.tx():
            self.db.execute('INSERT OR IGNORE INTO automation_tasks(id,spec,policy_hash,state) VALUES(?,?,?,?)',
                            (key,canonical(spec),digest(p),'PENDING'))
        return key

    def task(self,key): return dict(self.db.execute('SELECT * FROM automation_tasks WHERE id=?',(key,)).fetchone())

    def resume_blocked(self,key,policy):
        """Explicit owner-authorized resume; cannot revive ambiguous external work."""
        p=policy.read()
        if key not in p.get('automation_task_allowlist',[]):
            raise PermissionError('TASK_RESUME_NOT_AUTHORIZED')
        with self.tx():
            row=self.task(key)
            if row['state']!='BLOCKED': return
            if self.db.execute("SELECT 1 FROM automation_actions WHERE task_id=? AND state IN ('SENDING','UNKNOWN')",(key,)).fetchone():
                raise PermissionError('RECONCILIATION_REQUIRED')
            self.db.execute("UPDATE automation_tasks SET state='PENDING',policy_hash=?,reason=NULL,lease=0 WHERE id=?",(digest(p),key))
            self.store.event(key,'automation_resumed',{'policy_hash':digest(p)})

    def claim(self,key,worker,seconds=30):
        if not 0<seconds<=120: raise ValueError('LEASE_LIMIT')
        with self.tx():
            row=self.task(key); spec=strict_json(row['spec'])
            if row['state'] not in ('PENDING','RUNNING') or row['lease']>self.clock(): return None
            if self.db.execute("SELECT 1 FROM automation_actions WHERE task_id=? AND state IN ('SENDING','UNKNOWN')",(key,)).fetchone():
                self.db.execute("UPDATE automation_tasks SET state='UNKNOWN',reason='RECONCILIATION_REQUIRED' WHERE id=?",(key,)); return None
            if row['attempts']>=spec['max_attempts']:
                self.db.execute("UPDATE automation_tasks SET state='FAILED',reason='ATTEMPTS_EXHAUSTED' WHERE id=?",(key,)); return None
            fence=row['fence']+1
            self.db.execute("UPDATE automation_tasks SET state='RUNNING',owner=?,lease=?,fence=?,attempts=attempts+1 WHERE id=?",
                            (worker,self.clock()+seconds,fence,key))
            return fence

    def owned(self,key,worker,fence):
        row=self.task(key)
        if row['state']!='RUNNING' or row['owner']!=worker or row['fence']!=fence or row['lease']<=self.clock():
            raise RuntimeError('LEASE_LOST')
        return row

    def reserve(self,key,worker,fence,action,bucket,units,policy,*,model=None):
        if bucket not in ('local','model','infrastructure','flop','paper') or type(units)!=int or units<1:
            raise ValueError('RESERVATION_INVALID')
        with self.tx():
            row=self.owned(key,worker,fence); p=policy.read()
            if digest(p)!=row['policy_hash']: raise PermissionError('POLICY_CHANGED')
            if 'automation_task_allowlist' in p and key not in p['automation_task_allowlist']:
                raise PermissionError('TASK_NOT_AUTHORIZED')
            if model is not None and model!=p.get('automation_model'): raise PermissionError('MODEL_NOT_AUTHORIZED')
            aid=digest([key,action]); old=self.db.execute('SELECT * FROM automation_actions WHERE id=?',(aid,)).fetchone()
            if old: return dict(old)  # Caller may not re-execute an existing intent.
            day=datetime.fromtimestamp(self.clock(),timezone.utc).date().isoformat()
            total=self.db.execute('SELECT COALESCE(SUM(units),0) FROM automation_actions WHERE bucket=? AND day=?',(bucket,day)).fetchone()[0]
            task_total=self.db.execute('SELECT COALESCE(SUM(units),0) FROM automation_actions WHERE task_id=?',(key,)).fetchone()[0]
            if total+units>p.get('automation_daily_units',{}).get(bucket,0) or task_total+units>strict_json(row['spec'])['max_units']:
                raise PermissionError('BUDGET_EXHAUSTED')
            self.db.execute('INSERT INTO automation_actions VALUES(?,?,?,?,?,?,?,?)',(aid,key,bucket,day,units,'SENDING',None,None))
            self.store.event(key,'automation_intent',{'action_id':aid,'bucket':bucket,'units':units,'cost':None})
            return {'id':aid,'state':'NEW_INTENT'}

    def action_result(self,aid,*,receipt=None,reason=None,definitive_rejection=False):
        state='CONFIRMED' if receipt is not None else 'FAILED' if definitive_rejection else 'UNKNOWN'
        with self.tx():
            row=self.db.execute('SELECT * FROM automation_actions WHERE id=?',(aid,)).fetchone()
            if row['state']=='CONFIRMED': return
            self.db.execute('UPDATE automation_actions SET state=?,receipt=?,reason=? WHERE id=?',
                            (state,canonical(receipt) if receipt is not None else None,reason,aid))
            if state in ('UNKNOWN','FAILED'):
                self.db.execute('UPDATE automation_tasks SET state=?,reason=? WHERE id=?',(state,reason,row['task_id']))

    def reconcile(self,aid,adapter):
        # Adapter is a supplied TEST double; never invent an official lookup endpoint.
        if getattr(adapter,'environment',None)!='sandbox': raise PermissionError('NO_LIVE_RECONCILIATION_ADAPTER')
        row=self.db.execute('SELECT * FROM automation_actions WHERE id=?',(aid,)).fetchone()
        if row['state']=='CONFIRMED': return strict_json(row['receipt'])
        result=adapter.lookup(aid)
        if result is not None:
            self.action_result(aid,receipt=result)
            with self.tx(): self.db.execute("UPDATE automation_tasks SET state='PENDING',lease=0 WHERE id=? AND state='UNKNOWN'",(row['task_id'],))
        return result

    def block(self,key,reason,worker=None,fence=None):
        """Retain a blocked task and its local notice atomically; never erase uncertainty."""
        with self.tx():
            row=self.task(key)
            if worker is not None: self.owned(key,worker,fence)
            elif row['state'] not in ('PENDING','BLOCKED'): return None
            if self.db.execute("SELECT 1 FROM automation_actions WHERE task_id=? AND state IN ('SENDING','UNKNOWN')",(key,)).fetchone():
                return None
            self.db.execute("UPDATE automation_tasks SET state='BLOCKED',reason=?,lease=0 WHERE id=?",(reason,key))
            nid=digest([key,'local-review','BLOCKED',reason])
            self.db.execute("INSERT OR IGNORE INTO automation_outbox(id,task_id,destination,state,reason) VALUES(?,?,?,'PENDING',?)",
                            (nid,key,'local-review',reason))
            if row['state']!='BLOCKED' or row['reason']!=reason:
                self.store.event(key,'automation_blocked',{'reason':reason,'outbox_id':nid})
        return nid

    def complete(self,key,worker,fence,result,artifact,destination='local-review',fail=None):
        if result.get('TASK_OUTPUT_VALID') is not True: raise ValueError('QUALITY_NOT_VALIDATED')
        artifact=Path(artifact)
        if not artifact.is_file(): raise ValueError('ARTIFACT_MISSING')
        evidence={**result,'artifact':str(artifact.resolve()),'artifact_hash':digest(artifact.read_text(encoding='utf-8')),
                  'NETWORK_SUBMISSION_CONFIRMED':'NOT_ATTEMPTED','NETWORK_SETTLEMENT_CONFIRMED':'UNKNOWN',
                  'REWARD_ELIGIBILITY_CONFIRMED':'UNKNOWN','cost':None}
        with self.tx():
            self.owned(key,worker,fence)
            if self.db.execute("SELECT 1 FROM automation_actions WHERE task_id=? AND state!='CONFIRMED'",(key,)).fetchone():
                raise ValueError('ACTION_UNRESOLVED')
            self.db.execute("UPDATE automation_tasks SET state='CONFIRMED',result=?,lease=0 WHERE id=?",(canonical(evidence),key))
            if fail: fail()
            nid=digest([key,destination])
            self.db.execute('INSERT OR IGNORE INTO automation_outbox(id,task_id,destination,state) VALUES(?,?,?,?)',
                            (nid,key,destination,'PENDING'))
            self.store.event(key,'automation_completed',evidence); self._mark('useful_work','CONFIRMED')
        return nid

    def deliver(self,nid,adapter,policy,*,grant=None):
        p=policy.read()
        live=getattr(adapter,'environment',None)=='telegram'
        if not live and (getattr(adapter,'environment',None)!='sandbox' or p.get('automation_sandbox_delivery') is not True):
            raise PermissionError('DELIVERY_NOT_AUTHORIZED')
        with self.tx():
            row=dict(self.db.execute('SELECT * FROM automation_outbox WHERE id=?',(nid,)).fetchone())
            # Keep obsolete blocked history, but never present it as current after
            # completion. Match the exact block-notice key, not arbitrary notices.
            if (row['state']=='PENDING' and row['reason'] is not None and
                self.task(row['task_id'])['state']=='CONFIRMED' and
                nid==digest([row['task_id'],'local-review','BLOCKED',row['reason']])):
                self.db.execute("UPDATE automation_outbox SET state='SUPERSEDED' WHERE id=?",(nid,))
                self.store.event(row['task_id'],'notification_superseded',{'notification_id':nid,'reason':'TASK_ALREADY_COMPLETED'})
                return dict(self.db.execute('SELECT * FROM automation_outbox WHERE id=?',(nid,)).fetchone())
            retry_local=(live and row['state']=='NOT_SENT' and grant and grant.get('retry_proven_not_sent') is True
                         and row['receipt'] and strict_json(row['receipt']).get('requests')==0
                         and not self.db.execute('SELECT 1 FROM metadata WHERE key=?',('telegram_wire:'+nid,)).fetchone())
            if not retry_local and (row['state']!='PENDING' or row['next_attempt']>self.clock() or row['attempts']>=(1 if live else 3)): return row
            if live:
                task=self.task(row['task_id']); result=strict_json(task['result']) if task['result'] else {}
                if (not grant or grant.get('status')!='OPEN' or grant.get('notification_id')!=nid or
                    grant.get('task_id')!=task['id'] or grant.get('attempts')!=1 or
                    grant.get('outbox_attempt',1)!=row['attempts']+1 or
                    grant.get('expires',0)<=self.clock() or grant.get('chat_id')!=adapter.chat_id or
                    grant.get('username')!=adapter.username or not str(adapter.chat_id).isdigit()):
                    raise PermissionError('EXACT_DELIVERY_GRANT_REQUIRED')
                if task['state']!='CONFIRMED' or (row['reason'] is not None and not retry_local) or nid!=digest([task['id'],'local-review']):
                    raise PermissionError('COMPLETION_NOTICE_REQUIRED')
                artifact=Path(result['artifact'])
                if (str(artifact.resolve())!=grant.get('artifact') or
                    digest(artifact.read_text(encoding='utf-8'))!=result['artifact_hash'] or
                    hashlib.sha256(artifact.read_bytes()).hexdigest()!=grant.get('sha256')):
                    raise PermissionError('ARTIFACT_CHANGED')
                permission_key='delivery_permission:'+nid
                if self.db.execute('SELECT 1 FROM metadata WHERE key=?',(permission_key,)).fetchone() and not retry_local:
                    raise PermissionError('DELIVERY_PERMISSION_CLOSED')
                if retry_local:
                    self.store.event(row['task_id'],'delivery_local_block_resolved',{'notification_id':nid,'previous_attempts':row['attempts'],'previous_receipt':strict_json(row['receipt'])})
                self.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(permission_key,canonical({**grant,'status':'CLOSED'})))
                self.store.event(row['task_id'],'delivery_intent',{'notification_id':nid,'grant_hash':digest(grant),'artifact_sha256':grant['sha256']})
            elif digest(p)!=self.task(row['task_id'])['policy_hash']: raise PermissionError('POLICY_CHANGED')
            self.db.execute("UPDATE automation_outbox SET state='SENDING',attempts=attempts+1 WHERE id=?",(nid,))
        try:
            payload=strict_json(self.task(row['task_id'])['result'])
            if live: payload={**payload,'delivery_grant':grant}
            response=adapter.send(nid,adapter.chat_id if live else row['destination'],payload)
        except Exception:
            response=None
        with self.tx():
            if response and response.get('accepted') is True and response.get('service_id'):
                state,reason='SERVICE_ACCEPTED',None
            elif live and response and response.get('rejected') is True:
                state,reason='FAILED','SERVICE_REJECTED_NO_RETRY'
            elif live and response and response.get('status')=='NOT_SENT' and response.get('requests')==0:
                state,reason='NOT_SENT','LOCAL_PREFLIGHT_BLOCKED'
            elif response and response.get('definitely_not_sent') is True:
                state,reason=('FAILED' if row['attempts']+1>=3 else 'PENDING'),'RETRY_BACKOFF'
            else: state,reason='UNKNOWN','RECONCILIATION_REQUIRED'
            self.db.execute('UPDATE automation_outbox SET state=?,receipt=?,reason=?,next_attempt=? WHERE id=?',
                            (state,canonical(response),reason,self.clock()+2**(row['attempts']+1),nid))
            self._mark('delivery',state)
        return dict(self.db.execute('SELECT * FROM automation_outbox WHERE id=?',(nid,)).fetchone())

    def reconcile_notice(self,nid,adapter):
        if getattr(adapter,'environment',None)!='sandbox': raise PermissionError('NO_LIVE_LOOKUP')
        row=self.db.execute('SELECT * FROM automation_outbox WHERE id=?',(nid,)).fetchone()
        if row['state'] not in ('SENDING','UNKNOWN'): return dict(row)
        result=adapter.lookup(nid)
        if result and result.get('accepted') is True and result.get('service_id'):
            with self.tx():
                self.db.execute("UPDATE automation_outbox SET state='SERVICE_ACCEPTED',receipt=?,reason=NULL WHERE id=?",(canonical(result),nid))
                self._mark('delivery','SERVICE_ACCEPTED')
        return dict(self.db.execute('SELECT * FROM automation_outbox WHERE id=?',(nid,)).fetchone())

    def health(self):
        marks={r['kind']:{'at':r['at'],'status':r['status']} for r in self.db.execute('SELECT * FROM automation_health')}
        for name in ('heartbeat','scheduled_start','model','sources','useful_work','delivery'): marks.setdefault(name,None)
        return {'store':self.store.diagnose(),'marks':marks,'unknown_tasks':self.db.execute("SELECT COUNT(*) FROM automation_tasks WHERE state='UNKNOWN'").fetchone()[0],
                'scope':'Local observer only; cannot detect power loss of its own host','user_read_confirmation':'UNKNOWN'}
