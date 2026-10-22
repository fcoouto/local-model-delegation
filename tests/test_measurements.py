import copy
import importlib.util
import json
import sqlite3
from tests.support import Fixture
from local_model_delegation.contracts import digest
from local_model_delegation.store import Store


NATIVE = {'host':'fixture', 'provider':'fixture', 'model':'native', 'reasoning':'medium', 'boundary':'whole_task'}
BINDING = {'profile_id':'fictional','artifact_digest':'a'*64,'runtime_digest':'b'*64,
           'settings_digest':'c'*64,'helper_digest':'d'*64}


class Measurements(Fixture):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.measurements'), 'measurement ledger is missing')
        from local_model_delegation import measurements
        return measurements

    def setup_metrics(self):
        m = self.api(); self.write_config(enabled=False); Store(self.state)
        m.initialize_measurements(self.state)
        project = m.register_project(self.state, self.project, 'Example')
        self.project_id = project['project_id']
        return m

    def context(self, **changes):
        manifest = {'instructions':{}, 'toolchain':{'python':'fictional'}, 'checks':{}}
        return {'project_id':self.project_id, 'origin':'normal_work',
                'scope':{'capability':'code_change','language':'python','complexity':'simple',
                         'context_bucket':'small','input_bytes':100,'file_count':1},
                'environment_digest':digest(manifest), 'environment_manifest':manifest,
                'native_binding':NATIVE, 'source_revision':None, 'case_id':'case', 'case_hash':'a'*64, **changes}

    def receipt(self, kind, payload, key='event', **changes):
        return {'schema_version':1,'producer':'fixture','source_key':key,'kind':kind,
                'observed_at':100.0,'payload':payload, **changes}

    def test_additive_initialization_preserves_queue_and_configuration(self):
        m = self.api(); config = self.write_config(enabled=False); store = Store(self.state)
        before = config.read_bytes()
        with store.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            jobs = db.execute('SELECT * FROM jobs').fetchall()
        m.initialize_measurements(self.state); m.initialize_measurements(self.state)
        self.assertEqual(before, config.read_bytes())
        with store.db() as db:
            self.assertEqual(version, db.execute('PRAGMA user_version').fetchone()[0])
            self.assertEqual(jobs, db.execute('SELECT * FROM jobs').fetchall())
            db.execute('UPDATE measurement_meta SET version=99')
        with self.assertRaisesRegex(ValueError, 'unsupported_measurement_version'): m.initialize_measurements(self.state)

    def test_projects_and_context_replay_are_not_silently_merged(self):
        m = self.setup_metrics()
        self.assertEqual(m.register_project(self.state, self.project, 'Example')['project_id'], self.project_id)
        self.assertNotEqual(m.register_project(self.state, self.artifact, 'Example')['project_id'], self.project_id)
        a = m.begin_measurement(self.state, 'task', self.context())
        self.assertEqual(a, m.begin_measurement(self.state, 'task', self.context()))
        with self.assertRaisesRegex(ValueError, 'measurement_conflict'):
            m.begin_measurement(self.state, 'task', self.context(case_id='different'))
        with self.assertRaisesRegex(ValueError, 'invalid_measurement_context'):
            m.begin_measurement(self.state, 'bad', self.context(environment_digest='0'*64))

    def test_invalid_receipts_do_not_write_or_create_state(self):
        m = self.setup_metrics(); m.begin_measurement(self.state, 'task', self.context())
        for receipt in [self.receipt('invented', {}), self.receipt('delivery', {}, observed_at=float('nan'))]:
            with self.assertRaises(ValueError): m.append_event(self.state, 'task', receipt)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            self.assertEqual(0, db.execute('SELECT count(*) FROM measurement_events').fetchone()[0])
        absent = self.root/'absent'
        with self.assertRaisesRegex(ValueError, 'measurement_state_missing'): m.initialize_measurements(absent)
        self.assertFalse(absent.exists())

    def test_cli_initializes_and_records_without_runtime_calls(self):
        import contextlib, io
        from local_model_delegation.cli import main
        from unittest.mock import patch
        self.write_config(enabled=False); Store(self.state)
        def invoke(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['--state-dir', str(self.state), 'metrics', *args])
            self.assertEqual(code, 0, output.getvalue())
            return json.loads(output.getvalue())
        with patch('local_model_delegation.lmstudio.Runtime.stream', side_effect=AssertionError('no inference')):
            self.assertEqual(invoke('init')['measurement_version'], 1)
            self.project_id = invoke('register','--root',str(self.project),'--label','Example')['project_id']
            path = self.root/'context.json';path.write_text(json.dumps(self.context()))
            self.assertEqual(invoke('begin','--task','native-task','--context',str(path))['task_id'], 'native-task')
        self.assertFalse(json.loads((self.state/'profiles.json').read_text())['routing_enabled'])

    def test_event_replay_and_correction_preserve_history(self):
        m = self.setup_metrics(); m.begin_measurement(self.state, 'task', self.context())
        m.begin_measurement(self.state, 'other', self.context())
        receipt = self.receipt('delivery', {'outcome':'not_integrated','artifact_hash':'a'*64,
                              'checks_hash':'b'*64,'native_task_id':None,'durations':{}})
        first = m.append_event(self.state,'task',receipt)
        self.assertEqual(first, m.append_event(self.state,'task',receipt))
        with self.assertRaisesRegex(ValueError,'measurement_conflict'):
            m.append_event(self.state,'task',{**receipt,'observed_at':101})
        correction = {**receipt,'source_key':'correction','supersedes':first['event_id']}
        with self.assertRaisesRegex(ValueError,'invalid_measurement_correction'):
            m.append_event(self.state,'other',correction)
        m.append_event(self.state,'task',correction)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            self.assertEqual(2,db.execute('SELECT count(*) FROM measurement_events').fetchone()[0])

    def staged_measurement(self):
        from tests.test_delegation import Delegation
        m = self.api()
        brief = Delegation.generic(self)
        store, job = Delegation.stage_job(self, brief, Delegation.proposal(self, brief))
        m.initialize_measurements(self.state)
        self.project_id = m.register_project(self.state,self.project,'Example')['project_id']
        context = self.context(scope={'capability':brief['capability'],
            **{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
            'input_bytes':len(__import__('local_model_delegation.contracts',fromlist=['canonical']).canonical(
                {'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode()),
            'file_count':len(brief['files'])})
        m.begin_measurement(self.state, job, context, job)
        return m, store, job

    def test_verdict_survives_native_rescue_and_reconciliation(self):
        from tests.test_delegation import Delegation
        from local_model_delegation.validation import prepare_verification, record_verification
        m, store, job = self.staged_measurement()
        session = prepare_verification(self.state, job)
        receipt = Delegation.receipt(self, session); receipt['criteria'] = [False]
        record_verification(self.state, job, receipt)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            verdicts = db.execute("SELECT receipt FROM measurement_events WHERE kind='local_verdict'").fetchall()
        self.assertEqual(len(verdicts),1, 'local verdict must survive fallback replacement')
        self.assertFalse(json.loads(verdicts[0][0])['payload']['accepted'])
        before = store.attempt(store.job(job)['attempt_id'])
        self.assertEqual(m.reconcile_measurements(self.state)['conflicts'], [])
        self.assertEqual(before, store.attempt(store.job(job)['attempt_id']))
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            db.execute("DELETE FROM measurement_events WHERE kind='local_verdict'")
        m.reconcile_measurements(self.state)
        with sqlite3.connect(self.state/'state.sqlite3') as db:
            self.assertEqual(1,db.execute("SELECT count(*) FROM measurement_events WHERE kind='local_verdict'").fetchone()[0])

    def test_enqueue_context_is_atomic_and_cannot_change_on_retry(self):
        from tests.test_delegation import Delegation
        from local_model_delegation.store import atomic_json
        m = self.setup_metrics(); brief = Delegation.generic(self)
        atomic_json(self.state/'config.json', {'schema_version':2,'routing_enabled':True})
        store = Store(self.state)
        with store.db() as db: store.upgrade_schema(db)
        self.assertIn('measurement', __import__('inspect').signature(store.enqueue).parameters)
        context = self.context(scope={'capability':brief['capability'],
            **{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
            'input_bytes':len(__import__('local_model_delegation.contracts',fromlist=['canonical']).canonical(
                {'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode()),
            'file_count':len(brief['files'])})
        job = store.enqueue(brief, brief['fallback'], measurement=context)
        self.assertEqual(job, store.enqueue(brief, brief['fallback'], measurement=context))
        with self.assertRaisesRegex(ValueError,'measurement_conflict'):
            store.enqueue(brief, brief['fallback'], measurement={**context,'case_id':'changed'})
        with store.db() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM jobs').fetchone()[0])

    def test_bound_job_cannot_be_attributed_to_another_project_or_scope(self):
        m, store, job = self.staged_measurement()
        other = m.register_project(self.state,self.artifact,'Other')['project_id']
        with store.db() as db: db.execute('DELETE FROM measurement_tasks WHERE task_id=?',(job,))
        with self.assertRaisesRegex(ValueError,'measurement_project_mismatch'):
            m.begin_measurement(self.state,'forged',self.context(project_id=other),job)

    def usage(self, amount=300, **changes):
        return {'native_binding':NATIVE,'source_run_id':'run','span_id':'span','start':1,'end':10,
                'phase':'whole_task','usage_schema':'input_output_v1','tokens':{'input':amount,'output':0,'cached_input':0,'reasoning_output':0},
                'complete':True,'attribution':'exclusive','evidence_hash':'e'*64,'group_id':'whole',
                'role':'total','expected_spans':1,'overhead_complete':True,'allocations':None, **changes}

    def report_rows(self, outcome='unchanged_local', usage=300):
        self.project_id = 'project'
        tasks=[];events=[]
        for name, result, amount in [('local',outcome,usage),('native','native_only',1000)]:
            observation={'status':'accepted','reason':None,'binding':BINDING if name=='local' else {},
                'attempts':[{'attempt_id':'attempt','state':'complete','submitted_at':10,'finished_at':20,'inference_seconds':10}] if name=='local' else [],
                'native_task_id':None,'fallback':result=='native_fallback','queued_at':9,'request_bytes':1024}
            tasks.append({'task_id':name,'context':self.context(),'job_id':name if name=='local' else None,'observation':observation})
            def add(kind,payload,key):
                events.append({'event_id':name+key,'task_id':name,**self.receipt(kind,payload,key=name+key)})
            if name=='local': add('local_verdict',{'attempt_id':'attempt','candidate_hash':'a'*64,'checks_hash':'b'*64,
                                                  'accepted':result=='unchanged_local','category':'semantic'},'verdict')
            add('delivery',{'outcome':result,'artifact_hash':'a'*64,'checks_hash':'b'*64,'native_task_id':None,'durations':{'overall':20}},'delivery')
            add('usage',self.usage(amount,source_run_id=name),'usage')
        events.append({'event_id':'overhead','task_id':'local',**self.receipt('usage',self.usage(100,phase='onboarding',
            source_run_id='setup',allocations={'local':1.0}),key='overhead')})
        return {'projects':[],'tasks':tasks,'events':events,'pairs':[{'local_task':'local','native_task':'native','method':'paired_usage_proxy'}]}

    def test_report_savings_include_overhead_and_negative_failed_routes(self):
        m=self.api();self.assertTrue(hasattr(m,'build_report'),'report calculation is missing')
        for usage, outcome, expected in [(300,'unchanged_local',600),(1100,'native_fallback',-200)]:
            report=m.build_report(self.report_rows(outcome,usage),project_id='project',profile_id='fictional',now=200)
            cohort=report['cohorts'][0]
            self.assertEqual(cohort['savings']['net_native_token_proxy'],expected)
            self.assertEqual(cohort['quality']['local_delivery']['passed'],int(outcome=='unchanged_local'))
            self.assertEqual(cohort['quality']['local_delivery']['evaluated'],1)
            self.assertEqual(cohort['savings']['subscription_savings'],'unknown')

    def test_unknown_and_incompatible_usage_never_means_zero(self):
        m=self.api();self.assertTrue(hasattr(m,'build_report'),'report calculation is missing')
        for changes in [{'complete':False},{'attribution':'shared'},{'usage_schema':'unknown'},
                        {'tokens':{'input':None,'output':0,'cached_input':None,'reasoning_output':0}},
                        {'native_binding':{**NATIVE,'model':'other'}},{'overhead_complete':False}]:
            rows=self.report_rows()
            next(e for e in rows['events'] if e['event_id']=='localusage')['payload'].update(changes)
            cohort=m.build_report(rows,project_id='project',profile_id='fictional',now=200)['cohorts'][0]
            self.assertIsNone(cohort['savings']['net_native_token_proxy'])
            self.assertTrue(cohort['savings']['unknown_reasons'])

    def test_counts_separate_cohorts_pending_and_repeated_cases(self):
        m=self.api();self.assertTrue(hasattr(m,'build_report'),'report calculation is missing')
        rows=self.report_rows();original=rows['tasks'][0]
        for i in range(35):
            task=copy.deepcopy(original);task['task_id']='task'+str(i);rows['tasks'].append(task)
        other=copy.deepcopy(original);other['task_id']='changed';other['context']['environment_digest']='f'*64;rows['tasks'].append(other)
        report=m.build_report(rows,project_id='project',profile_id='fictional',now=200)
        self.assertEqual(len(report['cohorts']),2)
        cohort=next(c for c in report['cohorts'] if c['coverage']['tasks']==36)
        self.assertEqual(cohort['coverage']['distinct_cases'],1)
        self.assertEqual(cohort['quality']['first_candidate']['evaluated'],1)
        self.assertEqual(cohort['coverage']['missing_verdicts'],35)
        self.assertIsNone(cohort['latency']['overall']['p95'])

    def test_usage_span_alias_cannot_double_count_across_projects(self):
        m=self.setup_metrics();m.begin_measurement(self.state,'task',self.context());m.begin_measurement(self.state,'other',self.context())
        self.assertTrue(hasattr(m,'record_usage'),'usage ingestion is missing')
        receipt=self.receipt('usage',self.usage())
        first=m.record_usage(self.state,'task',receipt)
        self.assertEqual(first,m.record_usage(self.state,'task',receipt))
        with self.assertRaisesRegex(ValueError,'usage_span_conflict'):
            m.record_usage(self.state,'other',{**receipt,'source_key':'alias'})
        with self.assertRaises(ValueError):
            m.record_usage(self.state,'task',self.receipt('usage',self.usage(span_id='overhead',allocations={'task':.7,'other':.7}),key='bad'))

    def test_totals_do_not_double_count_components_or_token_subsets(self):
        m=self.api();rows=self.report_rows()
        total=next(e for e in rows['events'] if e['event_id']=='localusage')
        total['payload']['tokens']={'input':200,'output':100,'cached_input':150,'reasoning_output':80}
        component=copy.deepcopy(total);component.update(event_id='component',source_key='component')
        component['payload'].update(role='component',span_id='component',phase='verification')
        rows['events'].append(component)
        report=m.build_report(rows,project_id='project',profile_id='fictional',now=200)
        self.assertEqual(report['cohorts'][0]['savings']['net_native_token_proxy'],600)

    def test_recent_window_and_p95_require_enough_observations(self):
        m=self.api();rows=self.report_rows();template=rows['tasks'][0]
        for i in range(34):
            task=copy.deepcopy(template);task['task_id']='local'+str(i);task['context']['case_hash']=format(i+100,'064x');rows['tasks'].append(task)
            rows['events'].append({'event_id':'delivery'+str(i),'task_id':task['task_id'],**self.receipt('delivery',
                {'outcome':'not_integrated','artifact_hash':'a'*64,'checks_hash':'b'*64,'native_task_id':None,'durations':{'overall':i+1}},
                key='delivery'+str(i),observed_at=101+i)})
        cohort=m.build_report(rows,project_id='project',profile_id='fictional',now=200)['cohorts'][0]
        self.assertEqual(cohort['last_30_closed']['fallback']['closed_decisions'],30)
        self.assertEqual(cohort['latency']['overall']['samples'],35)
        self.assertEqual(cohort['latency']['overall']['p95'],33)

    def test_delivery_requires_correction_instead_of_two_terminal_outcomes(self):
        m=self.setup_metrics();m.begin_measurement(self.state,'task',self.context())
        payload={'outcome':'not_integrated','artifact_hash':'a'*64,'checks_hash':'b'*64,'native_task_id':None,'durations':{}}
        m.append_event(self.state,'task',self.receipt('delivery',payload))
        with self.assertRaisesRegex(ValueError,'delivery_already_recorded'):
            m.append_event(self.state,'task',self.receipt('delivery',{**payload,'outcome':'native_edited'},key='other'))
