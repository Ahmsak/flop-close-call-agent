"""Verify existing public records only. Requires PyNaCl; cannot sign or fetch."""
import base64
import datetime
import hashlib
import json
import re
from pathlib import Path
from nacl.signing import VerifyKey

ROOT = Path(__file__).resolve().parents[1]
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def verify_record(room, record):
    did = record['from']
    if not re.fullmatch(r'did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}', did):
        raise ValueError('unsupported DID')
    n = 0
    for char in did[len('did:key:z'):]:
        n = n * 58 + B58.index(char)
    raw = n.to_bytes((n.bit_length()+7)//8, 'big')
    if len(raw) != 34 or raw[:2] != b'\xed\x01':
        raise ValueError('invalid Ed25519 multicodec')
    sig = record['sig']
    if not re.fullmatch(r'[A-Za-z0-9_-]{85}[AQgw]', sig):
        raise ValueError('noncanonical signature encoding')
    message = f"{room}|{record['nonce']}|{record['text']}"
    VerifyKey(raw[2:]).verify(message.encode('utf-8'), base64.urlsafe_b64decode(sig+'=='))
    return did


def main():
    data = ROOT/'data'
    rooms = json.loads((ROOT/'contest.json').read_text())['rooms']['referee']
    verified, records, failures = {}, {}, []
    expected_signer = None
    for room in rooms:
        rows = [json.loads(line) for line in (data/(room+'.txt')).read_text(encoding='utf-8').splitlines() if line.strip()]
        records[room] = rows
        previous = {}
        passed = 0
        for row in rows:
            try:
                did = verify_record(room, row)
                if expected_signer is None:
                    expected_signer = did
                if did != expected_signer:
                    raise ValueError('mixed referee signers in exports')
                if row['nonce'] <= previous.get(did, -1):
                    raise ValueError('nonce not increasing within export')
                previous[did] = row['nonce']
                passed += 1
            except Exception as error:
                failures.append({'room': room, 'seq': row.get('seq'), 'error': str(error)})
        verified[room] = {'records': len(rows), 'verified': passed}
    seed = next(r for r in records['d-close1-price'] if json.loads(r['text']).get('t') == 'seed')
    (data/'signed_seed.json').write_text(json.dumps(seed,indent=2),encoding='utf-8')
    manifest_hash = hashlib.sha256((ROOT/'manifest.json').read_bytes()).hexdigest()
    negative_controls = []
    for bad_room, bad_record in [('different-room', seed), ('d-close1-price', {**seed, 'text':seed['text']+' '}), ('d-close1-price', {**seed,'nonce':seed['nonce']+1})]:
        try:
            verify_record(bad_room,bad_record)
            negative_controls.append(False)
        except Exception:
            negative_controls.append(True)
    report = {'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'algorithm':'Ed25519; exact room|nonce|text UTF-8; public multicodec ed01 key',
              'signature_created':False, 'rooms':verified, 'failures':failures,
              'tampering_rejected':negative_controls, 'seed_signature_valid':verify_record('d-close1-price',seed)==seed['from'],
              'seed_manifest_matches':json.loads(seed['text'])['package']==manifest_hash,
              'manifest_sha256':manifest_hash, 'close1_launch_trust_anchor_verified':False,
              'authority':'DRAFT/UNVERIFIED',
              'limitation':'Seed signature proves possession of stated key. No close-1 signed FLOP Labs launch binding that key to the contest was located.'}
    (data/'signature_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if failures or not all(negative_controls):
        raise ValueError('public signature verification failed')
    parsed = {room:{json.loads(r['text']).get('n'): (r,json.loads(r['text'])) for r in rows if 'n' in json.loads(r['text'])} for room,rows in records.items()}
    common = set.intersection(*(set(x) for x in parsed.values()))
    sweep = max(common)
    latest = {room:rows[sweep][1] for room,rows in parsed.items()}
    if len({v['file'] for v in latest.values()}) != 1:
        raise ValueError('common sweep archive hashes disagree across referee rooms')
    state,pnl,price,pos = [latest['d-close1-'+suffix] for suffix in ('state','pnl','price','positions')]
    flow = [v for n,(_,v) in parsed['d-close1-flow'].items() if n<=sweep]
    count = sum(len(v.get('settled',[]))+v.get('omitted',{}).get('settled',0) for v in flow)
    old_omissions = any('omitted' not in v for v in flow)
    minted, mint_mismatches, lags = 0, [], []
    opening = datetime.datetime.fromisoformat('2026-09-25T12:00:00+00:00')
    for v in sorted(flow,key=lambda v:v['n']):
        minted += len(v.get('mints',[]))+v.get('omitted',{}).get('mints',0)
        if minted != parsed['d-close1-state'][v['n']][1]['owners']:
            mint_mismatches.append(v['n'])
        envelope=parsed['d-close1-flow'][v['n']][0]
        delay=(datetime.datetime.fromisoformat(envelope['ts'].replace('Z','+00:00'))-opening).total_seconds()-300*v['n']
        lags.append((delay,v['n']))
    src = json.loads((data/'public_sources.json').read_text())
    snapshot = {'timestamp':next(s['timestamp'] for s in src if s['name']=='d-close1-state'),
                'authority':'DRAFT/UNVERIFIED', 'signatures_verified':True,
                'latest_common_sweep':sweep,'sweep_timestamp':parsed['d-close1-state'][sweep][0]['ts'],
                'registered_owner_accounts':state['owners'],'participant_humans':None,
                'leaderboard':pnl['top'],'leaderboard_mark':pnl['mark'],
                'top_score':pnl['top'][0][1] if pnl['top'] else None,
                'third_score':pnl['top'][2][1] if len(pnl['top'])>=3 else None,
                'score_type':'live mark-to-market, not final contest result',
                'reference_price':price['ref'], 'open_positions_summary':pos,
                'trade_count':None if old_omissions else count,
                'trade_count_lower_bound':count,
                'reported_trade_count':count,
                'mint_count_reconciled':minted, 'mint_mismatch_sweeps':mint_mismatches,
                'missed_range_sweeps':sum(bool(v.get('missed')) for v in flow),
                'max_observed_post_delay_seconds':max(lags)[0],
                'max_observed_post_delay_sweep':max(lags)[1],
                'trade_count_limitation':'Includes disclosed omitted counts; older flow posts may omit trades without a count. Full archives not located.',
                'sources':[s for s in src if s['name'] in rooms],
                'referee_key':seed['from'],'seed_manifest_sha256':json.loads(seed['text'])['package']}
    (data/'live_snapshot.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    print(json.dumps({'verification':report,'snapshot_summary':{k:v for k,v in snapshot.items() if k not in ('sources','leaderboard','open_positions_summary')}},indent=2))


if __name__ == '__main__': main()
