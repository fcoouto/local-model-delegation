import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch
from tests.support import Fixture, REPO_ROOT
from local_model_delegation.contracts import digest
from local_model_delegation.store import Store, atomic_json


class Updates(Fixture):
    def test_external_runtime_changes_do_not_enter_update_backup(self):
        from local_model_delegation.assessment_storage import workspace_root
        from local_model_delegation.store import private_dir
        api = self.api(); old, target = self.packages()
        runtime = private_dir(workspace_root(self.state)/'runtimes'/'fictional'/'node_modules')
        dependency = runtime/'dependency.js'; dependency.write_text('before')
        (runtime/'dependency-link').symlink_to('dependency.js')
        prepared = api.prepare_update(self.state, target, old)
        dependency.write_text('after')
        self.assertEqual(api.verify_update(self.state, Path(prepared['receipt']), target)['status'], 'verified')
        receipt = json.loads(Path(prepared['receipt']).read_text())
        self.assertNotIn(str(dependency), receipt['files'])
        self.assertEqual(dependency.read_text(), 'after')

    def test_misplaced_runtime_fails_before_bundle_or_backup_mutation(self):
        api = self.api(); old, target = self.packages()
        config = (self.state/'config.json').read_bytes()
        for name in ('node_modules', '.venv', 'venv'):
            runtime = self.state/'offline-reassessments'/'fictional'/'runtime'/name
            runtime.mkdir(parents=True)
            (runtime/'dependency').write_text('preserve')
            with self.subTest(name=name), patch('local_model_delegation.package.pin_runtime_bundle') as pin:
                with self.assertRaisesRegex(ValueError, 'assessment_runtime_in_state:'):
                    api.prepare_update(self.state, target, old)
                pin.assert_not_called()
            self.assertFalse((self.state/'updates').exists())
            self.assertFalse((self.state/'runtimes').exists())
            self.assertEqual((runtime/'dependency').read_text(), 'preserve')
            self.assertEqual((self.state/'config.json').read_bytes(), config)
            (runtime/'dependency').unlink(); runtime.rmdir()

    def test_arbitrary_state_symlink_still_blocks_backup(self):
        api = self.api(); old, target = self.packages()
        (self.state/'evidence-link').symlink_to(self.project/'helper.py')
        with self.assertRaisesRegex(ValueError, 'unsafe_update_file'):
            api.prepare_update(self.state, target, old)

    def test_unreadable_evidence_directory_cannot_silently_disappear(self):
        api = self.api(); self.packages()
        with patch('os.scandir', side_effect=PermissionError('unreadable evidence')):
            with self.assertRaises(PermissionError): api._files(self.state)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.updates'))
        from local_model_delegation import updates
        return updates

    def packages(self):
        paths=[]
        for version in ('0.2.0','0.3.0'):
            root=self.root/version;root.mkdir()
            for name in ('local_model_delegation','skills'):
                shutil.copytree(REPO_ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('delegate.py','plugin.json'):
                shutil.copy2(REPO_ROOT/name,root/name)
            manifest=json.loads((root/'plugin.json').read_text());manifest['version']=version
            (root/'plugin.json').write_text(json.dumps(manifest))
            paths.append(root)
        self.write_config(enabled=False)
        Store(self.state)
        (self.state/'private-evidence.txt').write_bytes(b'owner evidence')
        (self.state/'private-evidence.txt').chmod(0o600)
        return paths

    def test_package_identity_binds_contents_and_rejects_symlinks(self):
        api=self.api();old,target=self.packages()
        before=api.package_identity(target)
        (target/'delegate.py').write_text('changed')
        self.assertNotEqual(api.package_identity(target)['package_digest'],before['package_digest'])
        (target/'delegate.py').unlink();(target/'delegate.py').symlink_to(old/'delegate.py')
        with self.assertRaises(ValueError):api.package_identity(target)

    def test_numbered_release_rejects_bad_versions_and_tag_mismatch(self):
        api=self.api();old,target=self.packages()
        self.assertEqual(api.check_release(target,'v0.3.0')['version'],'0.3.0')
        with self.assertRaisesRegex(ValueError,'release_tag_mismatch'):api.check_release(target,'v0.4.0')
        manifest=json.loads((target/'plugin.json').read_text());manifest['version']='latest'
        (target/'plugin.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'invalid_release_version'):api.package_identity(target)

    def test_prepare_and_verify_preserve_settings_approval_and_history(self):
        api=self.api();old,target=self.packages()
        config=(self.state/'config.json').read_bytes();profile=(self.state/'profiles/fictional.json').read_bytes()
        with patch('local_model_delegation.lmstudio.Runtime.stream',side_effect=AssertionError('no inference')):
            prepared=api.prepare_update(self.state,target,old)
            result=api.verify_update(self.state,Path(prepared['receipt']),target)
            again=api.verify_update(self.state,Path(prepared['receipt']),target)
        self.assertEqual(result['status'],'verified');self.assertEqual(again['status'],'verified')
        self.assertEqual(result['installed']['version'],'0.3.0')
        self.assertEqual((self.state/'config.json').read_bytes(),config)
        self.assertEqual((self.state/'profiles/fictional.json').read_bytes(),profile)
        self.assertEqual((self.state/'private-evidence.txt').read_bytes(),b'owner evidence')
        receipt=json.loads(Path(prepared['receipt']).read_text())
        backup=Path(prepared['receipt']).parent/'backup'
        self.assertEqual((backup/'config.json').read_bytes(),config)
        with sqlite3.connect(backup/'state.sqlite3') as db:self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok')
        self.assertFalse(result['routing_enabled'])
        self.assertTrue(receipt['verified_at'])

    def test_same_version_different_contents_and_downgrade_are_rejected(self):
        api=self.api();old,target=self.packages()
        with self.assertRaisesRegex(ValueError,'release_downgrade'):api.prepare_update(self.state,old,target)
        manifest=json.loads((old/'plugin.json').read_text());manifest['version']='0.3.0'
        (old/'plugin.json').write_text(json.dumps(manifest));(old/'delegate.py').write_text('different')
        with self.assertRaisesRegex(ValueError,'release_version_reused'):api.prepare_update(self.state,target,old)

    def test_enabled_admission_and_uncertain_attempts_block_update(self):
        api=self.api();old,target=self.packages()
        config=json.loads((self.state/'config.json').read_text())
        for key in ('routing_enabled','assessment_policy'):
            value={**config,key:True if key=='routing_enabled' else {'enabled':True,'owner_reference':'fixture'}}
            atomic_json(self.state/'config.json',value)
            with self.assertRaisesRegex(ValueError,'admission_must_be_disabled'):api.prepare_update(self.state,target,old)
        atomic_json(self.state/'config.json',config)
        store=Store(self.state);job=store.reserve(self.brief(),self.profile(),self.loaded())
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='failed'")
            db.execute("UPDATE attempts SET state='uncertain'")
        with self.assertRaisesRegex(ValueError,'unresolved_work'):api.prepare_update(self.state,target,old)
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')

    def test_disabled_update_preserves_unsubmitted_queue_and_idle_policy_closure(self):
        api=self.api();old,target=self.packages();store=Store(self.state)
        self.write_config(enabled=True)
        waiting=store.enqueue(self.brief(),self.brief()['fallback'])
        # A completed assessment instance can retain a policy-only closure.
        prior=store.reserve(self.brief('prior'),self.profile(),self.loaded())
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='accepted' WHERE job_id=?",(prior['job_id'],))
            db.execute("UPDATE attempts SET state='complete'")
            db.execute("UPDATE instances SET state='closed'")
        self.write_config(enabled=False)
        before=store.job(waiting['job_id'])
        prepared=api.prepare_update(self.state,target,old)
        self.assertEqual(api.verify_update(self.state,Path(prepared['receipt']),target)['status'],'verified')
        self.assertEqual(store.job(waiting['job_id']),before)
        with store.db(write=True) as db:
            db.execute("UPDATE instances SET data=json_set(data,'$.recovery_phase','unload')")
        with self.assertRaisesRegex(ValueError,'unresolved_work'):api.prepare_update(self.state,target,old)

    def settled_trial(self):
        store=Store(self.state);brief=self.brief();job=store.reserve(brief,self.profile(),None)
        identifier='a'*32;trial_id='b'*32;permit={'assessment_id':identifier,'permit_token':'fixture-token'}
        with store.db(write=True) as db:
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?',(json.dumps({'assessment':permit}),job['job_id']))
        assessment={'permit_token':'fixture-token','trials':[{'trial_id':trial_id,'brief_hash':digest(brief)}],
                    'receipts':{trial_id:{'trial_id':trial_id,'job_id':job['job_id'],'passed':False,'status':'fallback_required'}}}
        path=self.state/'assessments'/identifier/'assessment.json';atomic_json(path,assessment)
        return store,job,assessment,path

    def test_recorded_assessment_rejection_is_settled_without_rewriting_job(self):
        api=self.api();old,target=self.packages();store,job,assessment,path=self.settled_trial()
        before=store.job(job['job_id'])
        prepared=api.prepare_update(self.state,target,old)
        self.assertEqual(prepared['settled_assessment_jobs'],1)
        self.assertEqual(store.job(job['job_id']),before)
        self.assertEqual(api.verify_update(self.state,Path(prepared['receipt']),target)['status'],'verified')

    def test_missing_or_mismatched_assessment_evidence_stays_blocked(self):
        api=self.api();old,target=self.packages();store,job,assessment,path=self.settled_trial()
        for field in ('permit_token','brief_hash','receipt'):
            bad=json.loads(json.dumps(assessment))
            if field=='permit_token':bad['permit_token']='wrong'
            elif field=='brief_hash':bad['trials'][0]['brief_hash']='0'*64
            else:bad['receipts']={}
            atomic_json(path,bad)
            with self.assertRaisesRegex(ValueError,'unresolved_work'):api.prepare_update(self.state,target,old)
        atomic_json(path,assessment)
        with store.db(write=True) as db:
            db.execute('INSERT INTO fallback_dispatches VALUES (?,?,?,?,?)',(job['job_id'],'token','external',None,'dispatch_uncertain'))
        with self.assertRaisesRegex(ValueError,'unresolved_work'):api.prepare_update(self.state,target,old)

    def test_changed_state_or_wrong_package_is_not_verified_or_rolled_back(self):
        api=self.api();old,target=self.packages();prepared=api.prepare_update(self.state,target,old)
        receipt=Path(prepared['receipt'])
        with self.assertRaisesRegex(ValueError,'installed_package_mismatch'):api.verify_update(self.state,receipt,old)
        changed=b'newer owner evidence';(self.state/'private-evidence.txt').write_bytes(changed)
        with self.assertRaisesRegex(ValueError,'state_changed'):api.verify_update(self.state,receipt,target)
        self.assertEqual((self.state/'private-evidence.txt').read_bytes(),changed)
        self.assertIsNone(json.loads(receipt.read_text())['verified_at'])

    def test_new_history_after_preparation_is_detected(self):
        api=self.api();old,target=self.packages();prepared=api.prepare_update(self.state,target,old)
        Store(self.state).reserve(self.brief(),self.profile(),None)
        with self.assertRaisesRegex(ValueError,'state_changed'):api.verify_update(self.state,Path(prepared['receipt']),target)

    def test_history_trigger_changes_are_detected(self):
        api=self.api();old,target=self.packages();prepared=api.prepare_update(self.state,target,old)
        with Store(self.state).db() as db:db.execute('DROP TRIGGER finish_native_dispatch')
        with self.assertRaisesRegex(ValueError,'state_changed'):api.verify_update(self.state,Path(prepared['receipt']),target)

    def test_database_named_evidence_is_preserved(self):
        api=self.api();old,target=self.packages()
        evidence=self.state/'state.sqlite3.audit';evidence.write_text('previous audit')
        prepared=api.prepare_update(self.state,target,old)
        evidence.write_text('changed audit')
        with self.assertRaisesRegex(ValueError,'state_changed'):api.verify_update(self.state,Path(prepared['receipt']),target)

    def test_verification_does_not_initialize_missing_state(self):
        api=self.api();old,target=self.packages();missing=self.root/'missing-state'
        with self.assertRaisesRegex(ValueError,'update_state_missing'):
            api.verify_update(missing,missing/'updates'/('a'*32)/'receipt.json',target)
        self.assertFalse(missing.exists())

    def test_cli_reports_version_and_prepares_then_verifies_update(self):
        import subprocess,sys
        old,target=self.packages()
        def invoke(*args):
            result=subprocess.run([sys.executable,'-B',str(REPO_ROOT/'delegate.py'),'--state-dir',str(self.state),*args],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            return json.loads(result.stdout)
        self.assertEqual(invoke('version','--root',str(target))['version'],'0.3.0')
        prepared=invoke('prepare-update','--target',str(target),'--installed',str(old))
        self.assertEqual(invoke('verify-update','--receipt',prepared['receipt'],'--installed',str(target))['status'],'verified')

    def test_release_archive_requires_clean_matching_tag_and_contains_only_tracked_files(self):
        import subprocess,zipfile
        api=self.api();old,target=self.packages()
        def git(*args):
            return subprocess.run(['git','-C',str(target),*args],check=True,capture_output=True,text=True).stdout.strip()
        git('init','-q');git('add','.')
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture release')
        git('tag','v0.3.0')
        output=self.root/'dist'
        build=getattr(api,'build_release',None);self.assertTrue(callable(build),'release builder missing')
        result=build(target,'v0.3.0',output)
        self.assertEqual(result['source_revision'],git('rev-parse','HEAD'))
        with zipfile.ZipFile(result['archive']) as archive:
            self.assertIn('local-model-delegation/plugin.json',archive.namelist())
            self.assertFalse(any('/.git/' in n for n in archive.namelist()))
            archive.extractall(self.root/'extracted')
        self.assertEqual(api.package_identity(self.root/'extracted/local-model-delegation'),api.package_identity(target))
        (target/'private.txt').write_text('do not package')
        with self.assertRaisesRegex(ValueError,'release_checkout_dirty'):build(target,'v0.3.0',self.root/'other-dist')
        (target/'private.txt').unlink()
        (target/'.git/info/exclude').write_text('local_model_delegation/untracked.py\n')
        (target/'local_model_delegation/untracked.py').write_text('not packaged')
        with self.assertRaisesRegex(ValueError,'release_archive_mismatch'):build(target,'v0.3.0',self.root/'ignored-dist')
