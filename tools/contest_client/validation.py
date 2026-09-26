"""Evidence-phase guards around unchanged official replay; no referee fixes implied."""
import json
from close_call_fold import replay


class PartialArchiveError(ValueError): pass


def validated_replay(events, config=None):
    lock=(config or {}).get('lock_sweep',2556)
    seeded=False;final=False;previous=0
    for event in events:
        if final:raise ValueError('event_after_final')
        kind=event.get('t')
        if kind=='seed':
            if seeded or previous:raise ValueError('duplicate_or_late_seed')
            seeded=True
        elif kind=='sweep':
            n=event.get('n')
            if not seeded or type(n) is not int or n<=previous:raise ValueError('sweep_order')
            if n!=previous+1:raise PartialArchiveError('missing_sweep')
            if n>lock:raise ValueError('after_lock')
            previous=n
        elif kind=='final':
            if not seeded or previous!=lock:raise PartialArchiveError('incomplete_before_final')
            final=True
        else:raise ValueError('unknown_event')
    if not final:raise PartialArchiveError('no_final_record')
    return replay([json.dumps(e) for e in events],config)
