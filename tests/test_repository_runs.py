"""Repository execution stays project-bound and uses the existing campaign queue."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_model_delegation import repository_context as context
from local_model_delegation import repository_runs as repository
from local_model_delegation.contracts import validate_brief, digest
from local_model_delegation.validation import parse_proposal, source_matches
from local_model_delegation.worker import build_model_request
from .test_container_checks import environment


class RepositoryRuns(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root/'source'; source.mkdir()
        (source/'large.py').write_text('# full source\n' * 20000 + 'answer = 1\n')
        assets = self.root/'assets'; assets.mkdir()
        (assets/'run.py').write_text('print("public")\n')
        hidden = self.root/'hidden'; hidden.mkdir()
        (hidden/'run.py').write_text('print("SECRET_ORACLE")\n')
        self.public = self.freeze(source, 'public')
        self.assets = self.freeze(assets, 'public-assets')
        self.hidden = self.freeze(hidden, 'private-assets')
        spec = environment(); spec['postgres_image'] = None
        check = {'id':'public', 'argv':['/usr/local/bin/python', '/evaluator/run.py'],
                 'timeout_seconds':5, 'expected_tests':['example.test'], 'setup_argv':None}
        self.execution = {'schema_version':2, 'source':self.public, 'public_assets':self.assets,
                          'private_assets':self.hidden, 'setup_source':None, 'environment':spec,
                          'editable_paths':['large.py'], 'criteria':['Correct answer.'],
                          'public_checks':[check], 'private_checks':[{**check,'id':'hidden'}],
                          'reference_edits':{'action':'submit','summary':'Reference', 'edits':[
                              {'path':'large.py','sha256':self.public['manifest']['files']['large.py']['sha256'],
                               'changes':[{'old':'answer = 1','new':'answer = 2'}]}]},
                          'review_reference':'independent-review', 'max_cycles':3,
                          'budget':{'context_length':262144,'output_ceiling':32768,'prefill_seconds':1,
                                    'decode_tokens_per_second':100,'measurement_reference':'fictional'}}
        self.task = {'id':'example','contract':'Change answer to two.','difficulty':'moderate',
                     'context_bucket':'repository','execution':self.execution}
        self.domain = {'id':'backend','capability':'code_change','language':'python'}
        self.profile = {'fallback':{'model':'inherited','reasoning_effort':'inherited'},
                        'request_settings':{'max_output_tokens':32768,'temperature':0,'reasoning':'on'}}

    def freeze(self, root, name):
        target = self.root/name
        manifest = context.snapshot(root, [p.name for p in root.iterdir()], target)
        return {'root':str(target),'manifest':manifest}

    def brief(self):
        return repository.build_trial(self.root, 'a'*32, self.domain,self.task,self.profile,1)['brief']

    def test_full_source_is_frozen_but_never_inlined_or_hidden_in_prompt(self):
        brief = self.brief()
        validate_brief(brief)
        request = build_model_request(brief,self.profile,'instance')
        self.assertLess(len(request['input'].encode()), 40000)
        self.assertNotIn('SECRET_ORACLE',request['input'])
        self.assertNotIn('reference_edits',request['input'])
        self.assertNotIn(str(self.root),request['input'])
        self.assertNotIn('# full source',request['input'])
        self.assertTrue(source_matches(brief))
        Path(brief['source_root'],'large.py').write_text('changed')
        self.assertFalse(source_matches(brief))

    def test_exact_submit_composes_large_complete_file_without_writes(self):
        brief = self.brief()
        result = parse_proposal(json.dumps(self.execution['reference_edits']), brief)
        self.assertTrue(result['files']['large.py'].endswith('answer = 2\n'))
        self.assertGreater(len(result['files']['large.py']),100000)
        self.assertTrue(Path(brief['source_root'],'large.py').read_text().endswith('answer = 1\n'))
        with self.assertRaisesRegex(ValueError,'repository_context_action'):
            parse_proposal('{"action":"read","path":"large.py","offset":0}',brief)

    def test_schema_cannot_relax_legacy_or_expose_checker_assets(self):
        brief = self.brief()
        old = copy.deepcopy(brief); old['schema_version'] = 2
        with self.assertRaises(ValueError): validate_brief(old)
        for field in ('source','public_assets','private_assets'):
            execution = copy.deepcopy(self.execution)
            execution[field]['manifest']['digest'] = '0'*64
            with self.subTest(field=field), self.assertRaises(ValueError):
                repository.validate_execution(execution)
        brief['repository']['context'] = [{'action':'read','content':'x'*40000}]
        with self.assertRaises(ValueError): validate_brief(brief)

    def test_reference_requires_real_failure_and_all_checks(self):
        with patch('local_model_delegation.container_checks.run_check',return_value={
                'returncode':0,'reason':None,'cleanup':'verified_absent'}) as check:
            with self.assertRaisesRegex(ValueError,'project_reference_failed'):
                repository.verify_references(self.root,self.task)
            self.assertEqual(check.call_count,4)


from . import test_project_assessment_runs as campaigns
from .support import Fixture


class RepositoryCampaigns(Fixture):
    pack = campaigns.ProjectRuns.pack
    generated = campaigns.ProjectRuns.generated
    # Reuse the established queue/fake transport fixture without running legacy cases twice.
    def executable_pack(self):
        pack = campaigns.ProjectRuns.executable_pack(self)
        spec = environment(); spec['postgres_image'] = None
        for task in pack['domains'][0]['assignments']:
            old = task['execution']
            base = self.state/('fixture-'+task['id']); base.mkdir(mode=0o700)
            (base/'helper.py').write_text(old['files']['helper.py'])
            target = self.state/('snapshot-'+task['id'])
            manifest = context.snapshot(base,['helper.py'],target)
            assets = self.state/('assets-'+task['id']); assets.mkdir(mode=0o700)
            (assets/'run.py').write_text('print("fictional check")\n')
            assets_target = self.state/('asset-snapshot-'+task['id'])
            assets_manifest = context.snapshot(assets,['run.py'],assets_target)
            frozen_assets = {'root':str(assets_target),'manifest':assets_manifest}
            check = {'id':'public','argv':['/usr/local/bin/python','/evaluator/run.py'],
                     'timeout_seconds':5,'expected_tests':['test.example'],'setup_argv':None}
            task['execution'] = {'schema_version':2,'source':{'root':str(target),'manifest':manifest},
                                 'public_assets':frozen_assets,'private_assets':frozen_assets,'setup_source':None,
                                 'environment':spec,'editable_paths':['helper.py'],'criteria':old['criteria'],
                                 'public_checks':[check],'private_checks':[{**check,'id':'private'}],
                                 'reference_edits':{'action':'submit','summary':'Fix', 'edits':[
                                     {'path':'helper.py','sha256':manifest['files']['helper.py']['sha256'],
                                      'changes':[{'old':old['files']['helper.py'],'new':old['reference_files']['helper.py']}]}]},
                                 'review_reference':'review','max_cycles':3,
                                 'budget':{**old['budget'],'context_length':262144}}
        return pack

    def setUp(self):
        campaigns.ProjectRuns.setUp(self)
        self.server.context_length = 262144
        # Fake runtime response uses its fixed loaded config; widen it at the transport boundary only.
        original = self.loaded
        self.loaded = lambda: {**original(),'config':{'context_length':262144,'flash_attention':True}}
        self.binding_patch = patch('local_model_delegation.repository_runs.verification_identity',return_value={'fictional':True})
        self.binding_patch.start(); self.addCleanup(self.binding_patch.stop)

    def prepare_run(self):
        from local_model_delegation import project_runs as runs
        with patch('local_model_delegation.project_runs.verify_references',return_value={'verified':True}), \
             patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            return runs.prepare_project_run(self.state,'fictional',self.project,self.executable_pack(),'owner')

    def test_repository_context_uses_existing_queue_and_durable_limits(self):
        from local_model_delegation import project_runs as runs, onboarding
        prepared = self.prepare_run()
        self.assertEqual(prepared['preview']['max_submissions'],120)
        with patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            prepared,store,job = self.generated(prepared,answer=json.dumps({'action':'read','path':'helper.py','offset':0}))
            child = runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
            self.assertEqual(child,runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id']))
        record = onboarding._assessment(self.state,prepared['assessment_id'])
        trial = record['trials'][-1]
        self.assertEqual(trial['cycle'],1)
        self.assertEqual(trial['context_turns'],1)
        self.assertIn('content',trial['brief']['repository']['context'][-1])
        self.assertEqual(store.job(job['job_id'])['reason'],'assessment_cycle_revised')
        self.assertFalse(any('SECRET' in canonical_part for canonical_part in [json.dumps(trial['brief']['repository']['context'])]))

    def test_repository_context_errors_consume_turn_and_hide_paths(self):
        from local_model_delegation import project_runs as runs,onboarding
        with patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            prepared,store,job = self.generated(answer='{"action":"read","path":"../hidden","offset":0}')
            runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
        trial = onboarding._assessment(self.state,prepared['assessment_id'])['trials'][-1]
        self.assertEqual(trial['context_turns'],1)
        self.assertEqual(trial['brief']['repository']['context'][-1],{'error':'invalid_context_action'})

    def test_failed_public_feedback_survives_source_reads(self):
        from local_model_delegation import project_runs as runs, onboarding
        prepared = self.prepare_run()
        task = onboarding._assessment(self.state,prepared['assessment_id'])['pack']['domains'][0]['assignments'][0]
        with patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            prepared,store,job = self.generated(prepared,answer=json.dumps(task['execution']['reference_edits']))
            with patch('local_model_delegation.repository_runs.run_checks',return_value=({'public':False},{'public':None})):
                child = runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
            prior = onboarding._assessment(self.state,prepared['assessment_id'])['trials'][-1]['brief']['behavior_contract']
            self.assertIn('"public":false',prior)
            prepared,store,job = self.generated(prepared,child['trial_id'],answer='{"action":"read","path":"helper.py","offset":0}')
            runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
        brief = onboarding._assessment(self.state,prepared['assessment_id'])['trials'][-1]['brief']
        self.assertEqual(brief['behavior_contract'],prior)
        profile = onboarding._assessment(self.state,prepared['assessment_id'])['profile_snapshot']
        self.assertEqual(json.loads(build_model_request(brief,profile,'instance')['input'])['contract'],prior)


    def test_repository_proposal_and_final_hidden_checks_use_complete_snapshot(self):
        from local_model_delegation import project_runs as runs,onboarding
        from local_model_delegation.validation import prepare_verification,run_native_checks,record_verification
        prepared = self.prepare_run()
        record = onboarding._assessment(self.state,prepared['assessment_id'])
        task = record['pack']['domains'][0]['assignments'][0]
        answer = json.dumps(task['execution']['reference_edits'])
        with patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            prepared,store,job = self.generated(prepared,answer=answer)
            session = prepare_verification(self.state,job['job_id'])
            observation = {'returncode':0,'reason':None,'cleanup':'verified_absent'}
            with patch('local_model_delegation.container_checks.run_check',return_value=observation) as check:
                self.assertEqual(run_native_checks(self.state,job['job_id'])['checks'],{'public':True,'private':True})
                self.assertEqual(check.call_count,2)
            with self.assertRaisesRegex(ValueError,'assessment_already_finalizing'):
                runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
            receipt = {k:session[k] for k in ('job_id','attempt_id','native_task_id','candidate_hash','source_hash','acceptance_hash','session_token')}
            receipt.update(criteria=[True],checks={'public':True,'private':True},claims=[])
            self.assertEqual(record_verification(self.state,job['job_id'],receipt)['status'],'accepted')

    def test_repository_context_limit_is_global_and_exhaustion_is_inconclusive(self):
        from local_model_delegation import project_runs as runs,onboarding
        prepared = self.prepare_run()
        trial_id = None
        with patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            for turn in range(13):
                prepared,store,job = self.generated(prepared,trial_id,answer='{"action":"list","directory":"","offset":0}')
                result = runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
                trial_id = result['trial_id']
                if turn < 12:
                    trial = onboarding._assessment(self.state,prepared['assessment_id'])['trials'][-1]
                    self.assertEqual(trial['cycle'],1)
                    self.assertEqual(trial['context_turns'],turn+1)
            self.assertIsNone(trial_id)
            self.assertEqual(result['reason'],'context_budget_exhausted')
            record = onboarding._assessment(self.state,prepared['assessment_id'])
            report = runs.record_final(self.state,record,{'trial_id':record['trials'][-1]['trial_id'],'job_id':job['job_id']})
            self.assertEqual(report['assignments'][0]['disposition'],'unfinished')

    def test_repository_schema_is_never_admitted_as_ordinary_work(self):
        from local_model_delegation import onboarding
        from local_model_delegation.store import Store
        prepared=self.prepare_run()
        record=onboarding._assessment(self.state,prepared['assessment_id'])
        brief=record['trials'][0]['brief']
        with self.assertRaisesRegex(ValueError,'invalid_brief'):
            Store(self.state).enqueue(brief,brief['fallback'])

    def test_repository_proposal_cycle_keeps_context_allowance_and_public_only_checks(self):
        from local_model_delegation import project_runs as runs,onboarding
        prepared=self.prepare_run()
        record=onboarding._assessment(self.state,prepared['assessment_id'])
        answer=json.dumps(record['pack']['domains'][0]['assignments'][0]['execution']['reference_edits'])
        with patch('local_model_delegation.lmstudio.select_loaded',return_value=self.loaded()):
            prepared,store,job=self.generated(prepared,answer=answer)
            with patch('local_model_delegation.container_checks.run_check',return_value={
                    'returncode':0,'reason':None,'cleanup':'verified_absent'}) as check:
                runs.advance_cycle(self.state,prepared['assessment_id'],job['job_id'])
                self.assertEqual(check.call_count,1)
        trial=onboarding._assessment(self.state,prepared['assessment_id'])['trials'][-1]
        self.assertEqual(trial['cycle'],2)
        self.assertEqual(trial['context_turns'],0)
        self.assertIn('Public check results',trial['brief']['behavior_contract'])
        self.assertEqual(len(trial['brief']['repository']['context']),1)
