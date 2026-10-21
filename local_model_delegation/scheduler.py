"""Shared admission; queue position never consumes an inference slot."""
import time
from .contracts import envelope
from .profiles import read_config, read_profiles, read_profile_by_id, scope_matches
from .store import Store


def rank_profiles(brief, profiles):
    candidates=[p for p in profiles if p.get('qualification_status')=='qualified' and p.get('approval')
                and p.get('benefit_evidence',{}).get('credible') is True and scope_matches(p,brief)
                and scope_matches({'scope':p['benefit_evidence'].get('scope',[])},brief)
                and not any(scope_matches({'scope':[s]},brief) for s in p.get('suspended_scope',[]))]
    return [p['profile_id'] for p in sorted(candidates,key=lambda p:(p['benefit_evidence'].get('native_overhead',float('inf')),
                        not p.get('owned_loaded',False),p['profile_id']))]


def admission_limit(profile, loaded, resources):
    from .capacity import qualified_limit
    return qualified_limit(profile,loaded,resources)


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
            permit=job['route_data'].get('assessment')
            if permit:
                from .onboarding import authorize_assessment
                try: ids=[authorize_assessment(store.root,job['brief'],permit)['profile_id']]
                except ValueError:
                    results.append(store.decide_wait(job['job_id'],{'action':'fallback','reason':'assessment_revoked'}));continue
            if not ids:
                results.append(store.decide_wait(job['job_id'],{'action':'fallback','reason':'no_qualified_model'})); continue
            for identifier in ids:
                try:
                    p=authorize_assessment(store.root,job['brief'],permit) if permit else read_profile_by_id(store.root,identifier,job['brief']['capability'])
                    from .profiles import model_identity
                    loaded=select_loaded(Runtime(p['endpoint'],token_env=p.get('token_env')).list_models(),p,model_identity(p) if permit else None)
                    result=store.admit(job['job_id'],p,loaded,resources)
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
