"""Local launch review, not an official FLOP schema or finality verifier.
Only fixed public documents are fetched. Never connects to profile endpoint values.
"""
import time
from pathlib import Path
from html.parser import HTMLParser
from ops import strict_json, digest
from source_discovery import PublicReader, specification
from flop_evidence import hash32

PROFILE = Path(__file__).parent/'sources/testnet-profile.json'
SOURCES = (
    'https://docs.flop.network/networks/testnet',
    'https://docs.flop.network/docs/testnet-and-timeline',
    'https://docs.flop.network/docs/sdk-references',
    'https://flop.finance/testnet/',
    'https://flop.network/releases.json',
)
FIELDS = ('genesis','chain_spec','rpc','gateway','faucet','supported_releases','onboarding','identity_binding')

class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden=0; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden: self.parts.append(data)

def evaluate(profile, observations, *, now, cli_version='0.4.0'):
    reasons=[]
    if profile.get('network')!='testnet': reasons.append('WRONG_NETWORK')
    if profile.get('status')!='VERIFIED': reasons.append('PROFILE_UNVERIFIED')
    for field in FIELDS:
        if not profile.get(field): reasons.append('MISSING_'+field.upper())
    if profile.get('genesis') and not hash32(profile['genesis']): reasons.append('INVALID_GENESIS')
    if profile.get('required_cli') is None: reasons.append('SDK_COMPATIBILITY_UNKNOWN')
    elif profile['required_cli']!=cli_version: reasons.append('SDK_NOT_QUALIFIED')
    if profile.get('faucet_status')!='OPEN': reasons.append('FAUCET_'+str(profile.get('faucet_status','UNKNOWN')))
    seen=set();texts=[]
    for item in observations:
        url=item.get('url')
        if url not in SOURCES: reasons.append('UNTRUSTED_SOURCE'); continue
        if url in seen: reasons.append('DUPLICATE_SOURCE'); continue
        seen.add(url)
        if item.get('status')!='OK': reasons.append('SOURCE_UNAVAILABLE'); continue
        stamp=item.get('observed_at')
        if type(stamp) not in (int,float) or not 0<=now-stamp<=900:
            reasons.append('SOURCE_STALE_OR_FUTURE'); continue
        texts.append(item.get('text','').lower())
    if seen!=set(SOURCES): reasons.append('COVERAGE_INCOMPLETE')
    planned=any('testnet (planned)' in t or 'statusdraft' in t.replace(' ','') for t in texts)
    announced=any('testnet is open' in t or 'testnet (live)' in t for t in texts)
    if planned: reasons.append('OFFICIAL_PLANNED_OR_DRAFT')
    if planned and announced: reasons.append('SOURCE_CLAIMS_REQUIRE_RECONCILIATION')
    # Text and caller-supplied VERIFIED flags cannot authenticate genesis, finality,
    # release compatibility or onboarding. Until an official artifact verifier is
    # implemented even a complete review stays UNVERIFIED, never OPEN/READY.
    reasons.append('INDEPENDENT_LAUNCH_ARTIFACT_VERIFIER_UNSUPPORTED')
    return {'status':'UNVERIFIED','network':'testnet','testnet_open':'UNKNOWN',
            'execution':'EXECUTION_DISABLED','can_execute':False,
            'reasons':sorted(set(reasons)), 'cutoff':'REVIEW_REQUIRED',
            'next_step':'Review official identity, release, onboarding and separate deadline evidence; do not enroll',
            'inference_evidence_policy':'Gateway success is not settlement; UNKNOWN retains reservation'}

def check(*, reader=None, store=None, now=None):
    now=time.time() if now is None else now
    reader=reader or PublicReader()
    profile=strict_json(PROFILE.read_text(encoding='utf-8'))
    observations=[];candidates=[]
    if store is not None:
        from durable import Durable
        durable=Durable(store,clock=lambda:now)
    for url in SOURCES:
        stamp=time.time() if reader.environment=='live' else now
        item={'url':url,'observed_at':stamp,'status':'UNAVAILABLE'}
        try:
            response=reader.read(url,timeout=5)
            item['http_status']=response['status']
            if response['status']!=200: raise ValueError('NON_SUCCESS')
            body=response['body']
            if not isinstance(body,str) or len(body.encode())>512*1024: raise ValueError('BODY_LIMIT')
            parser=Text();parser.feed(body)
            text=' '.join(' '.join(parser.parts).split())
            item.update(status='OK',text=text,body_hash=digest(body))
            spec=specification(url,'Testnet launch review',text,stamp,unknown=True)
            candidates.append(spec)
            if store is not None:
                key='testnet-launch:'+url
                durable.page(key,None,None,[{'id':digest([url,body]),'source':url,'body_hash':digest(body)}],
                             {**item,'body':body},event_kind='testnet_launch_snapshot')
        except Exception as error:
            item.update(status='UNAVAILABLE',error=type(error).__name__)
            if store is not None: durable.source_failed('testnet-launch:'+url,type(error).__name__)
        observations.append(item)
    result=evaluate(profile,observations,now=time.time() if reader.environment=='live' else now)
    result.update(profile=profile,sources=observations,candidates=candidates,
                  coverage={'requests':len(SOURCES),'max_bytes_each':512*1024,'timeout_each':5,
                            'retries':0,'links_followed':False,'faucet_contacted':False},
                  environment=reader.environment)
    if store is not None: store.record('','testnet_launch_readiness',result)
    return result
