"""Offline evidence classification, NOT a chain or receipt signature verifier.

Official subset: @flop-labs/contracts 0.1.1 ChatCompletionResponse (JSON text).
The capture envelope/bindings below are LOCAL, not an invented FLOP API schema.
No network, keys, signatures, SDK execution or monetary conversion occurs here.
"""
import re
import math
from ops import canonical, digest, strict_json

FORMAT = 'flop-local-capture-v1'
LEVELS = ('GATEWAY_ACCEPTED', 'INFERENCE_COMPLETED', 'SETTLEMENT_FINALIZED')
IDENTITY = ('id', 'idempotency_key', 'correlation_id', 'network', 'genesis',
            'model', 'fingerprint', 'unit')


def identifier(value):
    return isinstance(value,str) and 0<len(value)<=256 and all(33<=ord(c)<=126 for c in value)


def hash32(value):
    return isinstance(value,str) and re.fullmatch('0x[0-9a-f]{64}',value) is not None


def expected_identity(row):
    spec=strict_json(row['spec'])
    return {**{key:row[key] for key in IDENTITY if key not in ('genesis','unit')},
            'genesis':spec.get('genesis'), 'unit':spec['unit']}


def classify(expected, capture):
    """Classify a saved response bound to local request context, not authenticate it.

    Even a valid capture can be fabricated by its author. Local identity equality
    proves correlation consistency only. SETTLEMENT_FINALIZED is intentionally
    unreachable without a separately implemented independent finality verifier.
    """
    result={'level':None,'status':'UNKNOWN','settlement':'UNKNOWN',
            'cryptographic_verification':'UNSUPPORTED','can_release_reservation':False}
    try:
        if isinstance(capture,(bytes,str)):
            if len(capture)>524288: raise ValueError('EVIDENCE_TOO_LARGE')
            capture=strict_json(capture)
        if len(canonical(capture).encode())>524288: raise ValueError('EVIDENCE_TOO_LARGE')
        capture=strict_json(canonical(capture))  # reject nonfinite values in dict input too
        if not isinstance(capture,dict): raise ValueError('CAPTURE_SCHEMA_INVALID')
        if capture.get('format')!=FORMAT:
            return {**result,'status':'UNSUPPORTED','reason':'UNKNOWN_CAPTURE_FORMAT'}
        if set(capture)-{'format','identity','http_status','gateway_request_id','response','refs','settlement'}:
            raise ValueError('CAPTURE_SCHEMA_INVALID')
        if not hash32(expected.get('genesis')):
            return {**result,'status':'UNVERIFIABLE','reason':'GENESIS_NOT_PINNED'}
        if set(expected)!=set(IDENTITY) or not all(identifier(v) for v in expected.values()):
            raise ValueError('EXPECTED_IDENTITY_INVALID')
        if capture.get('identity')!=expected: raise ValueError('IDENTITY_MISMATCH')
        request_id=capture.get('gateway_request_id')
        if not identifier(request_id): raise ValueError('GATEWAY_REQUEST_ID_INVALID')
        code=capture.get('http_status')
        if type(code) is not int: raise ValueError('HTTP_STATUS_INVALID')
        refs=capture.get('refs',{})
        if not isinstance(refs,dict) or set(refs)-{'channel_id','transaction_hash','receipt_id'}:
            raise ValueError('REFERENCE_SCHEMA_INVALID')
        for key,value in refs.items():
            if value is not None and not (identifier(value) if key=='receipt_id' else hash32(value)):
                raise ValueError('REFERENCE_INVALID')
        result.update(gateway_request_id=request_id,refs=refs)
        if not 200<=code<300:
            return {**result,'reason':'HTTP_NOT_SUCCESS'}
        body=capture.get('response')
        if body is None:
            if code!=202: return {**result,'reason':'RESPONSE_MISSING'}
            result.update(level='GATEWAY_ACCEPTED',status='GATEWAY_REPORTED')
        else:
            if code!=200 or not isinstance(body,dict): raise ValueError('COMPLETION_SCHEMA_INVALID')
            if body.get('object')!='chat.completion':
                return {**result,'status':'UNSUPPORTED','reason':'UNSUPPORTED_RESPONSE_FORMAT'}
            if (not identifier(body.get('id')) or body.get('model')!=expected['model']
                    or type(body.get('created')) is not int or body['created']<0):
                raise ValueError('COMPLETION_IDENTITY_INVALID')
            if body.get('system_fingerprint') is not None and not isinstance(body['system_fingerprint'],str):
                raise ValueError('SYSTEM_FINGERPRINT_INVALID')
            choices=body.get('choices');usage=body.get('usage')
            if not isinstance(choices,list) or not 1<=len(choices)<=16 or not isinstance(usage,dict):
                raise ValueError('COMPLETION_SCHEMA_INVALID')
            indices=set()
            for choice in choices:
                if not isinstance(choice,dict): raise ValueError('CHOICE_INVALID')
                index=choice.get('index');message=choice.get('message')
                if type(index) is not int or index<0 or index in indices: raise ValueError('CHOICE_INVALID')
                indices.add(index)
                if (not isinstance(message,dict) or message.get('role')!='assistant'
                        or not isinstance(message.get('content'),str)):
                    raise ValueError('MESSAGE_INVALID')
                if choice.get('finish_reason') not in ('stop','length') or message.get('tool_calls'):
                    return {**result,'status':'UNSUPPORTED','reason':'UNSUPPORTED_COMPLETION_VARIANT'}
            for key in ('prompt_tokens','completion_tokens','total_tokens'):
                if type(usage.get(key)) is not int or usage[key]<0: raise ValueError('USAGE_INVALID')
            if usage['prompt_tokens']+usage['completion_tokens']!=usage['total_tokens']:
                raise ValueError('USAGE_CONFLICT')
            for key in ('cost_flop','gflops_used'):
                if key in usage and (type(usage[key]) not in (int,float) or usage[key]<0
                                     or not math.isfinite(usage[key])):
                    raise ValueError('REPORTED_USAGE_INVALID')
            # Official cost_flop/gflops_used are reported numbers, NOT exact chain units.
            # Do not convert them to confirmed spend or persist raw receipt extensions.
            result.update(level='INFERENCE_COMPLETED',status='GATEWAY_REPORTED',
                          completion_id=body['id'],response_hash=digest(body),
                          usage={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens')})
            if 'x_flop_receipt' in body:
                if not isinstance(body['x_flop_receipt'],dict): raise ValueError('RECEIPT_SCHEMA_INVALID')
                result.update(settlement='UNVERIFIABLE',reason='RECEIPT_NOT_AUTHENTICATED')
        claim=capture.get('settlement')
        if claim is not None:
            # Local optional/provisional claim. No field is accepted as finality proof.
            if not isinstance(claim,dict) or set(claim)!={'unit','inference_units','fee_units','finalized','escrow_closed'}:
                raise ValueError('SETTLEMENT_CLAIM_INVALID')
            if claim['unit']!=expected['unit']: raise ValueError('COST_UNIT_MISMATCH')
            if any(type(claim[k]) is not int or claim[k]<0 for k in ('inference_units','fee_units')):
                raise ValueError('EXACT_COST_UNITS_REQUIRED')
            if any(type(claim[k]) is not bool for k in ('finalized','escrow_closed')):
                raise ValueError('FINALITY_CLAIM_INVALID')
            result.update(settlement='UNVERIFIABLE',reason='INDEPENDENT_FINALITY_VERIFIER_UNAVAILABLE')
            result['settlement_claim_hash']=digest(claim)
        result['capture_hash']=digest(capture)
        return result
    except (ValueError,TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
        # Neither exception text nor raw evidence enters the public diagnostic.
        return {**result,'level':None,'status':'REJECTED_EVIDENCE','reason':'SCHEMA_OR_BINDING_MISMATCH'}


class OfflineEvidenceReader:
    """Saved-material adapter. Intentionally no network lookup or terminal verify()."""
    environment='offline'
    read_only=True

    def __init__(self, capture): self.capture=capture

    def lookup(self, identity): return self.capture
