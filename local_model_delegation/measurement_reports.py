"""Pure descriptive aggregates; reports cannot authorize work."""
from collections import Counter, defaultdict
import math
from statistics import median
from .contracts import digest


def effective_events(events):
    replaced = {e['supersedes'] for e in events if e.get('supersedes')}
    return [e for e in events if e['event_id'] not in replaced]


def token_count(payload):
    if (payload['usage_schema'] != 'input_output_v1' or not payload['complete']
            or payload['attribution'] != 'exclusive' or payload['start'] is None or payload['end'] is None
            or payload['end'] < payload['start']): return None
    tokens=payload['tokens']
    if tokens['input'] is None or tokens['output'] is None: return None
    # The two breakdown fields are subsets, not additional tokens.
    return tokens['input']+tokens['output']


def task_usage(task, events):
    spans=[e for e in events if e['kind']=='usage' and e['payload']['allocations'] is None]
    if not spans: return None,False
    bindings={digest(e['payload']['native_binding']) for e in spans}
    groups={(e['producer'],e['payload']['group_id'],e['payload']['source_run_id']) for e in spans}
    if bindings != {digest(task['context']['native_binding'])} or len(groups)!=1: return None,False
    totals=[e for e in spans if e['payload']['role']=='total']
    selected=totals if totals else spans
    if totals and (len(totals)!=1 or totals[0]['payload']['phase']!='whole_task'): return None,False
    if not totals:
        selected=sorted(selected,key=lambda e:e['payload']['start'] if e['payload']['start'] is not None else -1)
        if any(e['payload']['expected_spans']!=len(selected) for e in selected): return None,False
        if any(a['payload']['end'] is None or b['payload']['start'] is None or a['payload']['end']>b['payload']['start'] for a,b in zip(selected,selected[1:])): return None,False
    counts=[token_count(e['payload']) for e in selected]
    if any(v is None for v in counts): return None,False
    return sum(counts),all(e['payload']['overhead_complete'] for e in selected)


def summarize_latency(values):
    values=sorted(v for v in values if type(v) in (int,float) and math.isfinite(v) and v>=0)
    return {'samples':len(values),'median':median(values) if values else None,
            'p95':values[math.ceil(.95*len(values))-1] if len(values)>=20 else None}


def quality(tasks, events):
    counts=Counter();times=defaultdict(list);reasons=Counter();closed=[]
    for task in tasks:
        own=events[task['task_id']];obs=task.get('observation',{})
        verdicts=[e for e in own if e['kind']=='local_verdict']
        deliveries=[e for e in own if e['kind']=='delivery']
        delivered=deliveries[-1] if len(deliveries)==1 else None
        attempts=obs.get('attempts',[])
        submitted=any(a.get('submitted_at') is not None or a['state']=='complete' for a in attempts)
        counts['attempts']+=len(attempts)
        if verdicts:
            first=min(verdicts,key=lambda e:e['observed_at'])['payload']
            counts['verdicts']+=1;counts['accepted']+=first['accepted']
            reasons[first['category']]+=not first['accepted']
        elif submitted: counts['missing_verdicts']+=1
        if delivered:
            result=delivered['payload']['outcome'];counts[result]+=1
            counts['closed_submitted']+=submitted
            # A contradictory delivery receipt cannot turn native rescue into local success.
            counts['local_success']+=int(result=='unchanged_local' and submitted and bool(verdicts)
                and verdicts[-1]['payload']['accepted'] and not obs.get('fallback') and not obs.get('native_task_id'))
            counts['closed']+=1;closed.append(task)
            counts['fallback']+=bool(obs.get('fallback') or result=='native_fallback')
            counts['pre_post_fallback']+=bool(obs.get('fallback') and not submitted)
            counts['post_post_fallback']+=bool(obs.get('fallback') and submitted)
            for phase,value in delivered['payload']['durations'].items(): times[phase].append(value)
        else: counts['pending_delivery']+=1
        if obs.get('reason'): reasons[obs['reason']]+=1
        for a in attempts:
            counts['uncertain_attempts']+=a['state']=='uncertain'
            if not delivered or 'inference' not in delivered['payload']['durations']:
                times['inference'].append(a.get('inference_seconds'))
        for e in own:
            if e['kind']=='incident': counts['confirmed_incidents']+=e['payload']['disposition']=='confirmed'
    return {'first_candidate':{'passed':counts['accepted'],'evaluated':counts['verdicts']},
            'local_delivery':{'passed':counts['local_success'],'evaluated':counts['closed_submitted']},
            'fallback':{'tasks':counts['fallback'],'closed_decisions':counts['closed'],
                        'before_post':counts['pre_post_fallback'],'after_post':counts['post_post_fallback']},
            'deliveries':{k:counts[k] for k in ('unchanged_local','native_edited','native_fallback','not_integrated','native_only')},
            'confirmed_incidents':counts['confirmed_incidents'],'incident_limit':'only reported incidents are known',
            'reasons':dict(reasons)}, counts, {p:summarize_latency(times[p]) for p in ('queue','inference','verification','integration','fallback','overall')}, closed


