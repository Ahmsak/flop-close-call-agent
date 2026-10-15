"""Bounded public source intake. Content is evidence, never executable authority.

Uses the existing event journal for snapshots, restart state and a local notice queue.
No new operation states, keys, delivery channel or payment adapter.
"""
import base64
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from ops import NoRedirect, digest, strict_json
from opportunities import EvidenceBook, assess, selection, action_plan, timestamp

ROOTS = (
    ('repositories', 'https://api.github.com/orgs/flop-labs/repos?per_page=100&sort=updated'),
    ('program_pages', 'https://flop.finance/'),
    ('program_pages', 'https://flop.finance/testnet/'),
    ('program_pages', 'https://flop.finance/airdrop/'),
)
MAX_BYTES, MAX_REQUESTS, TTL = 512 * 1024, 8, 900
SIGNAL = re.compile(r'contest|challenge|prize|reward|airdrop|testnet|bounty|allocation|program', re.I)

def official(url):
    p = urlsplit(url)
    return (p.scheme == 'https' and not p.username and not p.password and p.port in (None, 443)
            and (p.hostname == 'flop.finance' or
                 p.hostname == 'github.com' and p.path.startswith('/flop-labs/') or
                 p.hostname == 'api.github.com' and p.path.startswith(('/orgs/flop-labs/', '/repos/flop-labs/'))))

def identity(url):
    p = urlsplit(url)
    path = p.path.rstrip('/')
    if p.hostname == 'github.com' and path.startswith('/flop-labs/'):
        path = '/'.join(path.split('/')[:3])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, '', ''))

class PublicReader:
    environment = 'live'

    def read(self, url, timeout=5):
        if not official(url):
            raise ValueError('SOURCE_NOT_ALLOWLISTED')
        opener = urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler({}))
        request = urllib.request.Request(url, headers={'User-Agent': 'FLOP-Agent/3-readonly',
                                                     'Accept': 'application/vnd.github+json, text/html'})
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('SOURCE_TOO_LARGE')
            return {'body': raw.decode('utf-8'), 'headers': dict(response.headers),
                    'status': response.status}

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.text, self.structured = [], [], []
        self.capture, self.script = False, ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.capture, self.script = True, ''

    def handle_data(self, data):
        if self.capture:
            self.script += data
        else:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.capture:
            try:
                self.structured.append(strict_json(self.script))
            except (ValueError, TypeError):
                pass
            self.capture = False

def specification(url, title, text, observed, *, dates=None, source=None, unknown=True):
    dates = dates or {}
    # Preserve separate date claims; never guess an entry deadline from an event end.
    deadline = None
    if dates.get('entry_deadline'):
        try:
            deadline = timestamp(dates['entry_deadline'])
        except (ValueError, TypeError):
            pass
    category = 'B' if re.search(r'contest|challenge|prize|bounty', title+' '+text, re.I) else 'C'
    if re.search(r'/(testnet|airdrop)(/|$)', urlsplit(url).path):
        category = 'C'
    return {'id': 'source-'+digest(identity(url))[:20], 'canonical_url': identity(url),
            'category': category, 'title': title, 'source': source or url,
            'observed_at': observed, 'deadline': deadline, 'max_age': TTL,
            'task': {}, 'terms': text, 'reward_terms': text, 'dates': dates,
            'review_required': 'PARSE_UNKNOWN_FORMAT_AND_VERIFY_REWARD_ELIGIBILITY_ACCEPTANCE',
            'format_unknown': unknown, 'season_event_id': identity(url), 'participant_role': 'UNKNOWN',
            'real_cost': None, 'game_units': None, 'identity_cutoff': dates.get('identity_cutoff'),
            'deadlines': {key:dates.get('entry_deadline' if key=='registration' else key) for key in ('registration','submission','voting','trading','claim')},
            'results_and_claim_tracking': 'REVIEW_REQUIRED'}

