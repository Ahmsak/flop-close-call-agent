"""Bounded local workload and opportunity decisions, separate from transport."""
import csv
import io
import time
from decimal import Decimal

from agent import amount
from ops import strict_json, verify_record, canonical, Store

def solve(job):
    if job['workload'] != 'invoice_totals_v1':
        raise ValueError('UNSUPPORTED_WORKLOAD: needs a reviewed worker')
    raw = job['input']
    if len(raw.encode()) > 65536:
        raise ValueError('WORK_BUDGET_EXCEEDED')
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames != ['sku', 'quantity', 'unit_price']:
        raise ValueError('invalid CSV columns')
    totals = {}
    for index, row in enumerate(reader):
        if index >= 1000 or None in row or any(value is None for value in row.values()):
            raise ValueError('invalid or excessive rows')
        sku = row['sku']
        if not sku or len(sku) > 64:
            raise ValueError('invalid SKU')
        quantity, price = amount(row['quantity']), amount(row['unit_price'])
        if quantity > 1000000 or price > 1000000 or quantity.as_tuple().exponent < -4 or price.as_tuple().exponent < -4:
            raise ValueError('numeric workload limit')
        totals[sku] = totals.get(sku, Decimal(0)) + quantity * price
    return {sku: str(value) for sku, value in sorted(totals.items())}

def discover(transport, store, *, room='tclk-offers', requester=None, now=None, reviewed=None):
    now = time.time() if now is None else now
    try:
        snapshot = transport.read(room)
    except Exception as error:
        store.record('', 'discovery_failed', {'source': transport.origin, 'error': type(error).__name__})
        if not transport.sandbox:
            # Mocked legacy stores have no sqlite connection; real stores persist outage bookmarks.
            if isinstance(store,Store):
                from durable import Durable
                Durable(store,clock=lambda:now).source_failed(transport.room(room),type(error).__name__)
            from opportunities import EvidenceBook, include_official, report
            book = EvidenceBook('live')
            result = report(include_official(book), book, now=now,
                            coverage={'mode': 'LIVE_READ_FAILED', 'room': room,
                                      'count': 0, 'official_sources': 'cached reviewed catalog, not refreshed'})
            result['status'] = 'SOURCE_UNAVAILABLE'
            store.record('', 'discovery_decision', result)
            return result
        return {'status': 'SOURCE_UNAVAILABLE', 'eligible': [], 'candidates': []}
    evidence={'at': now, 'origin': transport.origin, 'room': room, 'snapshot': snapshot}
    if not transport.sandbox:
        from durable import Durable
        durable=Durable(store,clock=lambda:now)
        source=transport.room(room); previous=durable.source(source)
        cursor=previous['cursor'] if previous else None
        old = strict_json(cursor) if cursor else None
        first,last=snapshot.get('first_seq'),snapshot.get('last_seq')
        lost=bool(old and (old['generation']!=snapshot['generation'] or
                  isinstance(first,int) and isinstance(old['last_seq'],int) and first>old['last_seq']+1))
        mark='HISTORY_LOST' if lost else 'PARTIAL'
        evidence['coverage_status']=mark
        durable.page(source,cursor,canonical({'generation':snapshot['generation'],'last_seq':last}),
                     [{'id':str(snapshot['generation'])+':'+str(row.get('seq')),'record':row} for row in snapshot['messages']],
                     evidence,status=mark,event_kind='discovery')
    else:
        store.record('', 'discovery', evidence)
    if not transport.sandbox or reviewed is not None:
        from opportunities import EvidenceBook, from_offer, include_official, report
        book = EvidenceBook('live') if reviewed is None else reviewed[1]
        if (book.environment == 'sandbox') != transport.sandbox or book.environment == 'replay':
            raise ValueError('DISCOVERY_ENVIRONMENT_MISMATCH')
        reviews = [] if reviewed is None else reviewed[0]
        specifications = []
        for row in snapshot['messages']:
            try:
                frame = strict_json(row['text'].removeprefix('tclk1 '))
                if frame.get('type') == 'offer':
                    parsed = from_offer(row, source=transport.room(room), observed_at=now)
                    # Reviewed contracts must bind the exact observed signed source record.
                    matching = [s for s in reviews if s.get('source_record') == row
                                and s['id'] == frame.get('id') and parsed['signature_valid']]
                    specifications.append(matching[0] if matching else parsed)
            except (ValueError, TypeError, KeyError):
                continue
        result = report(specifications + ([] if transport.sandbox else include_official(book)), book, now=now,
                        coverage={'mode':'SANDBOX_READ' if transport.sandbox else 'LIVE_READ', 'room':room, 'count':len(snapshot['messages']),
                                  'retention_status':evidence.get('coverage_status','SANDBOX_WINDOW'),
                                  'first_seq':snapshot.get('first_seq'), 'last_seq':snapshot.get('last_seq'),
                                  'official_sources':'cached reviewed catalog, not refreshed'})
        store.record('', 'discovery_decision', result)
        return result
    eligible, candidates = [], []
    for row in snapshot['messages']:
        if transport.sandbox:
            if row.get('from') != requester:
                continue
            try:
                verify_record(room, row)
                job = strict_json(row['text'])
                if job.get('kind') != 'local-job-v1':
                    continue
                if not 0 <= now-job['created_at'] <= 300 or job['deadline'] <= now:
                    raise ValueError('STALE_OPPORTUNITY')
                if job['unit'] != 'PAPER' or amount(job['max_cost']) != 0 or job['workload'] != 'invoice_totals_v1':
                    raise ValueError('UNSUPPORTED_ECONOMICS_OR_WORKLOAD')
                if amount(job['reward']) <= 0:
                    raise ValueError('NO_REWARD')
                solve(job)  # bounded deterministic feasibility check
                job['source_seen_at'] = now
                eligible.append(job)
            except Exception as error:
                candidates.append({'seq': row.get('seq'), 'blocked': str(error) or type(error).__name__})
    return {'status': 'READY' if eligible else 'NO_ELIGIBLE_TASK', 'eligible': eligible,
            'candidates': candidates, 'fetched_at': now, 'coverage': 'retained window only',
            'testnet_blocker': None if transport.sandbox else 'Official onboarding/quote contract unavailable in reviewed sources'}

def choose(jobs, model=None):
    """An optional LLM may rank eligible jobs; authority and feasibility stay in code."""
    if not jobs:
        raise ValueError('NO_ELIGIBLE_TASK')
    fallback = False
    if model:
        try:
            proposed_id = model([{'id': job['id'], 'reward': job['reward'], 'unit': job['unit']} for job in jobs])
            for job in jobs:
                if job['id'] == proposed_id:
                    return job, 'model_choice'
            fallback = True
        except Exception:
            fallback = True
    selected = sorted(jobs, key=lambda job: (-amount(job['reward']), job['deadline'], job['id']))[0]
    return selected, 'model_unavailable_fallback' if fallback else 'deterministic_zero_cost'