def savings(tasks, all_tasks, events, pairs):
    reasons=set();subset=0;covered=0;before_overhead=0;overhead=0;methods=set()
    for task in tasks:
        local_id=task['task_id'];matches=[p for p in pairs if p['local_task']==local_id]
        own=events[local_id];usage,overhead_complete=task_usage(task,own)
        if len(matches)!=1: reasons.add('comparable_baseline_missing');continue
        pair=matches[0];base=all_tasks.get(pair['native_task'])
        if not base: reasons.add('comparable_baseline_missing');continue
        a,b=task['context'],base['context']
        compatible=all(a[k]==b[k] for k in ('project_id','scope','environment_digest','native_binding','case_hash'))
        native_delivery=[e for e in events[base['task_id']] if e['kind']=='delivery']
        if (not compatible or a['environment_digest'] is None or a['native_binding'] is None
                or base.get('observation',{}).get('attempts') or len(native_delivery)!=1
                or native_delivery[0]['payload']['outcome']!='native_only'):
            reasons.add('baseline_incomparable_or_failed');continue
        baseline,_=task_usage(base,events[base['task_id']])
        if usage is None or baseline is None: reasons.add('native_usage_incomplete');continue
        if not any(e['kind']=='delivery' for e in own): reasons.add('delivery_pending');continue
        if not overhead_complete: reasons.add('overhead_coverage_unknown')
        delta=baseline-usage;subset+=delta;before_overhead+=delta;covered+=1;methods.add(pair['method'])
    selected={t['task_id'] for t in tasks}
    seen=set()
    for own in events.values():
        for e in own:
            if e['kind']!='usage' or e['payload']['allocations'] is None: continue
            payload=e['payload'];key=(e['producer'],payload['source_run_id'],payload['span_id'])
            if key in seen: continue
            seen.add(key)
            allocations=payload['allocations']
            if not selected.intersection(allocations):
                if not allocations: reasons.add('overhead_allocation_incomplete')
                continue
            if not math.isclose(sum(allocations.values()),1): reasons.add('overhead_allocation_incomplete')
            amount=token_count(payload)
            if amount is None: reasons.add('overhead_usage_incomplete');continue
            if any(payload['native_binding']!=all_tasks[t]['context']['native_binding'] for t in selected.intersection(allocations)):
                reasons.add('overhead_binding_mismatch');continue
            overhead+=amount*sum(v for k,v in allocations.items() if k in selected)
    complete=bool(tasks) and covered==len(tasks) and not reasons
    return {'net_native_token_proxy':before_overhead-overhead if complete else None,
            'before_allocated_overhead':before_overhead if covered==len(tasks) and tasks else None,
            'allocated_overhead':overhead,'complete_subset_before_overhead':subset if covered else None,
            'covered_tasks':covered,'total_tasks':len(tasks),'methods':sorted(methods),
            'unknown_reasons':sorted(reasons),'subscription_savings':'unknown',
            'subset_limit':'Complete subsets can be selection biased; they are not whole-cohort savings.'}


def build_report(rows, *, project_id, profile_id=None, now):
    active=effective_events(rows['events']);events=defaultdict(list)
    for event in active: events[event['task_id']].append(event)
    all_tasks={t['task_id']:t for t in rows['tasks']};groups=defaultdict(list);keys={}
    for task in rows['tasks']:
        context=task['context'];binding=task.get('observation',{}).get('binding',{})
        if context['project_id']!=project_id or profile_id and binding.get('profile_id')!=profile_id: continue
        scope={k:v for k,v in context['scope'].items() if k not in ('input_bytes','file_count')}
        key={'project_id':project_id,'model_binding':binding,'scope':scope,'environment_digest':context['environment_digest'],
             'origin':context['origin'],'native_binding':context['native_binding']}
        code=digest(key);keys[code]=key;groups[code].append(task)
    cohorts=[]
    for code,tasks in groups.items():
        q,counts,latency,closed=quality(tasks,events)
        recent=sorted(closed,key=lambda t:max(e['observed_at'] for e in events[t['task_id']] if e['kind']=='delivery'))[-30:]
        result=savings(tasks,all_tasks,events,rows.get('pairs',[]))
        recommendation='insufficient_evidence'
        if q['confirmed_incidents'] or q['first_candidate']['evaluated']>q['first_candidate']['passed']: recommendation='needs_attention'
        elif q['first_candidate']['evaluated']:
            recommendation='savings_not_demonstrated' if result['net_native_token_proxy'] is None or result['net_native_token_proxy']<=0 else 'promising_scope'
        cohorts.append({'cohort_id':code,**keys[code], 'quality':q,'last_30_closed':quality(recent,events)[0],
            'coverage':{'tasks':len(tasks),'distinct_cases':len({t['context']['case_hash'] for t in tasks}),
                        'attempts':counts['attempts'],'missing_verdicts':counts['missing_verdicts'],
                        'pending_delivery':counts['pending_delivery'],'uncertain_attempts':counts['uncertain_attempts']},
            'latency':latency,'savings':result,'recommendation':recommendation,
            'resources':{'request_bytes':sorted({t.get('observation',{}).get('request_bytes') for t in tasks if t.get('observation',{}).get('request_bytes') is not None}),
                         'pressure':'unknown','swap':'unknown','limit':'Admission estimates are not measured model residency.'}})
    return {'schema_version':1,'project_id':project_id,'generated_at':now,'cohorts':cohorts,
            'comparisons':[c for c in rows.get('comparisons',[]) if c['project_id']==project_id],
            'control':'read_only_recommendations','reliability_limit':'Descriptive counts are not a statistical reliability guarantee.'}