def extract(url, snapshot):
    """Adapter boundary: only observed public schemas/text; no invented FLOP API."""
    body, observed = snapshot['body'], snapshot['observed_at']
    specs, links = [], []
    if '/orgs/flop-labs/repos?' in url:
        repos = strict_json(body)
        if not isinstance(repos, list):
            raise ValueError('REPOSITORY_LIST_FORMAT_UNKNOWN')
        for repo in repos[:100]:
            target = repo.get('html_url', '')
            if not official(target):
                continue
            text = repo.get('description') or 'Repository description absent; inspect published rules'
            specs.append(specification(target, repo.get('name', target), text, observed, source=url))
            if SIGNAL.search(repo.get('name', '')+' '+text):
                links.append(('repositories', 'https://api.github.com/repos/'+repo['full_name']+'/readme'))
        return specs, links
    if url.startswith('https://api.github.com/repos/'):
        record = strict_json(body)
        body = base64.b64decode(record['content'], validate=False).decode('utf-8')
        canonical_url = 'https://github.com/'+urlsplit(url).path.split('/repos/')[1].split('/readme')[0]
        specs.append(specification(canonical_url, canonical_url.rsplit('/', 1)[-1], body, observed, source=url))
        targets = re.findall(r'https://[^\s<>\)\]"\x27]+', body)
    else:
        page = Page()
        page.feed(body)
        text = ' '.join(page.text)
        # A page with no recognized schema is still a reviewable candidate.
        structured_count = 0
        for group in page.structured:
            nodes = group if isinstance(group, list) else group.get('@graph', [group]) if isinstance(group, dict) else []
            for node in nodes:
                if not isinstance(node, dict) or node.get('@type') not in ('Event', 'BusinessEvent'):
                    continue
                target = urljoin(url, node.get('url') or node.get('@id') or url)
                if not official(target):
                    continue
                dates = {key: node[field] for key, field in
                         (('start', 'startDate'), ('end', 'endDate'), ('entry_deadline', 'registrationDeadline'),
                          ('submission','submissionDeadline'),('voting','votingDeadline'),
                          ('trading','tradingDeadline'),('claim','claimDeadline'),('identity_cutoff','identityCutoff'))
                         if field in node}
                specs.append(specification(target, node.get('name', target), node.get('description', ''),
                                           observed, source=url, dates=dates, unknown=False))
                if isinstance(node.get('identifier'),(str,int)):
                    specs[-1]['season_event_id']=str(node['identifier'])
                    specs[-1]['id']='source-'+digest([identity(target),str(node['identifier'])])[:20]
                structured_count += 1
        if not structured_count and SIGNAL.search(text):
            specs.append(specification(url, urlsplit(url).path or 'FLOP official page', text, observed))
        targets = [urljoin(url, target) for target in page.links]
    for target in targets:
        if official(target) and SIGNAL.search(target):
            specs.append(specification(target, identity(target).rsplit('/', 1)[-1],
                                       'Official source links this target; reward and terms require reading',
                                       observed, source=url))
            if urlsplit(target).hostname == 'flop.finance':
                links.append(('program_pages', target.split('#')[0]))
    # Prefer actual structured claims over a bare link in the same document.
    result = {}
    for spec in sorted(specs, key=lambda s: (s['format_unknown'], not bool(s['dates'])), reverse=True):
        if spec['id'] not in result or spec['dates'] or not spec['terms'].startswith('Official source links'):
            result[spec['id']] = spec
    return list(result.values()), links

def journal(store, kind):
    return [strict_json(row['evidence']) for row in store.db.execute(
        'SELECT evidence FROM events WHERE kind=? ORDER BY seq', (kind,))]

