"""One-shot public observer. Fixed read endpoints only; no signing or credentials."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from tools.verify_public_snapshot import verify_record
from scripts.verify import verify_manifest
from close_call_fold import amount

ROOT = Path(__file__).resolve().parents[2]
PINNED_COMMIT = '66c1da36538e4b1c685417d2f66922906b13fea0'
MANIFEST_SHA = 'bae09812e25eb6f1369c611f24964f7ea0acafddfc45301a16f33f941296dafa'
# Continuity pin from the first audit, NOT an independently established authority.
EXPECTED_SIGNER = 'did:key:z6MkowHQwsx9xr84WbWN3YCnKutyBnBXkT1ChKY4uEAAMzte'
ROOMS = ('d-close1-price','d-close1-flow','d-close1-state','d-close1-positions','d-close1-pnl')
URLS = {r:f'https://technocore.chat/r/{r}/export' for r in (*ROOMS,'close1')}
MAX_BYTES = 12*1024*1024


def utcnow(): return dt.datetime.now(dt.timezone.utc)


def timestamp(value):
    date = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if date.tzinfo is None: raise ValueError('timestamp requires timezone')
    return date.astimezone(dt.timezone.utc)


def strict_json(text):
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def atomic_write(path, raw):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def save_json(path,value):
    atomic_write(path,(json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def fetch(room, *, opener=None, sleep=time.sleep, max_bytes=MAX_BYTES):
    if room not in URLS: raise ValueError('endpoint not on read-only allowlist')
    opener = opener or urllib.request.build_opener(NoRedirect)
    info = {'url':URLS[room], 'room':room, 'received_at_utc':utcnow().isoformat(), 'method':'GET'}
    for attempt in range(3):
        try:
            request = urllib.request.Request(URLS[room],headers={'User-Agent':'CloseCall-ReadOnly-Observer/1.0'})
            with opener.open(request,timeout=15) as response:
                raw = response.read(max_bytes+1)
                if len(raw)>max_bytes: raise ValueError('response_size_limit')
                info.update(http_status=response.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                            attempts=attempt+1,received_at_utc=utcnow().isoformat(),
                            generation=response.headers.get('X-Room-Generation'))
                return raw,info
        except urllib.error.HTTPError as error:
            if error.code not in (429,500,502,503,504) or attempt==2:
                info.update(http_status=error.code,error='HTTP_ERROR_AUTH_NOT_BYPASSED',attempts=attempt+1)
                return None,info
        except (urllib.error.URLError,TimeoutError,OSError,http.client.HTTPException) as error:
            if attempt==2:
                info.update(error=type(error).__name__,attempts=attempt+1);return None,info
        except ValueError as error:
            info.update(error=str(error),attempts=attempt+1);return None,info
        sleep(2**attempt)
    raise AssertionError('unreachable')


def local_pin_valid():
    raw=(ROOT/'manifest.json').read_bytes()
    pinned=subprocess.run(['git','show',f'{PINNED_COMMIT}:manifest.json'],cwd=ROOT,capture_output=True)
    return (pinned.returncode==0 and hashlib.sha256(raw).hexdigest()==MANIFEST_SHA
            and pinned.stdout==raw and not verify_manifest(ROOT,json.loads(raw)))


def inspect_room(room, raw, verifier=verify_record):
    records, faults, gaps, metadata = [], [], [], []
    previous_seq,previous_n,previous_nonce = 0,0,-1
    final_seen=False
    if raw is None:return records,[{'kind':'fetch_unavailable'}],gaps,metadata
    try:lines=raw.decode('utf-8').splitlines()
    except UnicodeDecodeError:return records,[{'kind':'bad_utf8'}],gaps,metadata
    for index,line in enumerate(lines,1):
        if not line.strip():continue
        try:
            row=strict_json(line)
            if type(row.get('seq')) is not int or row['seq']<=previous_seq:
                raise ValueError('duplicate_or_unordered_seq')
            if row['seq']!=previous_seq+1:gaps.append([previous_seq+1,row['seq']-1])
            previous_seq=row['seq']
            try:body=strict_json(row['text'])
            except (ValueError,TypeError):
                if room in ROOMS:raise
                body={'t':'conversation'}
            timestamp(row['ts'])
            if not isinstance(body,dict):raise ValueError('payload_not_object')
            if room in ROOMS:
                did=verifier(room,row)
                if did!=EXPECTED_SIGNER:raise ValueError('unconfirmed_referee_key_change')
                if type(row.get('nonce')) is not int or row['nonce']<=previous_nonce:
                    raise ValueError('nonce_order')
                previous_nonce=row['nonce']
                if final_seen:raise ValueError('event_after_final')
                if body.get('t')=='final':final_seen=True
                n=body.get('n')
                if n is not None:
                    if type(n) is not int or n<=previous_n:raise ValueError('duplicate_or_unordered_sweep')
                    if n!=previous_n+1:gaps.append({'sweeps':[previous_n+1,n-1]})
                    previous_n=n
                elif body.get('t') not in ('seed','final'):
                    raise ValueError('unknown_referee_shape')
                if body.get('t')=='seed' and (body.get('season')!='close-1' or body.get('package')!=MANIFEST_SHA):
                    raise ValueError('manifest_or_season_mismatch')
                expected_type=room.removeprefix('d-close1-')
                if body.get('t') not in (expected_type,'seed','final'):
                    raise ValueError('wrong_message_type_for_room')
                if body.get('t') in ('seed','final') and room!='d-close1-price':
                    raise ValueError('seed_or_final_wrong_room')
                kind=body.get('t')
                if n is not None and not re.fullmatch('[0-9a-f]{64}',str(body.get('file',''))):
                    raise ValueError('archive_hash_shape')
                if kind=='state' and (type(body.get('owners')) is not int or body['owners']<0):
                    raise ValueError('owner_count_shape')
                if kind=='flow':
                    if any(not isinstance(body.get(k,[]),list) for k in ('mints','settled','void','missed')):
                        raise ValueError('flow_arrays_shape')
                    omitted=body.get('omitted',{})
                    if not isinstance(omitted,dict) or any(type(v) is not int or v<0 for v in omitted.values()):
                        raise ValueError('omitted_counts_shape')
                if kind in ('pnl','positions') and not isinstance(body.get('top'),list):
                    raise ValueError('top_array_shape')
                if kind=='pnl' and amount(body.get('mark')) is None:raise ValueError('mark_shape')
                if kind=='price' and (not isinstance(body.get('ref'),dict) or amount(body['ref'].get('px')) is None):
                    raise ValueError('reference_shape')
                signature='VALID'
            else:
                signature='UNVERIFIED'
                if row.get('sig'):
                    try:verifier(room,row);signature='VALID'
                    except Exception:signature='INVALID'
            records.append((row,body))
            metadata.append({'room':room,'seq':row['seq'],'sweep':body.get('n'),
                             'message_time':row['ts'],'signature':signature,
                             'referee_authority':'UNCONFIRMED' if room in ROOMS else 'NOT_REFEREE'})
        except Exception as error:
            # Free-text conversation in close1 is expected, never treated as instructions.
            faults.append({'line':index,'kind':str(error) or type(error).__name__})
    return records,faults,gaps,metadata


def collect_dids(value):
    if isinstance(value,str):return set(re.findall(r'did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}',value))
    if isinstance(value,list):return set().union(*(collect_dids(v) for v in value)) if value else set()
    if isinstance(value,dict):return collect_dids(list(value.values()))
    return set()


def analyze(raw_rooms, *, now=None, verifier=verify_record, pin_valid=True, max_age=900):
    now=now or utcnow();parsed={};issues=[];gaps={};record_checks={}
    for room in ROOMS:
        rows,faults,missing,checks=inspect_room(room,raw_rooms.get(room),verifier)
        parsed[room]=rows;record_checks[room]=checks;gaps[room]=missing
        issues.extend({'room':room,**f} for f in faults)
    if not pin_valid:issues.append({'kind':'local_frozen_package_mismatch'})
    index={room:{b['n']:(r,b) for r,b in rows if 'n' in b} for room,rows in parsed.items()}
    common=set.intersection(*(set(v) for v in index.values()))
    trust={'SEED_SIGNATURE_VALID':'UNKNOWN','MANIFEST_HASH_MATCH':'UNKNOWN',
           'REFEREE_AUTHORITY_CONFIRMED':False,'RULES_COMMIT_PINNED':pin_valid,
           'ARCHIVE_COMPLETENESS':'PARTIAL','LEDGER_REPLAY_VERIFIED':False}
    seeds=[(r,b) for r,b in parsed['d-close1-price'] if b.get('t')=='seed']
    if len(seeds)>1:issues.append({'kind':'duplicate_seed'})
    if len(seeds)==1:
        trust['SEED_SIGNATURE_VALID']=True
        trust['MANIFEST_HASH_MATCH']=seeds[0][1].get('package')==MANIFEST_SHA and pin_valid
    # Signature and manifest are independent verdicts, even when promotion is rejected.
    for line in raw_rooms.get('d-close1-price',b'').splitlines():
        try:
            candidate=strict_json(line);body=strict_json(candidate['text'])
            if body.get('t')!='seed':continue
            trust['MANIFEST_HASH_MATCH']=body.get('package')==MANIFEST_SHA and pin_valid
            try:verifier('d-close1-price',candidate);trust['SEED_SIGNATURE_VALID']=True
            except Exception:trust['SEED_SIGNATURE_VALID']=False
            break
        except Exception:continue
    result={'timestamp':now.isoformat(),'authority':'UNCONFIRMED','trust':trust,
            'completeness':'PARTIAL','issues':issues,'gaps':gaps,'record_checks':record_checks,
            'rules_commit':PINNED_COMMIT,'referee_continuity_pin':EXPECTED_SIGNER,
            'missing_evidence':'Independent FLOP Labs close-1 binding of referee DID; full hash-addressed sweep archive',
            'archive_files':{'status':'UNAVAILABLE_NO_DOCUMENTED_RETRIEVAL_URL','hashes':[],
                             'retrieved':0,'replayed':0},'execution':'EXECUTION_DISABLED'}
    if not common:
        result.update(status='REJECTED',reason='NO_COMMON_SWEEP');return result
    n=max(common);current={room:index[room][n][1] for room in ROOMS}
    hashes={v.get('file') for v in current.values()}
    if len(hashes)!=1 or not all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for h in hashes):
        issues.append({'kind':'cross_room_archive_hash_mismatch'})
    latest={room:max(entries,default=0) for room,entries in index.items()}
    state,pnl,price,positions=(current['d-close1-'+r] for r in ('state','pnl','price','positions'))
    observed=set();minted=set();traded=set();settled_count=0;omissions=[];missed=[]
    for room,rows in parsed.items():
        for row,body in rows:
            if body.get('n',0)>n:continue
            observed|=collect_dids(body)
            if room=='d-close1-flow':
                minted|=collect_dids(body.get('mints',[]))
                # Trade IDs alone do not identify the trading accounts.
                for trade in body.get('settled',[]):
                    if isinstance(trade,dict):traded|=collect_dids(trade)
                settled_count+=len(body.get('settled',[]))+body.get('omitted',{}).get('settled',0)
                if body.get('omitted'):omissions.append({'sweep':body['n'],'omitted':body['omitted']})
                if body.get('missed'):missed.append({'sweep':body['n'],'ranges':body['missed']})
    try:
        reference_age=(now-timestamp(price['ref']['time'])).total_seconds()
        message_time=index['d-close1-state'][n][0]['ts']
        state_age=(now-timestamp(message_time)).total_seconds()
        if min(reference_age,state_age)<-60:issues.append({'kind':'future_timestamp'})
    except (KeyError,ValueError,TypeError):
        reference_age=None;state_age=None;message_time=None;issues.append({'kind':'invalid_reference_time'})
    stale=reference_age is None or state_age is None or max(reference_age,state_age)>max_age
    result.update(status='REJECTED' if issues else 'PARTIAL',latest_common_sweep=n,
        sweep_timestamp=message_time,latest_sweep_by_room=latest,cross_room_lag=len(set(latest.values()))>1,
        stale=stale,reference_age_seconds=reference_age,state_age_seconds=state_age,
        reference_price=price.get('ref'),leaderboard_mark=pnl.get('mark'),leaderboard=pnl.get('top',[]),
        open_positions_summary=positions,counts={'declared_owner_accounts':state.get('owners'),
        'observed_unique_accounts':len(observed),'observed_scope':'Signed referee payloads through common sweep; mentions, not membership proof',
        'explicit_mint_accounts':len(minted),'mint_authority_confirmed':False,
        'explicit_settled_trade_accounts':len(traded) if traded else None,
        'settled_account_limitation':'IDs in settled summaries do not identify counterparties; no inference from positions',
        'reported_settled_trades':settled_count,'humans':None},
        omitted_records=omissions,missed_ranges=missed,
        positions_complete=False,competitor_final_ranking='UNAVAILABLE_INCOMPLETE_ACCOUNT_STATE')
    result['archive_files']['hashes']=sorted({b['file'] for rows in parsed.values() for _,b in rows if b.get('n',0)<=n and isinstance(b.get('file'),str)})
    result['accounts_explicitly_minted']=sorted(minted)
    return result


def refresh(output=ROOT/'data/observer', *, fetcher=fetch):
    output=Path(output);run=output/utcnow().strftime('%Y%m%dT%H%M%S%fZ')
    raw_rooms={};sources=[]
    for room in URLS:
        raw,source=fetcher(room);sources.append(source)
        if raw is not None:
            atomic_write(run/(room+'.jsonl'),raw);raw_rooms[room]=raw
    snapshot=analyze(raw_rooms,pin_valid=local_pin_valid())
    for room in ('close1',):
        _,faults,gaps,checks=inspect_room(room,raw_rooms.get(room))
        snapshot['record_checks'][room]=checks
        snapshot['gaps'][room]=gaps
        snapshot['trading_room_faults']=faults
    snapshot['trading_room_scope']='Raw retained window, individually checked; not mixed into common-sweep referee counts'
    snapshot['sources']=sources;snapshot['evidence_directory']=str(run.resolve())
    save_json(run/'snapshot.json',snapshot)
    # Failed verification is recorded but cannot replace a prior verified observation.
    if snapshot['status']!='REJECTED':save_json(output/'latest.json',snapshot)
    save_json(output/'last_attempt.json',{'path':str(run/'snapshot.json'),'status':snapshot['status']})
    return snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data/observer')
    args=parser.parse_args();snapshot=refresh(args.output)
    print(json.dumps({k:snapshot.get(k) for k in ('status','timestamp','latest_common_sweep','trust','counts','reference_age_seconds','stale','issues')},indent=2))
    return 1 if snapshot['status']=='REJECTED' else 0


if __name__=='__main__':raise SystemExit(main())
