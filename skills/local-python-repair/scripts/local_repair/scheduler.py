"""Shared admission; queue position never consumes an inference slot."""
import time
from .contracts import envelope
from .profiles import read_config, read_profiles, read_profile_by_id, scope_matches
from .store import Store


def rank_profiles(brief, profiles):
    candidates=[p for p in profiles if p.get('qualification_status')=='qualified' and p.get('approval')
                and p.get('benefit_evidence',{}).get('credible') is True and scope_matches(p,brief)
                and not any(scope_matches({'scope':[s]},brief) for s in p.get('suspended_scope',[]))]
    return [p['profile_id'] for p in sorted(candidates,key=lambda p:(p['benefit_evidence'].get('native_overhead',float('inf')),
                        not p.get('owned_loaded',False),p['profile_id']))]


def admission_limit(profile, loaded, resources):
    # Task 5 replaces this conservative provisional one-slot guard with measured capacity.
    if not loaded or resources.get('pressure')!='normal' or resources.get('swapout_delta_bytes')!=0: return 0
    if not isinstance(resources.get('available_bytes'),int) or resources['available_bytes']<4*1024**3: return 0
    return 1 if type(loaded.get('capacity')) is int and loaded['capacity']>0 else 0


def schedule_once(state_dir, resources=None):
    from .worker import ownership,start_worker
    from .lmstudio import Runtime,select_loaded
    store=Store(state_dir)
    with ownership(store,'scheduler') as owned:
        if not owned: return {'status':'scheduler_busy'}
        results=[]
        for job in store.waiting_jobs():
            if time.time()>=job['route_data']['wait_until']:
                with store.db(write=True) as db: db.execute("UPDATE jobs SET reason='route_decision_required' WHERE job_id=? AND status='waiting'",(job['job_id'],))
                results.append(envelope(store.job(job['job_id']))); continue
            if read_config(store.root).get('routing_enabled') is not True and not job['route_data'].get('assessment'):
                results.append(store.decide_wait(job['job_id'],{'action':'fallback','reason':'routing_disabled'})); continue
            profiles=read_profiles(store.root)
            ids=rank_profiles(job['brief'],profiles)
            if not ids:
                results.append(store.decide_wait(job['job_id'],{'action':'fallback','reason':'no_qualified_model'})); continue
            for identifier in ids:
                try:
                    p=read_profile_by_id(store.root,identifier,job['brief']['capability'])
                    loaded=select_loaded(Runtime(p['endpoint'],token_env=p.get('token_env')).list_models(),p)
                    result=store.admit(job['job_id'],p,loaded,resources or {})
                except (ValueError,OSError): continue
                if result['status']=='reserved':
                    start_worker(store.root,result['attempt_id']); break
            results.append(envelope(store.job(job['job_id'])))
        return {'status':'scheduled','jobs':results}


def run_scheduler(state_dir):
    from .worker import ownership
    store=Store(state_dir)
    with ownership(store,'scheduler-owner') as owned:
        if not owned: return 0
        while True:
            schedule_once(state_dir)
            jobs=store.waiting_jobs()
            if not any(j['reason']!='route_decision_required' for j in jobs): return 0
            time.sleep(1)
