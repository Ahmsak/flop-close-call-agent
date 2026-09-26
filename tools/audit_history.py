"""Audit all blobs reachable from HEAD before a non-force push; never print matches."""
import hashlib,json,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def audit():
    findings=[];sizes=[];seen=set();objects=git('rev-list','--objects','HEAD').decode().splitlines()
    patterns=[('private_key_block',re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
              ('github_token',re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})')),
              ('credential_url',re.compile(rb'https?://[^\s/:]+:[^\s/@]+@')),
              ('service_secret',re.compile(rb'(?:sk-proj-|sk-ant-)[A-Za-z0-9_-]{25,}'))]
    for obj in objects:
        oid,_,path=obj.partition(' ')
        if oid in seen or git('cat-file','-t',oid).strip()!=b'blob':continue
        seen.add(oid);raw=git('cat-file','blob',oid);sizes.append((len(raw),path))
        if len(raw)>1024*1024:findings.append({'path':path,'kind':'large_blob','oid':oid})
        if re.search(r'(^|/)(\.env(?:\..*)?|credentials(?:\..*)?|id_rsa|id_ed25519)$',path,re.I) or path.endswith(('.key','.pem','.pfx','.p12')):
            findings.append({'path':path,'kind':'sensitive_filename','oid':oid})
        if re.match(r'data/(?:observer/|stage2/|.*(?:export|snapshot)|d-close1-)',path):
            findings.append({'path':path,'kind':'raw_or_live_data','oid':oid})
        for kind,pattern in patterns:
            if pattern.search(raw):findings.append({'path':path,'kind':kind,'oid':oid})
    report={'head':git('rev-parse','HEAD').decode().strip(),'commits':int(git('rev-list','--count','HEAD')),
            'unique_blobs':len(seen),'largest_blobs':[{'bytes':s,'path':p} for s,p in sorted(sizes,reverse=True)[:10]],
            'findings':findings,'status':'PASS' if not findings else 'REVIEW_REQUIRED',
            'limitations':'Pattern/path/size audit plus manual review, not mathematical proof of no secrets. Exact local path in handoff is explicitly requested. Public upstream authorship and sample IDs preserved.'}
    print(json.dumps(report,indent=2));return 1 if findings else 0


if __name__=='__main__':raise SystemExit(audit())
