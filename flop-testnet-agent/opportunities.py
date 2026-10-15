"""Discovery decisions, not operation states or payment receipts.

Evidence is supplied out of band by reviewed source adapters. A message cannot
authorize itself by including verified=true, a grant, or a synthetic fixture.
"""
import copy
import datetime as dt
import time
from pathlib import Path

from ops import canonical, digest, strict_json, verify_record

DIMENSIONS = ('current', 'direction', 'eligibility', 'reward_basis', 'result_clear',
              'acceptance_clear', 'task_supported', 'interface_available', 'cost_bounded', 'permission')

def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

class EvidenceBook:
    """Local verifier output; never populated from offer bodies or CLI config."""
    def __init__(self, environment='live'):
        if environment not in ('live', 'sandbox', 'replay'):
            raise ValueError('invalid evidence environment')
        self.environment = environment
        self.entries = {}

    def add(self, specification, facts, *, source, valid_until):
        if (specification.get('synthetic') or source.startswith('fixture:') or
                specification.get('source', '').startswith('fixture:')) and self.environment != 'sandbox':
            raise ValueError('SYNTHETIC_EVIDENCE_NOT_LIVE')
        self.entries[digest(specification)] = {
            'facts': copy.deepcopy(facts), 'source': source, 'valid_until': valid_until}

    def facts(self, specification, now):
        entry = self.entries.get(digest(specification))
        if entry and now < entry['valid_until']:
            return entry
        return {'facts': {}, 'source': None, 'valid_until': None}

def payment_contract_facts(spec, verified_rail_record):
    """Check a record already authenticated by a rail adapter against this contract.

    No live rail adapter currently supplies these records. Tests use an isolated
    verifier; a transport message saying 'funded' is never passed here as proof.
    """
    from agent import amount
    record = verified_rail_record or {}
    terms = spec.get('payment_contract', {})
    result = {'value': 'UNKNOWN', 'reason': 'PAYMENT_RECORD_MISSING_OR_MISMATCHED'}
    try:
        matches = (bool(terms) and record.get('contract_hash') == digest(terms)
                   and record.get('payer') == terms['payer']
                   and record.get('beneficiary') == terms['beneficiary']
                   and record.get('asset') == terms['asset']
                   and record.get('finalized') is True
                   and record.get('status') == 'locked'
                   and amount(record['locked_amount']) >= amount(terms['amount']) > 0
                   and record['valid_until'] >= spec['deadline'])
        if matches:
            result = {'value': 'YES', 'reason': 'AUTHENTICATED_RAIL_RECORD_MATCHES_PAYMENT_CONTRACT'}
    except (KeyError, TypeError, ValueError):
        pass
    return result

