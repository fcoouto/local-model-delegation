"""Source-only plugin setup and immutable detached-runtime bundles."""
import os
from pathlib import Path
import platform
import shutil
import sys
import uuid
from .contracts import digest,text_hash,load_json
from .profiles import read_config,_quiescent
from .store import Store,atomic_json,private_dir


def initialize_state(state_dir):
    root=private_dir(Path(state_dir))
    config=read_config(root)
    if config['schema_version']!=2:raise ValueError('explicit_migration_required')
    config.setdefault('routing_enabled',False);config.setdefault('visibility_enabled',True)
    atomic_json(root/'config.json',config)
    Store(root)
    return config


def doctor(state_dir,inspect_runtime=False):
    from .validation import _qualified_isolation
    limitations=[]
    if platform.system()!='Darwin':limitations.append('macos_required')
    if sys.version_info<(3,11):limitations.append('python_311_required')
    if not _qualified_isolation():limitations.append('isolation_unsupported')
    config=read_config(state_dir)
    result={'supported':not limitations,'limitations':limitations,'routing_enabled':config.get('routing_enabled') is True,
            'visibility_enabled':config.get('visibility_enabled',True),'native_host_support':'requires_host_qualification',
            'automatic_loading':'lifecycle_unqualified','subscription_savings':'unknown'}
    if inspect_runtime:
        from .onboarding import discover_models
        from .lmstudio import Runtime
        endpoint=config.get('endpoint')
        if not endpoint:raise ValueError('explicit_endpoint_required')
        result['models']=discover_models(Runtime(endpoint,token_env=config.get('token_env')))
    return result


def prepare_update(state_dir):
    store=Store(state_dir)
    with store.db(write=True) as db:_quiescent(db)
    return {'status':'ready','state_preserved':True,'runtime_bundle':str(pin_runtime_bundle(state_dir))}


def pin_runtime_bundle(state_dir):
    from .worker import ownership
    from .onboarding import fixtures_path
    store=Store(state_dir)
    source=Path(__file__).resolve().parents[1]
    files={'repair.py':source/'repair.py','assessment-cases.json':fixtures_path()}
    files.update({'local_repair/'+p.name:p for p in (source/'local_repair').glob('*.py')})
    if any(p.is_symlink() for p in files.values()):raise ValueError('unsafe_runtime_source')
    contents={name:path.read_bytes() for name,path in files.items()}
    import hashlib
    manifest={n:hashlib.sha256(data).hexdigest() for n,data in contents.items()}
    identifier=digest(manifest)
    parent=private_dir(store.root/'runtimes');target=parent/identifier
    with ownership(store,'runtime-bundle') as owned:
        if not owned:raise ValueError('runtime_bundle_busy')
        if target.exists():
            validate_bundle(target,identifier)
            return target
        temp=private_dir(parent/('pending-'+uuid.uuid4().hex))
        try:
            for name,data in contents.items():
                path=temp/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o400)
            atomic_json(temp/'manifest.json',manifest)
            (temp/'manifest.json').chmod(0o400)
            os.rename(temp,target)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return target


def validate_bundle(path,identifier):
    import hashlib
    from .contracts import safe_path
    if path.is_symlink() or path.name!=identifier:raise ValueError('runtime_bundle_mismatch')
    manifest=load_json((path/'manifest.json').read_text())
    if digest(manifest)!=identifier:raise ValueError('runtime_bundle_mismatch')
    for name,expected in manifest.items():
        if hashlib.sha256(safe_path(path,name).read_bytes()).hexdigest()!=expected:raise ValueError('runtime_bundle_mismatch')
    return path


def prepare_uninstall(state_dir):
    from .visibility import _lock,_path
    root=Path(state_dir)
    if not root.exists():return {'status':'ready','state_preserved':True}
    config=read_config(root);config['routing_enabled']=False
    atomic_json(root/('config.json' if config['schema_version']==2 else 'profiles.json'),config)
    store=Store(root)
    with store.db(write=True) as db:_quiescent(db)
    with _lock(root):_path(root).unlink(missing_ok=True)
    return {'status':'ready','state_preserved':True,'models_preserved':True}
