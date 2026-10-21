"""Conservative macOS resource observations and measured admission limits."""
import platform
import re
import statistics
import subprocess
import time
from .contracts import digest, load_json, canonical, positive
from .store import Store

_last_swap = None


def machine_snapshot():
    global _last_swap
    result={'physical_bytes':None,'available_bytes':None,'pressure':'unknown','swapout_delta_bytes':None,
            'observed_at':time.time(),'machine_fingerprint':None}
    if platform.system()!='Darwin': return result
    try:
        def read(*argv): return subprocess.check_output(argv,text=True,timeout=3,stderr=subprocess.DEVNULL)
        physical=int(read('/usr/sbin/sysctl','-n','hw.memsize'))
        vm=read('/usr/bin/vm_stat'); page=int(re.search(r'page size of (\d+) bytes',vm)[1])
        values={k.strip():int(v) for k,v in re.findall(r'^([^:]+):\s*(\d+)\.',vm,re.M)}
        available=sum(values[k] for k in ('Pages free','Pages inactive','Pages speculative'))*page
        swap=values['Swapouts']*page
        if _last_swap is None:
            _last_swap=swap
            time.sleep(.05)
            second=read('/usr/bin/vm_stat')
            swap=int(re.search(r'^Swapouts:\s*(\d+)',second,re.M)[1])*page
        pressure=int(read('/usr/sbin/sysctl','-n','kern.memorystatus_vm_pressure_level'))
        result.update(physical_bytes=physical,available_bytes=available,pressure={1:'normal',2:'warning',4:'critical'}.get(pressure,'unknown'),
                      swapout_delta_bytes=None if _last_swap is None else max(0,swap-_last_swap),
                      machine_fingerprint=digest([platform.machine(),platform.mac_ver()[0],physical]))
        _last_swap=swap
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError): pass
    return result


def available_budget(resources, *, loaded=False):
    if (resources.get('pressure')!='normal' or type(resources.get('swapout_delta_bytes')) is not int
            or resources['swapout_delta_bytes']!=0 or not isinstance(resources.get('machine_fingerprint'),str)
            or not resources['machine_fingerprint'] or not positive(resources.get('observed_at'))
            or not -1<=time.time()-resources['observed_at']<=5
            or type(resources.get('physical_bytes')) is not int or resources['physical_bytes']<=0
            or type(resources.get('available_bytes')) is not int or not 0<=resources['available_bytes']<=resources['physical_bytes']): return 0
    # Loaded weights already appear in host usage; retain a floor for other work.
    reserve=4*1024**3 if loaded else max(4*1024**3,int(resources['physical_bytes']*.2))
    return max(0,resources['available_bytes']-reserve)