def assess(specification, book, *, now=None):
    now = time.time() if now is None else now
    spec = copy.deepcopy(specification)
    verified = book.facts(spec, now)
    facts = verified['facts']
    missing = {'eligibility':'CONFIRM_OUR_ELIGIBILITY', 'reward_basis':'PAYMENT_EVIDENCE_NOT_VERIFIED',
               'result_clear':'TASK_RESULT_CONTRACT_MISSING', 'acceptance_clear':'ACCEPTANCE_CRITERIA_UNVERIFIED',
               'interface_available':'SUBMISSION_PROTOCOL_NOT_REVIEWED', 'cost_bounded':'COST_BOUND_NOT_ESTABLISHED'}
    checks = {key: {'value': 'UNKNOWN', 'reason': missing.get(key, 'EVIDENCE_MISSING'), 'source': spec['source']} for key in DIMENSIONS}

    def set_check(key, value, reason, source=None):
        checks[key] = {'value': value, 'reason': reason, 'source': source or verified['source'] or spec['source']}

    # Only externally verified assertions influence eligibility/authority/funding.
    for key in ('eligibility', 'reward_basis', 'result_clear', 'acceptance_clear', 'interface_available', 'cost_bounded'):
        fact = facts.get(key)
        if fact and fact['value'] in ('YES', 'NO', 'UNKNOWN'):
            set_check(key, fact['value'], fact['reason'])
    set_check('permission', 'UNKNOWN', 'OWNER_GRANT_CHECKED_BY_EXECUTOR_ONLY')
    deadline = spec.get('deadline')
    expired = deadline is not None and now >= deadline
    if expired:
        set_check('current', 'NO', 'DEADLINE_PASSED')
    elif spec.get('starts_at') is not None and now < spec['starts_at']:
        set_check('current', 'NO', 'NOT_OPEN_YET')
    elif 0 <= now-spec['observed_at'] <= spec.get('max_age', 300) and deadline is not None:
        set_check('current', 'YES', 'WITHIN_OBSERVED_VALIDITY')
    else:
        set_check('current', 'UNKNOWN', 'REFRESH_SOURCE_OR_CONFIRM_DATES')

    kind = spec['category']
    if kind not in ('A', 'B', 'C'):
        raise ValueError('unknown reward category')
    if kind == 'A':
        direction = facts.get('direction')
        if direction in ('buyer_order', 'service_offer'):
            set_check('direction', 'YES' if direction == 'buyer_order' else 'NO', direction.upper())
        else:
            set_check('direction', 'UNKNOWN', 'ROLE_IS_HINT_CONFIRM_CONTRACT_AND_PARTIES')
        if spec.get('asset') == 'PAPER' or spec.get('rails') == ['paper']:
            set_check('reward_basis', 'NO', 'PAPER_RAIL_HAS_NO_VALUE')
    else:
        set_check('direction', 'YES', 'CONTEST_ENTRY' if kind == 'B' else 'PROGRAM_PARTICIPATION')
        # Future prizes/allocations do not require escrow. Official rules do.
        if facts.get('official_rules') is not True:
            set_check('reward_basis', 'UNKNOWN', 'OFFICIAL_RULES_NOT_AUTHENTICATED')

    task = spec.get('task', {})
    if task.get('workload') == 'invoice_totals_v1':
        set_check('task_supported', 'YES' if isinstance(task.get('input'), str) else 'UNKNOWN',
                  'EXISTING_INVOICE_WORKER' if isinstance(task.get('input'), str) else 'INVOICE_INPUT_MISSING')
    elif task.get('workload'):
        set_check('task_supported', 'NO', 'MISSING_WORKER:'+task['workload'])
    else:
        set_check('task_supported', 'UNKNOWN', 'TASK_INPUT_OR_WORKLOAD_UNSPECIFIED')
    if spec.get('contradictions'):
        set_check('acceptance_clear', 'NO', 'CONTRADICTORY_TERMS')
    if checks['acceptance_clear']['value'] == 'YES':
        acceptance = spec.get('acceptance', {})
        if acceptance.get('kind') != 'exact_json' or not isinstance(acceptance.get('expected'), dict):
            set_check('acceptance_clear', 'NO', 'QUALITY_VERIFIER_NOT_IMPLEMENTED')
    if checks['interface_available']['value'] == 'YES':
        submission = spec.get('submission') or {}
        if submission.get('protocol') != 'technocore-signed-post' or not submission.get('room'):
            set_check('interface_available', 'NO', 'SUBMISSION_ADAPTER_NOT_IMPLEMENTED')
    if spec.get('synthetic') and book.environment != 'sandbox':
        set_check('reward_basis', 'NO', 'SYNTHETIC_NOT_LIVE')
    if spec.get('signature_valid') is False:
        set_check('reward_basis', 'NO', 'INVALID_SOURCE_SIGNATURE')
    required = [key for key in DIMENSIONS if key != 'permission']
    hard_no = any(checks[key]['value'] == 'NO' for key in ('direction', 'eligibility', 'reward_basis'))
    if expired:
        stage = 'HISTORY'
    elif hard_no:
        stage = 'REJECTED'
    elif all(checks[key]['value'] == 'YES' for key in required):
        stage = 'READY'
    elif checks['reward_basis']['value'] == 'YES':
        stage = 'PREPARATION'
    else:
        stage = 'DISCOVERED'
    return {'id': spec['id'], 'category': kind, 'stage': stage, 'checks': checks,
            'unknown': [key for key, check in checks.items() if check['value'] == 'UNKNOWN'],
            'reasons': [check['reason'] for key, check in checks.items() if check['value'] != 'YES'],
            'specification': spec, 'assessed_at': now, 'environment': book.environment,
            'reward_received': 'UNKNOWN', 'can_execute': False,
            'next_steps': [checks[key]['reason'] for key in required if checks[key]['value'] != 'YES']
                          + ['Prepare exact envelope, then use executor owner-grant check']}

def from_offer(row, *, source, observed_at):
    frame = strict_json(row['text'].removeprefix('tclk1 '))
    try:
        verify_record('tclk-offers', row)
        signature_valid = frame.get('from') == row['from']
    except Exception:
        signature_valid = False
    return {'id': frame.get('id', 'seq-'+str(row['seq'])), 'category': 'A',
            'source': source, 'source_record': row, 'observed_at': observed_at,
            'deadline': frame['expiresMs']/1000 if type(frame.get('expiresMs')) is int else None,
            'asset': frame.get('asset'), 'rails': frame.get('rails'),
            'role_hint': frame.get('role'), 'task': {}, 'terms': frame.get('job', {}),
            'reward_terms': {'amount': frame.get('amount'), 'asset': frame.get('asset'), 'rails': frame.get('rails')},
            'signature_valid': signature_valid}