def collect(store, *, reader=None, now=None, roots=None):
    from durable import Durable
    reader = reader or PublicReader()
    now = time.time() if now is None else now
    sandbox = reader.environment == 'sandbox'
    if roots is not None and not sandbox:
        raise ValueError('CUSTOM_SOURCE_ROOTS_SANDBOX_ONLY')
    prefix = 'sandbox_' if sandbox else ''
    durable = Durable(store, clock=lambda:now)
    snapshots = {s['url']: s for s in journal(store, prefix+'source_snapshot')}
    queue, seen, coverage = list(ROOTS if roots is None else roots), set(), []
    parents = {}
    # Resume only server-provided next-page links; re-read roots as overlap later.
    pending=[]
    for group,url in queue:
        checkpoint=durable.source(prefix+url)
        if checkpoint and checkpoint['cursor'] and (sandbox or official(checkpoint['cursor'])):
            pending.append((group,checkpoint['cursor'])); parents[checkpoint['cursor']]=url
    queue=pending+queue
    calls, started = 0, time.monotonic()
    discovered = {}
    while queue and len(seen) < 16:
        group, url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not sandbox and not official(url):
            continue
        cached = snapshots.get(url)
        state = {'group': group, 'url': url, 'last_success': cached['observed_at'] if cached else None}
        fresh = cached and 0 <= now-cached['observed_at'] <= TTL
        if fresh:
            state['status'] = 'CACHED'
        elif calls >= MAX_REQUESTS or time.monotonic()-started >= 40:
            state['status'] = 'BUDGET_NOT_READ'
        else:
            calls += 1
            source_key=prefix+parents.get(url,url)
            expected=durable.source(source_key)
            expected_cursor=expected['cursor'] if expected else None
            try:
                response = reader.read(url, timeout=5)
                if len(response['body'].encode('utf-8')) > MAX_BYTES:
                    raise ValueError('SOURCE_TOO_LARGE')
                cached = {**response, 'url': url, 'group': group, 'observed_at': now,
                          'sha256': digest(response['body'])}
                cursor=expected_cursor
                link=response.get('headers',{}).get('Link','')
                match=re.search(r'<([^>]+)>;\s*rel="?next"?',link)
                next_url=urljoin(url,match[1]) if match else None
                if next_url and not (sandbox or official(next_url)): next_url=None
                durable.page(source_key,cursor,next_url,
                    [{'id':url,'body_hash':cached['sha256']}],cached,
                    status='PARTIAL' if next_url else 'COMPLETE',event_kind=prefix+'source_snapshot')
                snapshots[url] = cached
                state.update(status='READ', last_success=now)
            except Exception as error:
                state.update(status='UNAVAILABLE', error=type(error).__name__, attempted_at=now)
                store.record('', prefix+'source_failure', state)
                durable.source_failed(prefix+parents.get(url,url),type(error).__name__)
        if cached:
            try:
                specs, links = extract(url, cached)
                queue.extend(links)
                state['candidates_extracted'] = len(specs)
                state['pagination'] = cached.get('headers', {}).get('Link', 'not followed; bounded first response')
                state['has_unread_next_page'] = bool(re.search(r'rel=["\x27]?next', state['pagination']))
                next_match=re.search(r'<([^>]+)>;\s*rel="?next"?',state['pagination'])
                if next_match:
                    next_url=urljoin(url,next_match[1])
                    if sandbox or official(next_url):
                        parents[next_url]=parents.get(url,url); queue.append((group,next_url))
                for spec in specs:
                    old = discovered.get(spec['id'])
                    if old is None or (spec['observed_at'], bool(spec['dates']), len(spec['terms'])) > (
                            old['observed_at'], bool(old['dates']), len(old['terms'])):
                        discovered[spec['id']] = spec
            except Exception as error:
                state.update(status='PARSE_UNKNOWN', error=type(error).__name__)
                spec = specification(url, 'Unparsed official source', cached['body'], cached['observed_at'])
                discovered[spec['id']] = spec
        coverage.append(state)
    # Preserve previously discovered candidates when a source disappears or budget runs out.
    previous = {entry['specification']['id']: entry for entry in journal(store, prefix+'opportunity_notice')}
    notices = []
    for key, spec in discovered.items():
        material = {k: spec[k] for k in ('canonical_url', 'title', 'terms', 'dates', 'category')}
        fingerprint = digest(material)
        if key not in previous or previous[key]['fingerprint'] != fingerprint:
            notice = {'kind': 'NEW' if key not in previous else 'MATERIAL_UPDATE',
                      'fingerprint': fingerprint, 'specification': spec,
                      'delivery': 'DELIVERY_NOT_TESTED', 'queued_at': now}
            store.record('', prefix+'opportunity_notice', notice)
            notices.append(notice)
    for key, old in previous.items():
        discovered.setdefault(key, old['specification'])
    book = EvidenceBook('sandbox' if sandbox else 'live')
    candidates = [assess(spec, book, now=now) for spec in discovered.values()]
    for candidate in candidates:
        candidate['next_steps'].insert(0, candidate['specification']['review_required'])
    return {'candidates': candidates, 'sources': coverage, 'network_reads': calls,
            'plans': [action_plan(candidate) for candidate in candidates],
            'notices': notices, 'delivery': 'DELIVERY_NOT_TESTED',
            'check_complete': not queue and all(s['status'] in ('READ', 'CACHED') and
                                               not s.get('has_unread_next_page') for s in coverage),
            'scope': 'First 100 updated repositories; fixed official pages; bounded linked pages/READMEs. No email/X connection.',
            'environment': book.environment, 'checked_at': now}

def enrich(result, store):
    intake = collect(store)
    # Catalog rules retain their reviewed identity; discovered copies do not grant new trust.
    known = {identity(c['specification']['source']) for c in result['candidates']}
    candidates = result['candidates'] + [c for c in intake['candidates']
                                          if c['specification']['canonical_url'] not in known]
    chosen = selection(candidates)
    result.update(candidates=candidates, eligible=[c for c in candidates if c['stage']=='READY'],
                  preparation=[c['id'] for c in candidates if c['stage']=='PREPARATION'],
                  selected=chosen['id'] if chosen else None, plan=action_plan(chosen) if chosen else None,
                  official_discovery=intake)
    result['coverage']['official_sources'] = intake['sources']
    result['coverage']['official_network_reads'] = intake['network_reads']
    result['coverage']['check_complete'] = (intake['check_complete'] and result['status'] != 'SOURCE_UNAVAILABLE'
        and result['coverage'].get('retention_status') not in ('PARTIAL','HISTORY_LOST'))
    result['coverage']['notice_count'] = len(intake['notices'])
    result['coverage']['delivery'] = intake['delivery']
    store.record('', 'source_discovery_decision', result)
    return result
