import copy
import json
import time
from unittest.mock import patch

from local_model_delegation.contracts import digest, validate_brief
from local_model_delegation.store import Store
from local_model_delegation.worker import build_model_request, context_fits, run_local_attempt
from tests.support import FakeRuntime, Fixture


class GenerationBudgets(Fixture):
    def setUp(self):
        super().setUp()
        recovery = patch('local_model_delegation.recovery.request_recovery')
        recovery.start()
        self.addCleanup(recovery.stop)

    def prepare(self, *, budget=None, ceiling=1024, **kwargs):
        server = FakeRuntime(**kwargs)
        self.addCleanup(server.close)
        profile = self.profile()
        profile['endpoint'] = server.endpoint
        profile['request_settings']['max_output_tokens'] = ceiling
        profile['approval']['request_settings'] = copy.deepcopy(profile['request_settings'])
        self.write_config(profile)
        brief = self.brief()
        if budget is not None:
            brief['task_requirements']['max_output_tokens'] = budget
        loaded = {**self.loaded(), 'endpoint':server.endpoint}
        store = Store(self.state)
        return server, store, store.reserve(brief, profile, loaded), profile, loaded

    def test_task_budget_is_sent_instead_of_model_ceiling(self):
        server, store, job, profile, loaded = self.prepare(budget=256)
        self.assertEqual(run_local_attempt(self.state, job['attempt_id']), 0)
        self.assertEqual(server.requests[0]['max_output_tokens'], 256)
        self.assertEqual(store.attempt(job['attempt_id'])['data']['request_settings']['max_output_tokens'], 256)
        self.assertEqual(store.job(job['job_id'])['profile']['approval']['request_settings']['max_output_tokens'], 1024)

    def test_task_budget_enforcement_uses_sent_limit(self):
        server, store, job, profile, loaded = self.prepare(budget=256, output_tokens=256)
        self.assertEqual(run_local_attempt(self.state, job['attempt_id']), 1)
        self.assertEqual(store.job(job['job_id'])['reason'], 'output_budget_exhausted')
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'complete')

    def test_context_checks_selected_budget_not_unused_ceiling(self):
        brief, profile = self.brief(), self.profile()
        profile['request_settings']['max_output_tokens'] = 32768
        brief['task_requirements']['max_output_tokens'] = 512
        self.assertTrue(context_fits(brief, profile, self.loaded()))
        brief['task_requirements']['max_output_tokens'] = 8192
        self.assertFalse(context_fits(brief, profile, self.loaded()))

    def test_invalid_task_budgets_are_rejected(self):
        for budget in (0, -1, True, 1.5, '2048'):
            with self.subTest(budget=budget):
                brief = self.brief()
                brief['task_requirements']['max_output_tokens'] = budget
                with self.assertRaisesRegex(ValueError, 'invalid_requirements'):
                    validate_brief(brief)

    def test_budget_cannot_exceed_approved_model_ceiling(self):
        from local_model_delegation.scheduler import rank_profiles
        brief, profile = self.brief(), self.profile()
        brief['task_requirements']['max_output_tokens'] = 2048
        self.assertEqual(rank_profiles(brief, [profile]), [])
        with self.assertRaisesRegex(ValueError, 'generation_budget_exceeded'):
            build_model_request(brief, profile, 'fixture-instance')
        with self.assertRaisesRegex(ValueError, 'generation_budget_exceeded'):
            Store(self.state).reserve(brief, profile, self.loaded())
        with Store(self.state).db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_omitted_task_budget_keeps_saved_profile_allowance(self):
        self.assertEqual(build_model_request(self.brief(), self.profile(), 'fixture-instance')['max_output_tokens'], 1024)

    def test_verified_exhaustion_frees_slot_without_accepting_candidate(self):
        server, store, job, profile, loaded = self.prepare(output_tokens=1024)
        original = store.job(job['job_id'])['brief_hash']
        self.assertEqual(run_local_attempt(self.state, job['attempt_id']), 1)
        attempt = store.attempt(job['attempt_id'])
        self.assertEqual(attempt['state'], 'complete')
        self.assertEqual(attempt['data']['terminal']['stats']['total_output_tokens'], 1024)
        self.assertGreater(attempt['data']['finished_at'], attempt['data']['submitted_at'])
        self.assertEqual(store.instance(attempt['instance_key'])['state'], 'ready')
        result = store.job(job['job_id'])
        self.assertEqual(result['reason'], 'output_budget_exhausted')
        self.assertEqual(result['status'], 'fallback_required')
        self.assertIsNone(result['result_path'])
        self.assertEqual(result['brief_hash'], original)
        self.assertEqual(store.reserve(self.brief('next-task'), profile, loaded)['status'], 'reserved')
        run_local_attempt(self.state, job['attempt_id'])
        self.assertEqual(server.calls.count(('POST', '/api/v1/chat')), 1)

    def test_reasoning_only_exhaustion_settles_without_answer(self):
        server, store, job, profile, loaded = self.prepare(answer='', output_tokens=1024)
        server.terminal_result = {'model_instance_id':'fixture-instance', 'stats':{'total_output_tokens':1024,'reasoning_output_tokens':1024},
                                  'output':[{'type':'reasoning','content':'private reasoning'}]}
        run_local_attempt(self.state, job['attempt_id'])
        attempt = store.attempt(job['attempt_id'])
        self.assertEqual(attempt['state'], 'complete')
        self.assertNotIn('private reasoning', json.dumps(attempt))
        self.assertEqual(store.job(job['job_id'])['reason'], 'output_budget_exhausted')

    def test_invalid_terminal_evidence_keeps_uncertainty(self):
        for mutation in ('instance', 'stats', 'reasoning_count', 'output', 'stream_mismatch'):
            with self.subTest(mutation=mutation):
                server, store, job, profile, loaded = self.prepare(output_tokens=1024)
                result = {'model_instance_id':'fixture-instance','stats':{'total_output_tokens':1024},
                          'output':[{'type':'message','content':server.answer}]}
                if mutation == 'instance': result['model_instance_id'] = 'wrong'
                if mutation == 'stats': result['stats']['total_output_tokens'] = True
                if mutation == 'reasoning_count': result['stats']['reasoning_output_tokens'] = 1025
                if mutation == 'output': result['output'] = [{'type':'tool_call','content':'not supported'}]
                if mutation == 'stream_mismatch': result['output'][0]['content'] = 'different'
                server.terminal_result = result
                run_local_attempt(self.state, job['attempt_id'])
                self.assertEqual(store.attempt(job['attempt_id'])['state'], 'uncertain')
                # Each variant uses a new isolated fixture queue.
                self.state = self.root / ('next-state-' + mutation)

    def test_exhaustion_does_not_release_a_healthy_peer(self):
        server, store, job, profile, loaded = self.prepare(output_tokens=1024)
        peer = store.reserve(self.brief('peer'), profile, {**loaded,'capacity':2})
        self.assertEqual(peer['status'], 'reserved')
        before = store.attempt(peer['attempt_id'])
        run_local_attempt(self.state, job['attempt_id'])
        self.assertEqual(store.attempt(peer['attempt_id']), before)
        self.assertEqual(store.instance(before['instance_key'])['state'], 'ready')

    def test_generation_fencing_prevents_terminal_release(self):
        server, store, job, profile, loaded = self.prepare()
        attempt = store.attempt(job['attempt_id'])
        store.transition(job['attempt_id'], attempt['generation'], 'reserved', 'submitting', {})
        store.transition(job['attempt_id'], attempt['generation'], 'submitting', 'streaming', {})
        with store.db(write=True) as db:
            db.execute('UPDATE instances SET generation=generation+1')
        self.assertFalse(store.finish_exhausted(job['attempt_id'], attempt['generation'], {}))
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'streaming')

    def test_completion_without_confirmed_start_keeps_slot_uncertain(self):
        server, store, job, profile, loaded = self.prepare(answer='', output_tokens=1024)
        events = [('chat.end', {'result':{'model_instance_id':'fixture-instance',
                   'stats':{'total_output_tokens':1024}, 'output':[]}})]
        with patch('local_model_delegation.lmstudio.Runtime.stream', return_value=iter(events)):
            run_local_attempt(self.state, job['attempt_id'])
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'uncertain')

    def test_ceiling_refresh_waits_for_active_work_then_reuses_idle_runtime(self):
        server, store, job, profile, loaded = self.prepare()
        changed = copy.deepcopy(profile)
        changed['request_settings']['max_output_tokens'] = 2048
        changed['approval']['request_settings'] = copy.deepcopy(changed['request_settings'])
        key = store.attempt(job['attempt_id'])['instance_key']
        for state in ('reserved','submitting','streaming','uncertain'):
            with store.db(write=True) as db:
                db.execute('UPDATE attempts SET state=? WHERE attempt_id=?', (state,job['attempt_id']))
            result = store.reserve(self.brief('busy-'+state), changed, loaded)
            self.assertEqual(result['reason'], 'model_busy')
            self.assertEqual(store.instance(key)['state'], 'ready')
        with store.db(write=True) as db:
            db.execute("UPDATE attempts SET state='complete' WHERE attempt_id=?", (job['attempt_id'],))
        result = store.reserve(self.brief('idle'), changed, loaded)
        self.assertEqual(result['status'], 'reserved')
        self.assertEqual(store.job(job['job_id'])['profile'], profile)
        self.assertEqual(store.instance(key)['data']['profile'], changed)

    def test_explicit_ceiling_change_preserves_assessment_and_binds_approval(self):
        from local_model_delegation.onboarding import approve_scope
        from local_model_delegation.contracts import load_json
        profile = self.profile()
        profile['assessment'] = {'historical':'fixture'}
        self.write_config(profile)
        before = (self.state/'config.json').read_bytes()
        approve_scope(self.state, 'fictional', 'fixture-budget-consent', profile['scope'], max_output_tokens=32768)
        current = load_json((self.state/'profiles/fictional.json').read_text())
        self.assertEqual(current['request_settings']['max_output_tokens'], 32768)
        self.assertEqual(current['approval']['request_settings'], current['request_settings'])
        self.assertEqual(current['assessment'], profile['assessment'])
        self.assertEqual((self.state/'config.json').read_bytes(), before)

    def test_measurement_binding_distinguishes_actual_generation_settings(self):
        from local_model_delegation.measurements import model_binding
        profile = self.profile()
        actual = {**profile['request_settings'], 'max_output_tokens':256}
        binding = model_binding(profile, executed=True, request_settings=actual)
        self.assertEqual(binding['settings_digest'], digest(actual))
        self.assertNotEqual(binding['settings_digest'], model_binding(profile, executed=True)['settings_digest'])

    def test_historical_observations_do_not_gain_missing_metadata(self):
        from local_model_delegation.measurements import job_observation
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), self.loaded())
        with store.db() as db:
            attempt = job_observation(db, job['job_id'])['attempts'][0]
        self.assertEqual(set(attempt), {'attempt_id','state','submitted_at','finished_at','inference_seconds'})

    def test_measurements_capture_effective_budget_and_terminal_without_rewriting_history(self):
        from local_model_delegation import measurements as m
        from local_model_delegation.contracts import canonical
        from tests.test_measurements import Measurements
        server, store, first, profile, loaded = self.prepare(output_tokens=1024)
        run_local_attempt(self.state, first['attempt_id'])
        before = store.attempt(first['attempt_id'])
        m.initialize_measurements(self.state)
        self.project_id = m.register_project(self.state, self.project, 'Fixture')['project_id']
        brief = self.brief('measured'); brief['task_requirements']['max_output_tokens'] = 256
        context = Measurements.context(self, scope={'capability':brief['capability'],
            **{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
            'input_bytes':len(canonical({'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode()),
            'file_count':len(brief['files'])})
        job = store.enqueue(brief, brief['fallback'], measurement=context)
        job = store.admit(job['job_id'], profile, loaded, {'pressure':'normal','observed_at':time.time()})
        server.output_tokens = 256
        run_local_attempt(self.state, job['attempt_id'])
        with store.db() as db:
            observation = m.job_observation(db, job['job_id'])
        self.assertEqual(observation['binding']['settings_digest'], digest({**profile['request_settings'],'max_output_tokens':256}))
        self.assertEqual(observation['attempts'][0]['request_settings']['max_output_tokens'], 256)
        self.assertEqual(observation['attempts'][0]['terminal']['stats']['total_output_tokens'], 256)
        self.assertTrue(observation['fallback'])
        self.assertEqual(m.reconcile_measurements(self.state)['conflicts'], [])
        self.assertEqual(store.attempt(first['attempt_id']), before)

    def test_cli_ceiling_change_requires_valid_explicit_approval(self):
        from tests.test_cli import CLI
        profile = self.profile(); self.write_config(profile)
        scope = self.root/'scope.json'; scope.write_text(json.dumps(profile['scope']))
        path = self.state/'profiles/fictional.json'
        before = path.read_bytes()
        args = ('profile','approve','--profile-id','fictional','--owner-reference','fixture-consent','--scope',str(scope),'--max-output-tokens')
        CLI.invoke(self, *args, '0')
        self.assertEqual(path.read_bytes(), before)
        result = CLI.invoke(self, *args, '32768')
        self.assertEqual(result['status'], 'approval_recorded')
        self.assertEqual(json.loads(path.read_text())['approval']['request_settings']['max_output_tokens'], 32768)