def official_catalog():
    """Reviewed historical sources; stale observations stay visible, not executable."""
    return strict_json((Path(__file__).parent/'sources'/'opportunities.json').read_text(encoding='utf-8'))

def include_official(book):
    result = []
    for entry in official_catalog():
        spec = entry['specification']
        # The checked-in source review is not loaded from caller CLI configuration.
        book.add(spec, entry['facts'], source=spec['source'], valid_until=entry['review_valid_until'])
        result.append(spec)
    return result

def selection(candidates):
    pool = [c for c in candidates if c['stage'] in ('READY', 'PREPARATION')]
    if not pool:
        return None
    # Never compare nominal token amounts across currencies, contests or unknown odds.
    return min(pool, key=lambda c: (c['stage'] != 'READY',
                                   c['checks']['cost_bounded']['value'] != 'YES',
                                   len(c['next_steps']), c['id']))

def action_plan(candidate):
    spec = candidate['specification']
    return {'candidate_id': candidate['id'], 'stage': candidate['stage'],
            'work': spec.get('task'), 'quality_check': spec.get('acceptance'),
            'submission': spec.get('submission'), 'acceptance_evidence': spec.get('acceptance_evidence'),
            'reward_evidence': spec.get('reward_evidence'), 'reward_terms': spec.get('reward_terms'),
            'gaps': candidate['next_steps'], 'external_action': 'OWNER_GRANT_REQUIRED',
            'reward_received': 'UNKNOWN'}

def report(specifications, book, *, now=None, coverage=None):
    candidates = [assess(spec, book, now=now) for spec in specifications]
    selected = selection(candidates)
    return {'status': 'READY' if any(c['stage']=='READY' for c in candidates) else 'NO_ELIGIBLE_TASK',
            'candidates': candidates, 'eligible': [c for c in candidates if c['stage']=='READY'],
            'preparation': [c['id'] for c in candidates if c['stage']=='PREPARATION'],
            'selected': selected['id'] if selected else None,
            'plan': action_plan(selected) if selected else None, 'coverage': coverage,
            'environment': book.environment}

def replay(store, *, now=None):
    store.diagnose()
    book = EvidenceBook('replay')
    specs, windows = [], []
    for row in store.db.execute("SELECT seq,evidence FROM events WHERE kind='discovery' ORDER BY seq"):
        evidence = strict_json(row['evidence'])
        if evidence.get('origin') != 'https://technocore.chat' or evidence.get('room') != 'tclk-offers':
            continue
        snapshot = evidence['snapshot']
        windows.append({'event': row['seq'], 'count': len(snapshot['messages']),
                        'first_seq': snapshot.get('first_seq'), 'last_seq': snapshot.get('last_seq'),
                        'observed_at': evidence['at']})
        for message in snapshot['messages']:
            try:
                frame = strict_json(message['text'].removeprefix('tclk1 '))
                if frame.get('type') == 'offer':
                    specs.append(from_offer(message, source='https://technocore.chat/r/tclk-offers', observed_at=evidence['at']))
            except (ValueError, TypeError, KeyError):
                continue
    # Same offer observed again remains one candidate; last observation wins.
    specs = list({s['id']: s for s in specs}.values()) + include_official(book)
    return report(specs, book, now=now, coverage={'mode':'REPLAY', 'windows': windows, 'network_reads': 0})

def local_result(candidate, book, *, now=None):
    checked = assess(candidate['specification'], book, now=now)
    if checked['stage'] != 'READY':
        raise ValueError('CANDIDATE_NOT_READY: '+','.join(checked['next_steps']))
    from jobs import solve
    result = solve(checked['specification']['task'])
    acceptance = checked['specification'].get('acceptance', {})
    if acceptance.get('kind') != 'exact_json' or result != acceptance.get('expected'):
        raise ValueError('QUALITY_CHECK_FAILED_OR_UNSUPPORTED')
    return {'kind': 'local-job-result-v1', 'job': checked['id'], 'result': result}

def prepare_selected(candidate, book, operator, envelope):
    if book.environment == 'replay' or (book.environment == 'sandbox') != operator.transport.sandbox:
        raise PermissionError('DISCOVERY_ENVIRONMENT_MISMATCH')
    now = operator.clock()
    result = local_result(candidate, book, now=now)
    spec = candidate['specification']
    destination = spec.get('submission', {})
    if destination.get('protocol') != 'technocore-signed-post' or destination.get('origin') != operator.transport.origin:
        raise ValueError('SUBMISSION_ADAPTER_MISSING')
    if envelope['text'] != canonical(result):
        raise ValueError('ENVELOPE_RESULT_MISMATCH')
    return operator.prepare(spec['id'], destination['room'], envelope,
                            valid_until=spec['deadline'], source_seen_at=spec['observed_at'])