def measure_request_memory(samples):
    """Native samples: count process growth and host loss, never resident weights."""
    if not isinstance(samples,list) or len(samples)<3: raise ValueError('memory_samples_incomplete')
    first=samples[0]; previous=None; peak=0
    for sample in samples:
        if (not isinstance(sample,dict) or not positive(sample.get('observed_at'))
                or type(sample.get('process_bytes')) is not int or sample['process_bytes']<0
                or type(sample.get('available_bytes')) is not int or sample['available_bytes']<4*1024**3
                or type(sample.get('physical_bytes')) is not int or sample['available_bytes']>sample['physical_bytes']
                or sample.get('pressure')!='normal' or sample.get('swapout_delta_bytes')!=0
                or not sample.get('process_identity') or sample['process_identity']!=first.get('process_identity')
                or not sample.get('machine_fingerprint')
                or sample['machine_fingerprint']!=first.get('machine_fingerprint')
                or sample['physical_bytes']!=first.get('physical_bytes')
                or previous is not None and not 0<sample['observed_at']-previous<=2.5):
            raise ValueError('memory_samples_unqualified')
        peak=max(peak,sample['process_bytes']-first['process_bytes'],first['available_bytes']-sample['available_bytes'])
        previous=sample['observed_at']
    # Sampled peaks are observations, not upper bounds; keep at least 256 MiB margin.
    return {'peak_increment_bytes':peak,'request_bytes':peak+max(256*1024**2,(peak+1)//2)}


def assessment_request_bytes(assessment):
    # Unknown first-task cost: single-task calibration with at least 1 GiB headroom.
    return max([1024**3]+[r['memory']['request_bytes'] for r in assessment.get('receipts',{}).values() if 'memory' in r])


def qualified_limit(profile, loaded, resources):
    if not loaded or not available_budget(resources,loaded=True): return 0
    evidence=profile.get('capacity_evidence',{})
    if (evidence.get('qualified') is not True or evidence.get('machine_fingerprint')!=resources['machine_fingerprint']
            or evidence.get('settings_digest')!=digest(profile['request_settings'])
            or evidence.get('artifact_digest')!=profile['artifact']['digest']
            or evidence.get('context_length')!=loaded.get('config',{}).get('context_length')
            or type(evidence.get('limit')) is not int or evidence['limit']<1
            or type(evidence.get('batches')) is not int or evidence['batches']<3
            or not positive(evidence.get('median_slowdown')) or evidence['median_slowdown']>1.5
            or not positive(evidence.get('request_bytes')) or type(loaded.get('capacity')) is not int): return 0
    return min(loaded['capacity'],evidence['limit'],int(available_budget(resources,loaded=True)//evidence['request_bytes']))


def qualify_measurements(profile, batches, resources, context_length):
    """Native measurement receipts: three correct batches at each step, starting at one."""
    if not available_budget(resources,loaded=True): raise ValueError('resources_unqualified')
    grouped={}
    for batch in batches:
        if (set(batch)!={'concurrency','task_seconds','all_correct','request_bytes','pressure','swapout_delta_bytes'}
                or type(batch['concurrency']) is not int or batch['concurrency']<1
                or not isinstance(batch['task_seconds'],list) or len(batch['task_seconds'])!=batch['concurrency']
                or not all(positive(v) for v in batch['task_seconds']) or not positive(batch['request_bytes'])):
            raise ValueError('invalid_capacity_receipt')
        grouped.setdefault(batch['concurrency'],[]).append(batch)
    limit,baseline,slowdown,peak=0,None,None,0
    for concurrency in sorted(grouped):
        group=grouped[concurrency]
        if concurrency!=limit+1 or len(group)<3 or any(b['all_correct'] is not True or b['pressure']!='normal' or b['swapout_delta_bytes']!=0 for b in group): break
        median=statistics.median(v for b in group for v in b['task_seconds'])
        if baseline is None: baseline=median
        if median/baseline>1.5: break
        limit,slowdown=concurrency,median/baseline
        peak=max(peak,max(b['request_bytes'] for b in group))
    return {'qualified':limit>0,'limit':limit,'machine_fingerprint':resources['machine_fingerprint'],
            'settings_digest':digest(profile['request_settings']),'artifact_digest':profile['artifact']['digest'],
            'context_length':context_length,'request_bytes':peak,'batches':3 if limit else 0,'median_slowdown':slowdown}


def ensure_loaded(state_dir, profile_id):
    # shortcut: HTTP v1 has no documented estimator/non-eviction contract; qualify an adapter before implementing load POSTs.
    from .onboarding import _profile
    _profile(state_dir,profile_id)
    return {'status':'not_eligible','reason':'lifecycle_unqualified',
            'missing':['http_memory_estimate','verified_non_evicting_load_contract']}


def owned_operation(store, instance):
    identifier=instance['data'].get('owned_operation_id')
    if not identifier: return None
    with store.db() as db:
        if db.execute('PRAGMA user_version').fetchone()[0]!=2: return None
        row=db.execute("SELECT * FROM model_operations WHERE operation_id=? AND state='complete'",(identifier,)).fetchone()
    if not row:return None
    data=load_json(row['data'])
    if (data.get('instance_id')!=instance['data']['instance_id'] or data.get('kind')!='load' or data.get('ownership_verified') is not True
            or row['model_key']!=digest([instance['data']['endpoint'],instance['data']['model_id']])):return None
    return dict(row)


def release_idle(state_dir, instance_key):
    from .worker import ownership
    from .lmstudio import Runtime
    store=Store(state_dir)
    instance=store.instance(instance_key)
    model_key=digest([instance['data']['endpoint'],instance['data']['model_id']])
    with ownership(store,'recovery-'+model_key) as owned:
        if not owned:return {'status':'busy','reason':'instance_busy'}
        instance=store.instance(instance_key)
        if not owned_operation(store,instance):return {'status':'not_eligible','reason':'instance_not_owned'}
        profile=instance['data']['profile']
        operation='unload-'+instance_key+'-'+str(instance['generation'])
        with store.db(write=True) as db:
            if db.execute("SELECT 1 FROM attempts WHERE instance_key=? AND state IN ('reserved','submitting','streaming','uncertain')",(instance_key,)).fetchone():
                return {'status':'busy','reason':'instance_busy'}
            db.execute("UPDATE instances SET state='closed' WHERE instance_key=?",(instance_key,))
            previous=db.execute('SELECT state FROM model_operations WHERE operation_id=?',(operation,)).fetchone()
            if not previous:
                db.execute("INSERT INTO model_operations VALUES (?,?,'submitting',?)",(operation,model_key,canonical({'kind':'unload','instance_id':instance['data']['instance_id']})))
        runtime=Runtime(profile['endpoint'],token_env=profile.get('token_env'))
        # Unload only the exact owned identifier. A missing acknowledgement never permits a load retry.
        if not previous:
            try: runtime.unload(instance['data']['instance_id'])
            except (ValueError,OSError):
                with store.db(write=True) as db:db.execute("UPDATE model_operations SET state='uncertain' WHERE operation_id=?",(operation,))
        snapshot=runtime.list_models()
        if any(i.get('id')==instance['data']['instance_id'] for m in snapshot.get('models',[]) for i in m.get('loaded_instances',[])):
            return {'status':'uncertain','reason':'unload_unconfirmed'}
        with store.db(write=True) as db:
            db.execute("UPDATE model_operations SET state='complete' WHERE operation_id=?",(operation,))
            data={**instance['data'],'recovery_phase':'retired'}
            db.execute("UPDATE instances SET data=? WHERE instance_key=?",(canonical(data),instance_key))
        return {'status':'released','instance_key':instance_key}
